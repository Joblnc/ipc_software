import os
import json
import joblib
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import TensorDataset, DataLoader
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import (
	confusion_matrix,
	precision_score,
	recall_score,
	f1_score,
	balanced_accuracy_score,
)

# ============================ CONFIG ============================
DATA_PATH = "../server/datas/data_13_06_2026.csv"
MODEL_PATH = "ipc_model.pth"
SCALER_PATH = "ipc_scaler.gz"
META_PATH = "ipc_meta.json"   # feature order + config, so inference matches training

# we save the splits too, so the exact train/val/test used can be inspected
TRAIN_PATH = "training_set.csv"
VAL_PATH = "validation_set.csv"
TEST_PATH = "test_set.csv"

SEQ_LEN = 10            # number of consecutive sweeps the LSTM looks at
TARGET = "Light"        # column we want to predict (light ON / OFF)

# The plant reacts to a light change with a lag: for ~40-80 sweeps after a
# toggle the frequency signature still looks like the previous state, so those
# rows are effectively mislabeled and unlearnable. We drop windows whose last
# row falls within SETTLE_ROWS of a toggle (a physical "dead-time"). In real
# use the light cycles are long, so we operate in the settled regime anyway.
SETTLE_ROWS = 40

# The goal is to detect the light *from the plant's frequency signature*.
# Temperature/Humidity are kept out by default: the light heats the room, so
# they would let the model cheat through temperature instead of learning the
# plant signal. Set to True to feed them in as extra features.
USE_ENV_FEATURES = False

# chronological split ratios (NOT random: see split_dataframe)
TRAIN_RATIO = 0.70
VAL_RATIO = 0.15
# the remaining 0.15 is the test set

SEED = 42


# ===================== REPRODUCIBILITY =========================
def set_seed(seed=SEED):
	np.random.seed(seed)
	torch.manual_seed(seed)


# ========================== CLEANING ===========================
def load_and_clean(path=DATA_PATH):
	"""Loads the raw collection CSV and returns a clean dataframe.

	- Light: bool/"True"/"False" -> int 0/1
	- Temperature/Humidity: the Tuya sensor sometimes returns nothing, leaving
	  holes. They change slowly, so we fill them forward then backward.
	- Frequencies are always present (the Arduino sweep never drops values).
	"""
	df = pd.read_csv(path)

	# normalize the label to 0/1 whatever its original type (bool or string)
	df[TARGET] = (
		df[TARGET].astype(str).str.strip().str.lower().map({"true": 1, "false": 0})
	)
	if df[TARGET].isna().any():
		raise ValueError("Some Light values could not be parsed to 0/1")
	df[TARGET] = df[TARGET].astype(int)

	# fill the slow environmental sensors, then drop anything still empty
	for col in ("Temperature", "Humidity"):
		if col in df.columns:
			df[col] = df[col].ffill().bfill()

	before = len(df)
	df = df.dropna().reset_index(drop=True)
	if len(df) != before:
		print(f"Dropped {before - len(df)} rows that were still incomplete")

	return df


def feature_columns(df):
	# everything except the label, minus the environmental columns when disabled.
	# columns starting with "_" are bookkeeping (e.g. _since_toggle), never features.
	drop = [TARGET]
	if not USE_ENV_FEATURES:
		drop += [c for c in ("Temperature", "Humidity") if c in df.columns]
	return [c for c in df.columns if c not in drop and not c.startswith("_")]


def rows_since_toggle(labels):
	"""For each row, how many rows since the last label change (0 right at a toggle).

	Computed on the full chronological series so the count stays correct across
	the train/val/test cut points.
	"""
	labels = np.asarray(labels)
	since = np.zeros(len(labels), dtype=int)
	for i in range(1, len(labels)):
		since[i] = 0 if labels[i] != labels[i - 1] else since[i - 1] + 1
	return since


