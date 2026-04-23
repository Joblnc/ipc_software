import asyncio
from tapo import ApiClient

IP_SC = "192.168.12.90"
EMAIL = "aubin.thome@atelier-lyon.com"
PASSWORD = "pXC#0JE07OJyiqcIlek!u5$J4YXH!m"


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
