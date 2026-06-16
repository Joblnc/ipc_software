# 1. On part d'un "mini-ordinateur" Linux avec Python 3.11 pré-installé
FROM python:3.11-slim

# 2. On se place dans un dossier /app à l'intérieur de ce mini-ordinateur
WORKDIR /app

# 3. On installe quelques outils de base Linux (souvent nécessaires pour compiler PyTorch ou Tapo)
RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

# 4. On copie le fichier des dépendances en premier (C'est une astuce pour que Docker aille plus vite)
COPY website/requirements.txt ./requirements.txt

# 5. On demande à Python d'installer toutes les librairies
RUN pip install --no-cache-dir -r requirements.txt

# 6. On copie absolument TOUT ton dossier (ipc_software) à l'intérieur du conteneur
COPY . .

# 7. On indique que notre site communiquera sur le port 5000
EXPOSE 5000

# 8. La commande qui sera exécutée au démarrage du conteneur
CMD ["python3", "-m", "website.backend"]