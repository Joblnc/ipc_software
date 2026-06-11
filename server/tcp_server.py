import socket
import struct
import sys
import argparse
import threading
import queue
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import asyncio
from data_collection import write_data, LightCycleController


def get_collection_config():
    # number of cycles and phase duration drive the automatic light schedule.
    # CLI flags override the interactive prompts (handy in tmux / scripts).
    parser = argparse.ArgumentParser(description="Automated plant data collection")
    parser.add_argument("--cycles", type=int, help="number of ON/OFF cycles to run")
    parser.add_argument("--minutes", type=float,
                        help="minutes per phase (light ON for n min, then OFF for n min)")
    parser.add_argument("--start-off", action="store_true",
                        help="start each cycle with the light OFF instead of ON")
    args = parser.parse_args()

    cycles = args.cycles
    if cycles is None:
        cycles = int(input("Number of cycles [4]: ") or 4)

    minutes = args.minutes
    if minutes is None:
        minutes = float(input("Minutes per phase (light ON / light OFF) [15]: ") or 15)

    start_on = not args.start_off

    total_minutes = cycles * 2 * minutes
    print(f"\nRunning {cycles} cycle(s) of {minutes} min "
          f"{'ON' if start_on else 'OFF'} + {minutes} min "
          f"{'OFF' if start_on else 'ON'}  ->  total {total_minutes} min\n")

    return LightCycleController(cycles, minutes * 60, start_on)

def get_local_ip():
    # creates false socket to get our ip
    temp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # simulates a connexion to google (8.8.8.8), 
        # forces computer to choose its own WiFi / ethernet card
        temp_socket.connect(('8.8.8.8', 80))
        ip = temp_socket.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        temp_socket.close()
    return ip

def frequencies_list():
    # list containing different frequencies
    freq_list = []
    x_axis_freqs = []
    # frequency of the RP2040
    max_freq = 125000000
    # iteration from 15kHz to 40kHz
    for i in range(15, 41, 1):
        target_freq = i * 1000
        x_axis_freqs.append(target_freq)
        # gets the top, considering that div_int = 1 and div_frac = 0
        top = max_freq // (i * 1000) - 1
        # appends top, div_int and div_frac encoded to be understabndable by the RP2040
        freq_list.append(struct.pack('<HBB', top, 1, 0))
    # iteration from 180kHz to 230kHz
    for i in range(180, 231, 1):
        target_freq = i * 1000
        x_axis_freqs.append(target_freq)
        # gets the top, considering that div_int = 1 and div_frac = 0
        top = max_freq // (i * 1000) - 1
        # appends top, div_int and div_frac encoded to be understabndable by the RP2040
        freq_list.append(struct.pack('<HBB', top, 1, 0))

    # gets the list as one long byte sequence, optimization
    payload = b"".join(freq_list)
    return payload, len(freq_list), x_axis_freqs

def send_instructions(s : socket.socket):
    print("sending data to Arduino")

    payload, count, x_axis = frequencies_list()
    # says to arduino that it will receive the list of frequencies
    s.send(struct.pack('<B', 3))

    # TODO : look for a delay between each sweep

    # indicates to the arduino the nb of frequences to sweep
    s.send(struct.pack('<H', count))
    # sends the sequence of frequencies
    s.send(payload)
    # says to Arduino that it can start to sweep
    s.send(struct.pack('<B', 1))
    return x_axis

# Queue to transfer network data to graphical interface
data_queue = queue.Queue(maxsize=5)

# Signaled by the UDP thread once all the requested cycles are done,
# so the main (matplotlib) thread can close the window and return.
collection_done = threading.Event()

# Function that runs backwards, to collect udp data without blocking display of data
def udp_listener_thread(host, port, expected_length, controller):
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.bind((host, port))
    print(f"UDP listening started on {host}:{port}...")

    # the cycle clock starts when we begin listening for data
    controller.start()

    try:
        while not collection_done.is_set():
            # stop as soon as the configured number of cycles has elapsed
            if controller.is_finished():
                asyncio.run(controller.finish())
                collection_done.set()
                break

            # 2048 is the max number of bytes to read
            data_bytes, _ = udp_socket.recvfrom(2048)
            # data_bytes stores answers on 2 bytes, so actual nb of bytes is len // 2
            nb_answers = len(data_bytes) // 2

            if nb_answers == expected_length:
                # Unpacks data with the correct format
                data = struct.unpack(f"<{nb_answers}H", data_bytes)

                # Only keeps most recent data for display
                if data_queue.full():
                    try:
                        data_queue.get_nowait()
                    except queue.Empty:
                        pass
                data_queue.put(data)
                # Writes the data in a csv file and drives the light schedule
                asyncio.run(write_data(data, controller))

    except Exception as e:
        print(f"Error UDP : {e}")
    finally:
        udp_socket.close()


