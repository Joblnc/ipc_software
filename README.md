# ipc_software

## Launch the tcp_serv detached

- Go in the script arduino, change the WiFi SSID, WiFi password, and ip of the servers (Note : your servers and your Arduino have to be on the same WiFi)

```bash
tmux new -s data_collector # create new session if not already created
source .venv/bin/activate
python3 tcp_server.py
Ctrl+B then d # Detach
tmux attach -t data_collector # Attach
```

## Automated collection (light cycles)

At launch the server asks how many **cycles** to run and how many **minutes per phase**.
One cycle = `n` min with the light ON followed by `n` min with the light OFF.
After the requested number of cycles the light is turned off, collection stops, and the window closes.

You can skip the prompts with CLI flags (handy for tmux / scripts):

```bash
python3 tcp_server.py --cycles 4 --minutes 15   # 4 cycles of 15 min ON + 15 min OFF
python3 tcp_server.py --cycles 6 --minutes 10 --start-off  # start each cycle with light OFF
```

## Setup temporary wifi

- Check wifi adapter : `nmcli d`
- Plug the usb wifi adapter
- Find the one that is newly plugged
- Execute : `nmcli device wifi hotspot ifname <adapter_name> ssid "MyAccessPoint" password "12345678"`

## What the repo is composed of

### Arduino Folder
- The script that runs on Arduino. You might have to change the SSID, WiFi password, and ip of the server if you change the WiFi you work with
- the given script from polish guys

### Machine_learning Folder
- A training set, that you can fill up with more data as you wish
- A test set, that you can replace or fill up (might disappear for the final product)
- A training script, that trains an LSTM and saves the best model it makes in the folder, as "ipc_model.pth"
- A test script, that tests the test set. If a model already exists, it uses it for testing. If no model exists, it trains a new one

(Note : when you train a model, a file "ipc_scaler.gz" appears. It's the scaler from the training, since we have to use the same for training and testing. If you remove it, when testing it will train a whole new model) 
