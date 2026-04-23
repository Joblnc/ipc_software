import pandas as pd
import asyncio
from tapo import ApiClient

from env_control.test_lampe import EMAIL, PASSWORD, IP_SC

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

# collects the data and writes it in plant_data.csv 
# since we have to wait for get_light_status, this function has to be awaited too

async def write_data(sweep: list):
    temp = 20 # TODO: request to get temperature
    humidity = 0 # TODO: request to get humidity
    light = await get_light_status()
    print(light)

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
