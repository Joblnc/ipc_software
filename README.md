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
