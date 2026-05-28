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

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
IP_SC = os.getenv("IP_SC")
CLIENT_ID = os.getenv("TUYA_CLIENT_ID")
SECRET = os.getenv("TUYA_SECRET")
DEVICE_ID = os.getenv("TUYA_DEVICE_ID")

if not EMAIL or not PASSWORD or not IP_SC or not CLIENT_ID or not SECRET or not DEVICE_ID:
    raise RuntimeError("Env variables must be define in the .env file at the root")

# TO NOT REMOVE : Way to write the names of the columns if we loose them
# cols = ["Temperature", "Humidity", "Light"]
# for i in range(15, 41):
#     cols.append("Frequency:" + str(i) + "kHz")
# for i in range(180, 231):
#     cols.append("Frequency:" + str(i) + "kHz")

# gets the light status by connecting to the connected stopcontact
# since we have to wait for client.p110, this function has to be awaited too
async def get_light_status():
    try:
        # connects to the stopcontact
        client = ApiClient(EMAIL, PASSWORD)
        device = await client.p110(IP_SC)

        # next line is for debug
        #print(f"{'\033[92m'}Connected to the lamp !{'\033[0m'}")

        # gets the information about the light state
        info = await device.get_device_info_json()
        return True if info.get("device_on", False) else False
    
    except Exception as e:
        print(f"{'\033[91m'}error : {e}\n{'\033[0m'}")

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
    light = await get_light_status()

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
asyncio.run(write_data(l))
