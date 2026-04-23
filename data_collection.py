import pandas as pd

# TO NOT REMOVE : Way to write the names of the columns if we loose them
# cols = ["Temperature", "Humidity", "Light"]
# for i in range(15, 41):
#     cols.append("Frequency:" + str(i) + "kHz")
# for i in range(180, 231):
#     cols.append("Frequency:" + str(i) + "kHz")

# collects the data and writes it in plant_data.csv 
def write_data(sweep: list):
    temp = 20 # TODO: request to get temperature
    humidity = 0 # TODO: request to get humidity
    light = False # TODO: request for light

    # fills the current line with all the collected data
    curr_line = [temp, humidity, light]
    for i in sweep:
        curr_line.append(i)
    
    # fills the csv by making a dataframe with the collected data, and 
    # appends it to the file
    df = pd.DataFrame([curr_line], columns=cols)
    df.to_csv("plant_data.csv", mode="a", index=False, header=False)



