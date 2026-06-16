"""Standalone light-state predictor.

Self-contained: it does NOT import anything from the rest of the project. Drop
this folder anywhere (it ships with the trained artifacts next to it) and call:

    from predict_csv import predict_csv
    result = predict_csv("input.csv")   # -> JSON-serializable dict

`result` is meant to be handed straight to a web page. It contains the per-row
predictions plus a `current` summary (the most recent window).

Required files next to this script (already bundled):
    ipc_model.pth   - trained LSTM weights
    ipc_scaler.gz   - the scaler used at training time
    ipc_meta.json   - feature order + config (seq length, etc.)

Dependencies: see requirements.txt (torch, scikit-learn, pandas, numpy, joblib).
"""

import os
import json

import joblib
import numpy as np
import torch
import torch.nn as nn

# the artifacts live next to this file, so the folder is portable
HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(HERE, "ipc_model.pth")
SCALER_PATH = os.path.join(HERE, "ipc_scaler.gz")
META_PATH = os.path.join(HERE, "ipc_meta.json")

# frequency column names in the order the Arduino sends a sweep
# (15-40 kHz then 180-230 kHz), matching the training CSV header.
FREQ_NAMES = ([f"Frequency:{i}kHz" for i in range(15, 41)] +
              [f"Frequency:{i}kHz" for i in range(180, 231)])


class _IPCLSTM(nn.Module):
	"""Same architecture the model was trained with (copied so we stay isolated)."""

	def __init__(self, input_size, hidden_size=32, num_layers=1):
		super().__init__()
		self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)
		self.fc = nn.Linear(hidden_size, 1)

	def forward(self, x):
		out, _ = self.lstm(x)
		return torch.sigmoid(self.fc(out[:, -1, :]))


# the model/scaler/meta are loaded once and reused across calls
_STATE = {}


def _load(model_dir=None):
	"""Load (and cache) the model, scaler and meta. Returns the loaded bundle."""
	model_dir = model_dir or HERE
	if _STATE.get("dir") == model_dir:
		return _STATE

	with open(os.path.join(model_dir, "ipc_meta.json")) as f:
		meta = json.load(f)
	scaler = joblib.load(os.path.join(model_dir, "ipc_scaler.gz"))
	model = _IPCLSTM(input_size=len(meta["features"]))
	model.load_state_dict(
		torch.load(os.path.join(model_dir, "ipc_model.pth"), weights_only=True)
	)
	model.eval()

	_STATE.update(dir=model_dir, meta=meta, scaler=scaler, model=model)
	return _STATE


def predict_csv(csv_path, model_dir=None, threshold=0.5):
	"""Predict the light state for every window in a CSV of consecutive sweeps.

	The CSV must contain the 77 `Frequency:NkHz` columns (plus Temperature /
	Humidity if the model was trained with them). A prediction needs `seq_len`
	consecutive rows, so the first seq_len-1 rows only build up history.

	Returns a JSON-serializable dict:
		{
		  "ok": true,
		  "seq_len": 10,
		  "n_features": 77,
		  "count": <number of predictions>,
		  "predictions": [{"index": i, "light_on": bool, "probability_on": float}, ...],
		  "current": {"light_on": bool, "probability_on": float}   // last window
		}
	On any failure it returns {"ok": false, "error": "<message>"} so the web page
	always receives structured JSON.
	"""
	try:
		import pandas as pd  # imported lazily so import errors surface as JSON

		state = _load(model_dir)
		meta, scaler, model = state["meta"], state["scaler"], state["model"]
		features, seq_len = meta["features"], meta["seq_len"]

		df = pd.read_csv(csv_path)

		missing = [c for c in features if c not in df.columns]
		if missing:
			return {"ok": False, "error": f"missing required columns: {missing}"}
		if len(df) < seq_len:
			return {"ok": False,
			        "error": f"need at least {seq_len} rows, got {len(df)}"}

		# rows in the exact trained feature order, scaled with the saved scaler
		X = scaler.transform(df[features].astype(float).values)

		# sliding windows -> [n_windows, seq_len, n_features]
		windows = np.stack([X[i:i + seq_len]
		                    for i in range(len(X) - seq_len + 1)])
		with torch.no_grad():
			probs = model(torch.tensor(windows, dtype=torch.float32)).numpy().flatten()

		predictions = []
		for offset, p in enumerate(probs):
			predictions.append({
				# index of the last row of the window (the moment predicted)
				"prediction": bool(p > threshold),
				"probability_on": round(float(p), 4),
			})

		return {
			"prediction": predictions[-1],
		}

	except Exception as e:
		return {"ok": False, "error": f"{type(e).__name__}: {e}"}


if __name__ == "__main__":
	import sys

	path = sys.argv[1] if len(sys.argv) > 1 else "input.csv"
	print(json.dumps(predict_csv(path), indent=2))
