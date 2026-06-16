"""Live light-state inference from the plant's frequency sweeps.

The model is trained on the 77 frequencies only (Temperature/Humidity are off
by default, see USE_ENV_FEATURES in ml_script.py). The exact feature list is
read from ipc_meta.json, so this file follows whatever the model was trained on.

Feeds the trained LSTM the same window shape it was trained on: the last
`seq_len` sweeps, each row in the exact feature order saved at training time,
scaled with the saved scaler -> tensor [1, seq_len, n_features] -> probability.

This module needs torch, so it runs in the machine_learning/.venv (Python 3.10),
NOT the server venv. See the bottom of the file and the README for how the
server can use it.
"""

import json
from collections import deque

import joblib
import numpy as np
import torch
import sys

from ml_script import MyIPCLSTM, MODEL_PATH, SCALER_PATH, META_PATH

# frequency column names in the exact order the Arduino sends a sweep
# (15-40 kHz then 180-230 kHz), matching the CSV header.
FREQ_NAMES = ([f"Frequency:{i}kHz" for i in range(15, 41)] +
              [f"Frequency:{i}kHz" for i in range(180, 231)])


class LightPredictor:
	"""Rolling-window predictor: push one sweep at a time, get ON/OFF out."""

	def __init__(self, model_path=MODEL_PATH, scaler_path=SCALER_PATH,
	             meta_path=META_PATH, threshold=0.5):
		with open(meta_path) as f:
			meta = json.load(f)
		self.features = meta["features"]          # exact training feature order
		self.seq_len = meta["seq_len"]
		self.settle_rows = meta["settle_rows"]

		self.scaler = joblib.load(scaler_path)
		self.model = MyIPCLSTM(input_size=len(self.features))
		self.model.load_state_dict(torch.load(model_path, weights_only=True))
		self.model.eval()

		self.threshold = threshold
		self.buffer = deque(maxlen=self.seq_len)
		# rows since the last known light toggle (caller signals via notify_toggle)
		self._since_toggle = self.settle_rows  # assume settled until told otherwise

	def notify_toggle(self):
		"""Call this whenever the light is switched, to arm the dead-time guard."""
		self._since_toggle = 0

	def _row(self, temperature, humidity, sweep):
		# assemble every possible input by name, then pick the trained order.
		# the model is frequency-only by default; Temperature/Humidity are only
		# read if the model was trained with them (USE_ENV_FEATURES).
		if len(sweep) != len(FREQ_NAMES):
			raise ValueError(f"expected {len(FREQ_NAMES)} frequencies, got {len(sweep)}")
		values = {"Temperature": temperature, "Humidity": humidity}
		values.update(zip(FREQ_NAMES, sweep))
		row = [values[name] for name in self.features]
		if any(v is None for v in row):
			missing = [n for n in self.features if values[n] is None]
			raise ValueError(f"model needs these features but they were not provided: {missing}")
		return row

	def push(self, sweep, temperature=None, humidity=None):
		"""Add one sweep (77 frequencies) and return a prediction dict, or None
		until the buffer holds `seq_len` sweeps.

		`temperature`/`humidity` are optional and only used if the model was
		trained with environmental features. Returns {"prob", "on", "settled"}
		where `settled` is False during the dead-time right after a toggle
		(prediction is unreliable there).
		"""
		self.buffer.append(self._row(temperature, humidity, sweep))
		self._since_toggle += 1

		if len(self.buffer) < self.seq_len:
			return None  # not enough history yet

		X = self.scaler.transform(np.array(self.buffer, dtype=float))
		x = torch.tensor(X, dtype=torch.float32).unsqueeze(0)  # [1, seq_len, n_feat]
		with torch.no_grad():
			prob = float(self.model(x).item())

		return {
			"prob": prob,
			"on": prob > self.threshold,
			"settled": self._since_toggle >= self.settle_rows,
		}


def predict_file(csv_path):
	"""Predict the light state for each row of an unlabeled CSV of sweeps.

	The file must hold consecutive sweeps with the 77 Frequency columns (plus
	Temperature/Humidity if the model was trained with them). Each prediction
	uses the row and the 9 sweeps before it, so the first 9 rows only build up
	history; give exactly 10 rows to get a single prediction on the last one.
	"""
	import pandas as pd

	df = pd.read_csv(csv_path)
	predictor = LightPredictor()

	# the model needs every trained feature to be present in the file
	missing = [c for c in predictor.features if c not in df.columns and c not in FREQ_NAMES]
	if missing:
		raise ValueError(f"input is missing required columns: {missing}")
	has_temp = "Temperature" in df.columns
	has_hum = "Humidity" in df.columns

	print(f"Predicting {len(df)} row(s) from {csv_path} "
	      f"(need {predictor.seq_len} consecutive sweeps per prediction)\n")
	for idx, r in df.iterrows():
		sweep = [r[name] for name in FREQ_NAMES]
		out = predictor.push(
			sweep,
			temperature=float(r["Temperature"]) if has_temp else None,
			humidity=float(r["Humidity"]) if has_hum else None,
		)
		if out is None:
			print(f"row {idx:>4} : (warming up {len(predictor.buffer)}/{predictor.seq_len})")
			continue
		state = "ON " if out["on"] else "OFF"
		print(f"row {idx:>4} : light {state}  (probability ON = {out['prob']*100:5.1f}%)")


if __name__ == "__main__":
	path = sys.argv[1] if len(sys.argv) > 1 else "input.csv"
	predict_file(path)