import pandas as pd
import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
from tapo import ApiClient
import hmac
import hashlib
import time
import requests

LIGHT_TOGGLE_INTERVAL_SECONDS = 15 * 60
_last_light_toggle = time.monotonic()

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
IP_LIGHT = os.getenv("IP_LIGHT")
CLIENT_ID = os.getenv("TUYA_CLIENT_ID")
SECRET = os.getenv("TUYA_SECRET")
DEVICE_ID = os.getenv("TUYA_DEVICE_ID")

if not EMAIL or not PASSWORD or not IP_LIGHT or not CLIENT_ID or not SECRET or not DEVICE_ID:
    raise RuntimeError("Env variables must be define in the .env file at the root")

# TO NOT REMOVE : Way to write the names of the columns if we loose them
# cols = ["Temperature", "Humidity", "Light"]
# for i in range(15, 41):
#     cols.append("Frequency:" + str(i) + "kHz")
# for i in range(180, 231):
#     cols.append("Frequency:" + str(i) + "kHz")

async def _get_light_device():
    if not EMAIL or not PASSWORD or not IP_LIGHT:
        raise RuntimeError("Env variables must be define in the .env file at the root")

    client = ApiClient(EMAIL, PASSWORD)
    return await client.p110(IP_LIGHT)

async def get_light_status(device=None):
    try:
        if device is None:
            device = await _get_light_device()

        # next line is for debug
        #print(f"{'\033[92m'}Connected to the lamp !{'\033[0m'}")

        # gets the information about the light state
        info = await device.get_device_info_json()
        return True if info.get("device_on", False) else False

    except Exception as e:
        print(f"{'\033[91m'}error : {e}\n{'\033[0m'}")

async def toggle_light(device=None, current_state=None):
    try:
        if device is None:
            device = await _get_light_device()

        if current_state is None:
            current_state = await get_light_status(device)

        if current_state:
            await device.off()
            print("Light toggled: OFF")
        else:
            await device.on()
            print("Light toggled: ON")

    except Exception as e:
        print(f"{'\033[91m'}error while toggling light : {e}\n{'\033[0m'}")

async def toggle_light_every_15_minutes_if_needed(device, current_state):
    global _last_light_toggle

    now = time.monotonic()
    if now - _last_light_toggle >= LIGHT_TOGGLE_INTERVAL_SECONDS:
        await toggle_light(device, current_state)
        _last_light_toggle = now
        return not current_state

    return current_state

async def test_light_toggle_at_start():
    global _last_light_toggle

    device = await _get_light_device()
    initial_state = await get_light_status(device)

    print("Startup toggle test: switching the light once")
    await toggle_light(device, initial_state)
    await asyncio.sleep(2)
    await toggle_light(device, not initial_state)
    print("Startup toggle test finished: light restored")

    _last_light_toggle = time.monotonic()

async def get_humidity_and_temperature() -> tuple[int | None, int | None]:
    BASE_URL = "https://openapi.tuyaeu.com"
    EMPTY_HASH = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'

    try:
        if not CLIENT_ID or not SECRET or not DEVICE_ID:
            raise RuntimeError("Env variables must be define in the .env file at the root")

        print("Demande du token Tuya en cours...")
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
            print("Error : Can't get token")
            print(response_token)
            return (None, None)

        access_token = response_token['result']['access_token']
        print(f"Token collected !\n")

        print("Getting proprieties...")
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
            humidity = None

            for prop in properties:
                if prop.get('code') == 'temp_indoor':
                    temperature = prop.get('value')
                elif prop.get('code') == 'humidity_indoor':
                    humidity = prop.get('value')

            return (temperature, humidity)

        print("Error while reading")
        print(response_device)
        return (None, None)

    except Exception as e:
        print(f"{'\033[91m'}error : {e}\n{'\033[0m'}")
        return (None, None)

# collects the data and writes it in plant_data.csv 
# since we have to wait for get_light_status, this function has to be awaited too

async def write_data(sweep: list):
    (temp, humidity) = await get_humidity_and_temperature()
    light_device = await _get_light_device()
    current_light_state = await get_light_status(light_device)
    light = await toggle_light_every_15_minutes_if_needed(light_device, current_light_state)

    print("light:", light)
    print("temperature:", temp)
    print("humidity:", humidity)

    # fills the current line with all the collected data
    curr_line = [temp, humidity, light]
    for i in sweep:
        curr_line.append(i)
    
    # fills the csv by making a dataframe with the collected data, and 
    # appends it to the file
    df = pd.DataFrame([curr_line])
    df.to_csv("plant_data.csv", mode="a", index=False, header=False)


l = [0] * 79

async def main():
    await test_light_toggle_at_start()
    await write_data(l)


asyncio.run(main())
