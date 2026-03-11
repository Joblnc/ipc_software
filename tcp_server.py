import socket
import struct
import sys

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
    # frequency of the RP2040
    max_freq = 125000000
    # iteration from 20kHz to 250kHz
    for i in range(20, 251):
        # gets the top, considering that div_int = 1 and div_frac = 0
        top = max_freq // (i * 1000) - 1
        # appends top, div_int and div_frac encoded to be understabndable by the RP2040
        freq_list.append(struct.pack('<HBB', top, 1, 0))
    # gets the list as one long byte sequence, optimization
    payload = b"".join(freq_list)
    return payload, len(freq_list)

def send_instructions(s : socket.socket):
    print("sending data to Arduino")

    payload, count = frequencies_list()
    # says to arduino that it will receive the list of frequencies
    s.send(struct.pack('<B', 3))

    # TODO : look for a delay between each sweep

    # indicates to the arduino the nb of frequences to sweep
    s.send(struct.pack('<H', count))
    # sends the sequence of frequencies
    s.send(payload)
    # says to Arduino that it can start to sweep
    s.send(struct.pack('<B', 1))
    return

def receive_answers(host : str):
    # configures a socket for UDP protocol
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # Arduino sends data on port 12345, so we get data on this port
    UDP_PORT = 12345
    udp_socket.bind((host, UDP_PORT))

    try:
        while True:
            # recvfrom stops the script, waiting for somthing from arduino
            # 2048 is the max number of bytes to read
            data_bytes, arduino_address = udp_socket.recvfrom(2048)
            
            # data_bytes stores answers on 2 bytes, so tha actual nb of bytes is len // 2
            nb_answers = len(data_bytes) // 2
            # fromat used for unpacking
            unpack_format = f"<{nb_answers}H"
            data = struct.unpack(unpack_format, data_bytes)

            for e in data:
                print(e)
            print(f"number of data answers got :{len(data)}")

            udp_socket.close()

            return
            # TODO : save the data
            
    except KeyboardInterrupt:
        print("Stops reception.")
    finally:
        udp_socket.close()

def main():
    # indicates the ip to use, and the port where to send data
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

    while(True):
        # gets the socket and address of the arduino that connects to the TCP socket
        arduino_socket, arduino_address = tcp_socket.accept()
        print(f"Arduino connected from {arduino_address}")

        try:
            # send the list of frequencies to arduino
            send_instructions(arduino_socket)
            # gets the corresponding answers
            receive_answers(host)
            # maybe have to remove the return: it's just here to stop the program after getting the answers
            #return
        except ConnectionResetError:
            print("Arduino disconnected")
        finally:
            arduino_socket.close()
            print("waiting for new connexion")

main()