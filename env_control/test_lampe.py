import asyncio
import os
from pathlib import Path

from tapo import ApiClient

IP_SC = "192.168.12.90"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_env_file(Path(__file__).with_name(".env"))

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

if not EMAIL or not PASSWORD:
    raise RuntimeError("EMAIL et PASSWORD doivent être définis dans env_control/.env")


async def afficher_statut(device):
    info = await device.get_device_info_json()
    etat = "ON" if info.get("device_on", False) else "OFF"
    print(f"📊 Statut actuel: {etat}")

async def main():
    print(f"⏳ Tentative de connexion à la prise {IP_SC}...")

    try:
        client = ApiClient(EMAIL, PASSWORD)

        device = await client.p110(IP_SC)
        print("✅ Authentification réussie !")
        await afficher_statut(device)

        print("⌨️  Commandes: on | off | status | q")

        while True:
            commande = (await asyncio.to_thread(input, "> ")).strip().lower()

            if commande == "on":
                await device.on()
                print("💡 Prise allumée")
                await afficher_statut(device)
            elif commande == "off":
                await device.off()
                print("🌙 Prise éteinte")
                await afficher_statut(device)
            elif commande in {"q", "status", "stat"}:
                await afficher_statut(device)
            elif commande in {"q", "quit", "exit"}:
                print("👋 Fin du contrôle")
                break
            else:
                print("Commande inconnue. Utilise: on | off | status | q")

    except Exception as e:
        print(f"❌  ERREUR : {e}\n")

if __name__ == "__main__":
    asyncio.run(main())
