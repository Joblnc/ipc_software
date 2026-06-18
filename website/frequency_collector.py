from __future__ import annotations

import socket
import struct
from pathlib import Path

import pandas as pd


def get_local_ip() -> str:
    """Return the local IP address used to reach the network interface.
    
    This function uses a clever trick: it attempts a dummy UDP connection 
    to a public DNS (Google's 8.8.8.8). This forces the OS to route the packet 
    through the primary network interface (Wi-Fi/Ethernet). We then extract 
    and return the source IP address assigned to that interface.
    """
    temp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        temp_socket.connect(("8.8.8.8", 80))
        return temp_socket.getsockname()[0]
    except Exception:
        # Fallback to localhost if there is no network connection
        return "127.0.0.1"
    finally:
        temp_socket.close()


def frequencies_list() -> tuple[bytes, int, list[int]]:
    """Build the frequency sweep payload to configure the Arduino hardware.
    
    Returns:
        - payload: A concatenated byte string of all hardware instructions.
        - count: The total number of frequencies to sweep.
        - x_axis_freqs: A list of the actual frequencies (in Hz) for reference.
    """
    freq_payloads: list[bytes] = []
    x_axis_freqs: list[int] = []
    # Base clock speed of the microcontroller (125 MHz, typical for RP2040/Pico)
    max_freq = 125_000_000

    # First frequency band: 15 kHz to 40 kHz
    for freq_khz in range(15, 41):
        target_freq = freq_khz * 1000
        x_axis_freqs.append(target_freq)
        
        # Calculate the timer 'top' value required to generate this specific frequency
        top = max_freq // target_freq - 1
        
        # Pack into a C-struct format:
        # < : Little-endian (standard for Arduino/ARM)
        # H : Unsigned short (2 bytes) -> The 'top' timer value
        # B : Unsigned char (1 byte)  -> Number of samples to read (1)
        # B : Unsigned char (1 byte)  -> Delay in milliseconds after reading (0 ms)
        freq_payloads.append(struct.pack("<HBB", top, 1, 0))

    # Second frequency band: 180 kHz to 230 kHz
    for freq_khz in range(180, 231):
        target_freq = freq_khz * 1000
        x_axis_freqs.append(target_freq)
        top = max_freq // target_freq - 1
        freq_payloads.append(struct.pack("<HBB", top, 1, 0))

    # Combine all individual 4-byte instructions into one single payload
    payload = b"".join(freq_payloads)
    return payload, len(freq_payloads), x_axis_freqs


def send_instructions(tcp_socket: socket.socket) -> list[int]:
    """Send the frequency sweep definition to the connected Arduino over TCP.
    
    TCP is used here because configuration requires guaranteed, error-free delivery.
    """
    payload, count, x_axis = frequencies_list()

    # Protocol sequence expected by the Arduino firmware:
    # 1. Send '3' (Command type indicating a sweep setup)
    tcp_socket.send(struct.pack("<B", 3))
    # 2. Send the total number of frequencies
    tcp_socket.send(struct.pack("<H", count))
    # 3. Send the actual binary payload (timer settings)
    tcp_socket.send(payload)
    # 4. Send '1' (Command to start the sweep process)
    tcp_socket.send(struct.pack("<B", 1))

    return x_axis


def _frequency_columns(x_axis: list[int]) -> list[str]:
    """Helper to generate pandas DataFrame column names based on the frequencies."""
    return [f"Frequency:{freq // 1000}kHz" for freq in x_axis]


def collect_frequency_lines(
    num_lines: int = 10,
    host: str | None = None,
    tcp_port: int = 20000,
    udp_port: int = 12345,
    timeout: float | None = 30.0,
) -> pd.DataFrame:
    """Collect real-time UDP sweeps from the Arduino and return them as a DataFrame.

    This function acts as a dual-protocol server:
    1. It hosts a TCP server to securely send the configuration to the Arduino.
    2. It hosts a UDP server to receive the massive, high-speed data stream. 
       (UDP is preferred for streaming as it avoids TCP congestion and overhead).
    """
    host = host or get_local_ip()
    rows: list[list[int]] = []

    # --- 1. TCP Server Setup (Configuration Channel) ---
    tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcp_socket.bind((host, tcp_port))
    tcp_socket.listen(1)

    # --- 2. UDP Server Setup (Data Streaming Channel) ---
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    udp_socket.bind((host, udp_port))
    if timeout is not None:
        udp_socket.settimeout(timeout)

    try:
        print(f"Waiting for Arduino on {host}:{tcp_port}...")
        
        # Block until the Arduino establishes a TCP connection
        tcp_client, tcp_address = tcp_socket.accept()
        print(f"Arduino connected from {tcp_address}")

        try:
            # Brief the Arduino with the hardware settings
            x_axis = send_instructions(tcp_client)
            expected_length = len(x_axis)
            column_names = _frequency_columns(x_axis)

            # Listen to the UDP data stream
            while len(rows) < num_lines:
                # Receive up to 2048 bytes (more than enough for our sweep size)
                data_bytes, _ = udp_socket.recvfrom(2048)
                
                # Each reading is a 16-bit integer (2 bytes)
                nb_answers = len(data_bytes) // 2

                # Discard corrupted or incomplete UDP packets
                if nb_answers != expected_length:
                    continue

                # Unpack the binary data into a tuple of integers
                data = struct.unpack(f"<{nb_answers}H", data_bytes)
                rows.append(list(data))

            return pd.DataFrame(rows, columns=column_names)

        finally:
            # Always cleanly close the client connection
            tcp_client.close()

    finally:
        # Always release the network ports back to the OS
        udp_socket.close()
        tcp_socket.close()


def save_frequency_lines(
    output_path: str | Path,
    num_lines: int = 10,
    host: str | None = None,
    tcp_port: int = 20000,
    udp_port: int = 12345,
    timeout: float | None = 30.0,
) -> pd.DataFrame:
    """Collect lines using collect_frequency_lines and save them to a CSV file."""
    dataframe = collect_frequency_lines(
        num_lines=num_lines,
        host=host,
        tcp_port=tcp_port,
        udp_port=udp_port,
        timeout=timeout,
    )
    
    output_path = Path(output_path)
    # Ensure the target directory exists before saving
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Save the dataframe without the row indices
    dataframe.to_csv(output_path, index=False)
    
    return dataframe


if __name__ == "__main__":
    # Test execution: collect 10 sweeps and print the first 5
    df = collect_frequency_lines(num_lines=10)
    print(df.head())