# Function to collect data from Arduino in UDP and to display it
def receive_answers_animated(host: str, x_axis: list, controller):
    UDP_PORT = 12345

    collection_done.clear()

    # Starts network listening in a separate thread
    listener = threading.Thread(target=udp_listener_thread,
                                args=(host, UDP_PORT, len(x_axis), controller), daemon=True)
    listener.start()

    # Configuration of Matplotlib
    fig, ax = plt.subplots(figsize=(10, 6))
    fig.canvas.manager.set_window_title("Internet of Plants - Biosignal")
    
    # Style and colors
    ax.set_facecolor('#f8f9fa') # Very bright gray
    fig.patch.set_facecolor('#ffffff') # White
    
    # Creation of the reference green line
    line, = ax.plot(x_axis, np.zeros(len(x_axis)), '-', color='#2ca02c', linewidth=2, alpha=0.9)
    
    # Titles and labels
    ax.set_title("Signature d'impédance de la plante", fontsize=14, fontweight='bold', pad=15)
    ax.set_xlabel("Fréquence (Hz)", fontsize=12)
    ax.set_ylabel("Amplitude brute (ADC)", fontsize=12)
    
    # Grid
    ax.grid(True, linestyle=':', alpha=0.7, color='#6c757d')
    ax.set_xlim(min(x_axis), max(x_axis))

    # Update function (called automatically with Matplotlib)
    def update_graph(frame):
        # close the window from the main thread once all cycles are done
        if collection_done.is_set():
            plt.close(fig)
            return line,
        try:
            # Gets previous data
            data = data_queue.get_nowait()
            line.set_ydata(data)

            # Adjusting Y axis, to avoid flat effect when the plant is not touched
            min_y = min(data)
            max_y = max(data)
            margin = (max_y - min_y) * 0.1 
            
            # In case there's no signal, puts a small margin
            if margin == 0: 
                margin = 100 
                
            # Focus on current data
            ax.set_ylim(max(0, min_y - margin), min(4095, max_y + margin))
            
            # Fills area under the curve
            if hasattr(update_graph, 'fill_poly'):
                update_graph.fill_poly.remove()
            update_graph.fill_poly = ax.fill_between(x_axis, data, min(0, min_y - margin), color='#2ca02c', alpha=0.15)

            return line,
        
        except queue.Empty:
            # If no new data, does nothing
            return line,

    # Intializes the filling variable
    update_graph.fill_poly = ax.fill_between(x_axis, np.zeros(len(x_axis)), 0, color='#2ca02c', alpha=0.1)

    # Starts the animation
    ani = animation.FuncAnimation(fig, update_graph, interval=50, blit=False, cache_frame_data=False)
    
    plt.tight_layout()
    plt.show()


def main():
    # ask for / parse the cycle configuration before opening the server
    controller = get_collection_config()

    host = get_local_ip()
    port = 20000

    # creates a socket in TCP mode
    tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # security : to avoid error "Address already in use"
    tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        # binds the socket to the correct port and host
        tcp_socket.bind((host, port))
    except socket.error:
        print("Socket couldn't connect to expected address.")
        sys.exit()

    # server is now listening; can only accept one connexion by one
    tcp_socket.listen(1)
    print("Server waiting for a request ...")

    while True:
        arduino_socket, arduino_address = tcp_socket.accept()
        print(f"Arduino connecté depuis {arduino_address}")

        try:
            # send the list of frequencies to arduino
            x_axis = send_instructions(arduino_socket)
            # gets the corresponding answers (blocks until the cycles finish or the window is closed)
            receive_answers_animated(host, x_axis, controller)

            if collection_done.is_set():
                print("Data collection finished: all cycles completed.")
                arduino_socket.close()
                break

        except ConnectionResetError:
            print("Arduino disconnected")
        finally:
            arduino_socket.close()
            print("waiting for new connexion...")

if __name__ == "__main__":
    main()