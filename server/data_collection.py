import pandas as pd
import asyncio
import os
from pathlib import Path
from typing import Sequence
from dotenv import load_dotenv
from tapo import ApiClient
import hmac
import hashlib
import time
import requests

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

class LightCycleController:
    """Drives the light through a fixed number of cycles.

    One cycle is `phase_seconds` with the light in its starting state followed
    by `phase_seconds` in the opposite state (by default: ON then OFF).
    The desired state is computed from the elapsed time, so the light is always
    set to the right state even if some sweeps are missed.
    """

    def __init__(self, num_cycles: int, phase_seconds: float, start_on: bool = True):
        self.num_cycles = num_cycles
        self.phase_seconds = phase_seconds
        self.start_on = start_on
        self.cycle_seconds = phase_seconds * 2
        self.total_seconds = num_cycles * self.cycle_seconds
        self.start_time: float | None = None
        self.device = None
        # last state we deliberately applied, to avoid hitting the light every sweep
        self._last_desired: bool | None = None

    def start(self):
        self.start_time = time.monotonic()

    def elapsed(self) -> float:
        if self.start_time is None:
            return 0.0
        return time.monotonic() - self.start_time

    def is_finished(self) -> bool:
        return self.start_time is not None and self.elapsed() >= self.total_seconds

    def desired_state(self) -> bool:
        # which half of the current cycle are we in?
        position = self.elapsed() % self.cycle_seconds
        in_first_phase = position < self.phase_seconds
        return self.start_on if in_first_phase else not self.start_on

    async def ensure_device(self):
        if self.device is None:
            self.device = await _get_light_device()
        return self.device

    async def apply(self) -> bool:
        """Set the light to the state expected for the current time. Returns that state."""
        if self.start_time is None:
            self.start()

        device = await self.ensure_device()
        desired = self.desired_state()

        # only talk to the light when the target state changes
        if desired != self._last_desired:
            current = await get_light_status(device)
            if current is not None and current != desired:
                await toggle_light(device, current)
            self._last_desired = desired

        return desired

    async def finish(self):
        """Turn the light off at the end of the run."""
        device = await self.ensure_device()
        current = await get_light_status(device)
        if current:
            await toggle_light(device, current)
            print("Light turned OFF: all cycles finished")

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

async def write_data(sweep: Sequence, controller: "LightCycleController | None" = None, real_data = False):
    curr_line = []
    file_path = "test_data.csv"
    for i in sweep:
        curr_line.append(i)

    if (not real_data):
        (temp, humidity) = await get_humidity_and_temperature()

        if controller is not None:
            # the controller owns the light: it decides the state from the cycle schedule
            light = await controller.apply()
        else:
            # no schedule: just record the current light state without touching it
            light_device = await _get_light_device()
            light = await get_light_status(light_device)

        print("light:", light)
        print("temperature:", temp)
        print("humidity:", humidity)

        # fills the current line with all the collected data
        curr_line = [temp, humidity, light]
        file_path = "plant_data.csv"
    
    
    # fills the csv by making a dataframe with the collected data, and 
    # appends it to the file
    df = pd.DataFrame([curr_line])
    df.to_csv(file_path, mode="a", index=False, header=False)