# ===================== CHRONOLOGICAL SPLIT =====================
def split_dataframe(df):
	"""Splits by time, not by random rows.

	The light is toggled in long cycles (~220 identical-label rows in a row).
	A random row split would put almost-identical neighbouring rows in both
	train and test and leak the answer. Cutting the timeline into three
	contiguous blocks keeps train/val/test independent. Each block still spans
	many ON/OFF cycles, so both classes stay well represented.
	"""
	n = len(df)
	train_end = int(n * TRAIN_RATIO)
	val_end = int(n * (TRAIN_RATIO + VAL_RATIO))

	train_df = df.iloc[:train_end].reset_index(drop=True)
	val_df = df.iloc[train_end:val_end].reset_index(drop=True)
	test_df = df.iloc[val_end:].reset_index(drop=True)

	train_df.to_csv(TRAIN_PATH, index=False)
	val_df.to_csv(VAL_PATH, index=False)
	test_df.to_csv(TEST_PATH, index=False)

	def balance(d):
		return d[TARGET].value_counts(normalize=True).round(2).to_dict()

	print(f"Split -> train {len(train_df)} {balance(train_df)} | "
	      f"val {len(val_df)} {balance(val_df)} | "
	      f"test {len(test_df)} {balance(test_df)}")
	return train_df, val_df, test_df


def create_sequences(X_data, y_data, since=None, seq_length=SEQ_LEN):
	"""Sliding windows of `seq_length` consecutive rows.

	The label of a window is the label of its last row (the present moment).
	Built inside a single split only, so no window ever crosses a split border.
	When `since` is given, windows whose last row sits within SETTLE_ROWS of a
	toggle are skipped (the plant has not reacted yet -> unreliable label).
	"""
	X_seq, y_seq = [], []
	for i in range(len(X_data) - seq_length + 1):
		last = i + seq_length - 1
		if since is not None and since[last] < SETTLE_ROWS:
			continue
		X_seq.append(X_data[i : i + seq_length])
		y_seq.append(y_data[last])
	return np.array(X_seq), np.array(y_seq)


def build_tensors(df, feat_cols, scaler, fit):
	X_raw = df[feat_cols].values
	y_raw = df[TARGET].astype(int).values
	since = df["_since_toggle"].values if "_since_toggle" in df.columns else None
	# scaler is fit on TRAIN only, then reused (transform) on val/test
	X_scaled = scaler.fit_transform(X_raw) if fit else scaler.transform(X_raw)
	X_seq, y_seq = create_sequences(X_scaled, y_raw, since)
	X = torch.tensor(X_seq, dtype=torch.float32)
	y = torch.tensor(y_seq, dtype=torch.float32).view(-1, 1)
	return X, y


# ====================== LSTM MODEL =============================
class MyIPCLSTM(nn.Module):
	def __init__(self, input_size, hidden_size=32, num_layers=1):
		super(MyIPCLSTM, self).__init__()
		# the lstm reads the sequence; hidden_size is its "memory width"
		self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)
		# a linear layer turns the final memory into a single score
		self.fc = nn.Linear(hidden_size, 1)

	def forward(self, x):
		out, (h_n, c_n) = self.lstm(x)
		# only the last time step matters for a single global prediction
		last_out = out[:, -1, :]
		# sigmoid -> probability that the light is ON
		return torch.sigmoid(self.fc(last_out))


