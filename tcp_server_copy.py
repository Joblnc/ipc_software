import socket
import struct
import sys
import threading
import queue
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation

# --- Fonctions inchangées ---
def get_local_ip():
    temp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        temp_socket.connect(('8.8.8.8', 80))
        ip = temp_socket.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        temp_socket.close()
    return ip

def frequencies_list():
    freq_list = []
    x_axis_freqs = []
    max_freq = 125000000
    
    # ATTENTION : Si tu veux suivre l'expérience du document (1kHz de pas), 
    # remplace le "10" par "1" ci-dessous.
    for i in range(20, 251, 10): 
        target_freq = i * 1000
        x_axis_freqs.append(target_freq)
        top = max_freq // (i * 1000) - 1
        freq_list.append(struct.pack('<HBB', top, 1, 0))
        
    payload = b"".join(freq_list)
    return payload, len(freq_list), x_axis_freqs

def send_instructions(s: socket.socket):
    print("Envoi des instructions à l'Arduino...")
    payload, count, x_axis = frequencies_list()
    s.send(struct.pack('<B', 3))
    s.send(struct.pack('<H', count))
    s.send(payload)
    s.send(struct.pack('<B', 1))
    return x_axis


# --- NOUVELLE APPROCHE : Écoute UDP en arrière-plan ---

# File d'attente pour passer les données du réseau vers l'interface graphique
data_queue = queue.Queue(maxsize=5)

def udp_listener_thread(host, port, expected_length):
    """Tourne en arrière-plan pour attraper les paquets UDP sans bloquer l'affichage."""
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.bind((host, port))
    print(f"Écoute UDP démarrée sur {host}:{port}...")
    
    try:
        while True:
            data_bytes, _ = udp_socket.recvfrom(2048)
            nb_answers = len(data_bytes) // 2
            
            if nb_answers == expected_length:
                data = struct.unpack(f"<{nb_answers}H", data_bytes)
                
                # On ne garde que la donnée la plus récente pour l'affichage
                if data_queue.full():
                    try:
                        data_queue.get_nowait()
                    except queue.Empty:
                        pass
                data_queue.put(data)
                
                # TODO: C'est ici que tu peux ajouter ton code pour SAUVEGARDER 
                # 'data' dans un fichier CSV ou .npy
                
    except Exception as e:
        print(f"Erreur UDP : {e}")
    finally:
        udp_socket.close()


# --- NOUVELLE APPROCHE : Affichage Animé ---

def receive_answers_animated(host: str, x_axis: list):
    UDP_PORT = 12345
    
    # 1. Lancer l'écoute réseau dans un thread séparé
    listener = threading.Thread(target=udp_listener_thread, args=(host, UDP_PORT, len(x_axis)), daemon=True)
    listener.start()

    # 2. Configuration esthétique de Matplotlib
    fig, ax = plt.subplots(figsize=(10, 6))
    fig.canvas.manager.set_window_title("Internet of Plants - Biosignal")
    
    # Couleurs et style
    ax.set_facecolor('#f8f9fa') # Fond gris très clair
    fig.patch.set_facecolor('#ffffff')
    
    # Création de la ligne (verte)
    line, = ax.plot(x_axis, np.zeros(len(x_axis)), '-', color='#2ca02c', linewidth=2, alpha=0.9)
    
    # Titres et labels
    ax.set_title("Signature d'impédance de la plante", fontsize=14, fontweight='bold', pad=15)
    ax.set_xlabel("Fréquence (Hz)", fontsize=12)
    ax.set_ylabel("Amplitude brute (ADC)", fontsize=12)
    
    # Grille fine
    ax.grid(True, linestyle=':', alpha=0.7, color='#6c757d')
    ax.set_xlim(min(x_axis), max(x_axis))

    # 3. Fonction de mise à jour (appelée automatiquement en boucle par Matplotlib)
    def update_graph(frame):
        try:
            # Récupère la dernière donnée reçue sans bloquer
            data = data_queue.get_nowait()
            line.set_ydata(data)

            # Ajustement DYNAMIQUE de l'axe Y (C'est ça qui enlève l'effet ratatiné !)
            min_y = min(data)
            max_y = max(data)
            margin = (max_y - min_y) * 0.1 # Ajoute 10% de marge en haut et en bas
            
            if margin == 0: 
                margin = 100 # Sécurité si le signal est totalement plat
                
            # On recadre la vue sur les données actuelles
            ax.set_ylim(max(0, min_y - margin), min(4095, max_y + margin))
            
            # Optionnel : Remplir la zone sous la courbe pour un côté plus "Dashboard"
            if hasattr(update_graph, 'fill_poly'):
                update_graph.fill_poly.remove()
            update_graph.fill_poly = ax.fill_between(x_axis, data, min(0, min_y - margin), color='#2ca02c', alpha=0.15)

            return line,
        
        except queue.Empty:
            # Pas de nouvelle donnée, on ne change rien
            return line,

    # Initialisation de la variable de remplissage
    update_graph.fill_poly = ax.fill_between(x_axis, np.zeros(len(x_axis)), 0, color='#2ca02c', alpha=0.1)

    # 4. Lancement de l'animation (rafraîchissement toutes les 50ms)
    ani = animation.FuncAnimation(fig, update_graph, interval=50, blit=False, cache_frame_data=False)
    
    plt.tight_layout()
    plt.show() # Ouvre la fenêtre et gère la boucle principale


def main():
    host = get_local_ip()
    port = 20000

    tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        tcp_socket.bind((host, port))
    except socket.error:
        print("Erreur de liaison TCP.")
        sys.exit()

    tcp_socket.listen(1)
    print("Serveur en attente de la connexion Arduino (TCP)...")

    while True:
        arduino_socket, arduino_address = tcp_socket.accept()
        print(f"Arduino connecté depuis {arduino_address}")

        try:
            x_axis = send_instructions(arduino_socket)
            
            # On appelle notre nouvelle fonction d'affichage
            receive_answers_animated(host, x_axis)
            
        except ConnectionResetError:
            print("Arduino déconnecté")
        finally:
            arduino_socket.close()
            print("En attente d'une nouvelle connexion...")

if __name__ == "__main__":
    main()