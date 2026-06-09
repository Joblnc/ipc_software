# ipc_software

## Launch the tcp_serv detached

- Go in the script arduino, change the WiFi SSID, WiFi password, and ip of the servers (Note : your servers and your Arduino have to be on the same WiFi)

```bash
tmux new -s data_collector # create new session if not already created
python3 tcp_server.py
Ctrl+B then d # Detach
tmux attach -t data_collector # Attach
```

## Setup temporary wifi

- Check wifi adapter : `nmcli d`
- Plug the usb wifi adapter
- Find the one that is newly plugged
- Execute : `nmcli device wifi hotspot ifname <adapter_name> ssid "MyAccessPoint" password "12345678"`
