import hmac
import hashlib
import os
import time
from pathlib import Path

import requests

def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file(Path(__file__).with_name(".env"))

CLIENT_ID = os.getenv("TUYA_CLIENT_ID")
SECRET = os.getenv("TUYA_SECRET")
DEVICE_ID = os.getenv("TUYA_DEVICE_ID")
BASE_URL = os.getenv("TUYA_BASE_URL", "https://openapi.tuyaeu.com")

if not CLIENT_ID or not SECRET or not DEVICE_ID:
    raise RuntimeError("TUYA_CLIENT_ID, TUYA_SECRET et TUYA_DEVICE_ID doivent être définis dans env_control/.env")

# Un hash vide standard utilisé par Tuya pour les requêtes GET
EMPTY_HASH = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'


print("Demande du token en cours...")
t_token = str(int(time.time() * 1000))
url_token = '/v1.0/token?grant_type=1'

string_to_sign_token = f"GET\n{EMPTY_HASH}\n\n{url_token}"
message_token = CLIENT_ID + t_token + string_to_sign_token
sign_token = hmac.new(SECRET.encode('utf-8'), msg=message_token.encode('utf-8'), digestmod=hashlib.sha256).hexdigest().upper()

headers_token = {
    'client_id': CLIENT_ID,
    'sign': sign_token,
    't': t_token,
    'sign_method': 'HMAC-SHA256'
}

response_token = requests.get(BASE_URL + url_token, headers=headers_token).json()

if not response_token.get('success'):
    print("Erreur fatale : Impossible de récupérer le token.")
    print(response_token)
    exit()

access_token = response_token['result']['access_token']
print(f"Token récupéré avec succès !\n")


print("Lecture des propriétés de l'appareil...")
t_device = str(int(time.time() * 1000))
url_device = f'/v2.0/cloud/thing/{DEVICE_ID}/shadow/properties'

string_to_sign_device = f"GET\n{EMPTY_HASH}\n\n{url_device}"
message_device = CLIENT_ID + access_token + t_device + string_to_sign_device
sign_device = hmac.new(SECRET.encode('utf-8'), msg=message_device.encode('utf-8'), digestmod=hashlib.sha256).hexdigest().upper()

headers_device = {
    'client_id': CLIENT_ID,
    'access_token': access_token,
    'sign': sign_device,
    't': t_device,
    'sign_method': 'HMAC-SHA256'
}

response_device = requests.get(BASE_URL + url_device, headers=headers_device).json()

if response_device.get('success'):
    properties = response_device.get('result', {}).get('properties', [])

    temperature = None
    humidite = None

    for prop in properties:
        if prop.get('code') == 'temp_indoor':
            temperature = prop.get('value')
        elif prop.get('code') == 'humidity_indoor':
            humidite = prop.get('value')

    print(f"Température : {temperature}°F")
    print(f"Humidité    : {humidite}%")

else:
    print("Erreur lors de la lecture de l'appareil :")
    print(response_device)