# ========================= TRAINING ===========================
def train_model(model, X_train, y_train, X_val, y_val,
                epochs=100, patience=10, batch_size=32, lr=0.001):
	train_loader = DataLoader(
		TensorDataset(X_train, y_train), batch_size=batch_size, shuffle=True
	)

	criterion = nn.BCELoss()
	optimizer = optim.Adam(model.parameters(), lr=lr)

	best_val_loss = float("inf")
	epochs_no_improve = 0

	print(f"Training on X{tuple(X_train.shape)} ...")
	for epoch in range(epochs):
		model.train()
		train_loss = 0.0
		for batch_X, batch_y in train_loader:
			optimizer.zero_grad()
			preds = model(batch_X)
			loss = criterion(preds, batch_y)
			loss.backward()
			optimizer.step()
			train_loss += loss.item() * batch_X.size(0)
		train_loss /= len(train_loader.dataset)

		# validation pass for early stopping
		model.eval()
		with torch.no_grad():
			val_loss = criterion(model(X_val), y_val).item()

		if val_loss < best_val_loss:
			best_val_loss = val_loss
			epochs_no_improve = 0
			torch.save(model.state_dict(), MODEL_PATH)  # keep the best model
		else:
			epochs_no_improve += 1
			if epochs_no_improve >= patience:
				print(f"Early stopping at epoch {epoch+1} "
				      f"(best val loss {best_val_loss:.4f})")
				break

		if (epoch + 1) % 10 == 0:
			print(f"Epoch {epoch+1:02d}/{epochs} - "
			      f"train {train_loss:.4f} - val {val_loss:.4f}")

	# reload the best checkpoint before returning
	model.load_state_dict(torch.load(MODEL_PATH, weights_only=True))
	print("Training finished, best model reloaded.")


# ========================= EVALUATION =========================
def evaluate(model, X_test, y_test):
	model.eval()
	with torch.no_grad():
		probs = model(X_test).numpy().flatten()
	y_pred = (probs > 0.5).astype(int)
	y_true = y_test.numpy().flatten().astype(int)

	acc = (y_pred == y_true).mean() * 100
	bal = balanced_accuracy_score(y_true, y_pred) * 100
	cm = confusion_matrix(y_true, y_pred)
	prec = precision_score(y_true, y_pred, zero_division=0)
	rec = recall_score(y_true, y_pred, zero_division=0)
	f1 = f1_score(y_true, y_pred, zero_division=0)

	print("\n========== Test set results ==========")
	print(f"Sequences tested : {len(y_true)}")
	print(f"Accuracy          : {acc:.2f}%")
	print(f"Balanced accuracy : {bal:.2f}%")
	print(f"Confusion matrix  : TN={cm[0,0]} FP={cm[0,1]} FN={cm[1,0]} TP={cm[1,1]}")
	print(f"ON precision/recall/F1 : {prec:.3f} / {rec:.3f} / {f1:.3f}")


# =========================== MAIN =============================
def main():
	set_seed()

	df = load_and_clean()
	feat_cols = feature_columns(df)
	print(f"{len(feat_cols)} features used "
	      f"({'with' if USE_ENV_FEATURES else 'without'} Temperature/Humidity)")

	# distance-to-toggle, computed on the full series before cutting the splits
	df["_since_toggle"] = rows_since_toggle(df[TARGET].values)
	print(f"Dead-time: dropping windows within {SETTLE_ROWS} rows of a toggle")

	train_df, val_df, test_df = split_dataframe(df)

	scaler = MinMaxScaler()
	X_train, y_train = build_tensors(train_df, feat_cols, scaler, fit=True)
	X_val, y_val = build_tensors(val_df, feat_cols, scaler, fit=False)
	X_test, y_test = build_tensors(test_df, feat_cols, scaler, fit=False)
	joblib.dump(scaler, SCALER_PATH)

	# persist the exact feature order + config so live inference is consistent
	with open(META_PATH, "w") as f:
		json.dump({
			"features": feat_cols,
			"seq_len": SEQ_LEN,
			"settle_rows": SETTLE_ROWS,
			"use_env_features": USE_ENV_FEATURES,
		}, f, indent=2)

	model = MyIPCLSTM(input_size=len(feat_cols))
	train_model(model, X_train, y_train, X_val, y_val)
	evaluate(model, X_test, y_test)

	print(f"\nSaved model -> {MODEL_PATH} | scaler -> {SCALER_PATH}")


if __name__ == "__main__":
	main()