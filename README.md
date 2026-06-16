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

- A raw data collection (e.g. `data_13_06_2026.csv`) used to train the model
- `ml_script.py` : cleans the data, splits it, trains an LSTM and evaluates it
- `predict.py` : uses the trained model to tell, live, if the light is ON or OFF
- After a training run, three artifacts appear (all needed together for inference) :
  - `ipc_model.pth` : the best model weights
  - `ipc_scaler.gz` : the scaler fit on the training data (the SAME scaling must be used for inference)
  - `ipc_meta.json` : the exact feature order + config (seq length, dead-time)
- The train/validation/test splits are also written out (`training_set.csv`, ...) so they can be inspected

## Machine learning

The ML scripts need PyTorch, which is **not** in the server `.venv`. Use a dedicated env :

```bash
cd machine_learning
python3.10 -m venv .venv
.venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv/bin/pip install scikit-learn pandas numpy joblib
```

### Train the model

```bash
cd machine_learning
.venv/bin/python ml_script.py
```

This cleans `data_13_06_2026.csv`, splits it **chronologically** (not randomly, to avoid
leaking neighbouring rows of the same light cycle), trains the LSTM with early stopping,
prints the test-set accuracy and saves `ipc_model.pth` / `ipc_scaler.gz` / `ipc_meta.json`.

Key knobs at the top of `ml_script.py` :

- `SEQ_LEN` : how many consecutive sweeps the model looks at (default 10)
- `SETTLE_ROWS` : dead-time. The plant reacts to a light change with a lag, so the sweeps
  right after a toggle still look like the previous state. Windows within this many sweeps
  of a toggle are dropped from training and evaluation (default 40)
- `USE_ENV_FEATURES` : also feed Temperature/Humidity on top of the 77 frequencies

### Predict the light state from sweeps

`predict.py` exposes a `LightPredictor` that takes the **same 10-sweep window** the model
was trained on. Feed it one sweep at a time :

```python
from predict import LightPredictor

predictor = LightPredictor()            # loads model + scaler + meta

# each time a new sweep arrives (the 77 frequency values):
out = predictor.push(sweep)
# out is None until 10 sweeps are buffered, then:
#   {"prob": 0.87, "on": True, "settled": True}

# tell it whenever the light is switched, so it can flag the unreliable dead-time:
predictor.notify_toggle()               # for SETTLE_ROWS sweeps after this, out["settled"] is False
```

You can also run it from the command line on a CSV :

```bash
.venv/bin/python predict.py test_set.csv   # has a Light column -> prints the accuracy
.venv/bin/python predict.py input.csv      # no Light column   -> prints ON/OFF per row
```

`input.csv` must hold **consecutive sweeps** with the 77 `Frequency:NkHz` columns. Each
prediction uses 10 consecutive rows, so give at least 10 (the first 9 only build up history).

(Note : `predict.py` needs torch, so run it from `machine_learning/.venv`, not the server env.)
