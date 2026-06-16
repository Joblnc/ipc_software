from __future__ import annotations

import socket
import struct
from pathlib import Path

import pandas as pd


def get_local_ip() -> str:
    """Return the local IP address used to reach the network interface."""
    temp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        temp_socket.connect(("8.8.8.8", 80))
        return temp_socket.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        temp_socket.close()


def frequencies_list() -> tuple[bytes, int, list[int]]:
    """Build the same frequency payload as the original tcp_server."""
    freq_payloads: list[bytes] = []
    x_axis_freqs: list[int] = []
    max_freq = 125_000_000

    for freq_khz in range(15, 41):
        target_freq = freq_khz * 1000
        x_axis_freqs.append(target_freq)
        top = max_freq // target_freq - 1
        freq_payloads.append(struct.pack("<HBB", top, 1, 0))

    for freq_khz in range(180, 231):
        target_freq = freq_khz * 1000
        x_axis_freqs.append(target_freq)
        top = max_freq // target_freq - 1
        freq_payloads.append(struct.pack("<HBB", top, 1, 0))

    payload = b"".join(freq_payloads)
    return payload, len(freq_payloads), x_axis_freqs


def send_instructions(tcp_socket: socket.socket) -> list[int]:
    """Send the frequency sweep definition to the connected Arduino."""
    payload, count, x_axis = frequencies_list()

    tcp_socket.send(struct.pack("<B", 3))
    tcp_socket.send(struct.pack("<H", count))
    tcp_socket.send(payload)
    tcp_socket.send(struct.pack("<B", 1))

    return x_axis


def _frequency_columns(x_axis: list[int]) -> list[str]:
    return [f"Frequency:{freq // 1000}kHz" for freq in x_axis]


def collect_frequency_lines(
    num_lines: int = 10,
    host: str | None = None,
    tcp_port: int = 20000,
    udp_port: int = 12345,
    timeout: float | None = 30.0,
) -> pd.DataFrame:
    """Collect ``num_lines`` UDP sweeps and return them as a DataFrame.

    This is the minimal extraction of ``tcp_server.py``: it keeps the TCP
    handshake and the UDP reception, but removes the light controller,
    animation, queueing, and CSV writing logic.
    """
    host = host or get_local_ip()
    rows: list[list[int]] = []

    tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcp_socket.bind((host, tcp_port))
    tcp_socket.listen(1)

    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    udp_socket.bind((host, udp_port))
    if timeout is not None:
        udp_socket.settimeout(timeout)

    try:
        print(f"Waiting for Arduino on {host}:{tcp_port}...")
        tcp_client, tcp_address = tcp_socket.accept()
        print(f"Arduino connected from {tcp_address}")

        try:
            x_axis = send_instructions(tcp_client)
            expected_length = len(x_axis)
            column_names = _frequency_columns(x_axis)

            while len(rows) < num_lines:
                data_bytes, _ = udp_socket.recvfrom(2048)
                nb_answers = len(data_bytes) // 2

                if nb_answers != expected_length:
                    continue

                data = struct.unpack(f"<{nb_answers}H", data_bytes)
                rows.append(list(data))

            return pd.DataFrame(rows, columns=column_names)

        finally:
            tcp_client.close()

    finally:
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
    """Collect lines and save them to disk while returning the DataFrame."""
    dataframe = collect_frequency_lines(
        num_lines=num_lines,
        host=host,
        tcp_port=tcp_port,
        udp_port=udp_port,
        timeout=timeout,
    )
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_csv(output_path, index=False)
    return dataframe


if __name__ == "__main__":
    df = collect_frequency_lines(num_lines=10)
    print(df.head())