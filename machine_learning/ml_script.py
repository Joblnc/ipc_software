import torch
import joblib
import os
import torch.nn as nn
import torch.optim as optim
import pandas as pd
import numpy as np
from torch.utils.data import TensorDataset, DataLoader
from sklearn.preprocessing import MinMaxScaler
from sklearn.model_selection import train_test_split


# ============= Fictive DATA ====================
# Imaginons que l'on a 100 exemples (batch=100)
# Chaque exemple contient une séquence de 10 étapes de temps (seq_len=10)
# À chaque étape, on a 79 seule valeur/feature (input_size=79) : temp, hum, + 77 fréquences
# X = torch.randn(100, 10, 79)


# Les valeurs que le modèle doit essayer de prédire (100 résultats)
# 0 ou 1, en float pour les calculs de pytorch
# y = torch.randint(0, 2, (100, 1)).float()


model_path = "ipc_model.pth"
scaler_path = "ipc_scaler.gz"


# ========== LSTM MODEL DEFINITION ===================
class MyIPCLSTM(nn.Module):
	def __init__(self, input_size=79, hidden_size=32, num_layers=1):
		super(MyIPCLSTM, self).__init__()

		# the lstm layer : hidden_size is the level of intelligence of the lstm
		self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)

		# a linear layer, to transform the hidden_size (64) into one guess
		self.fc = nn.Linear(hidden_size, 1)

	def forward(self, x):
		# goes through the lstm; out contains guesses for each temporal step
		# (h_n, c_n) is the state of the final memory
		out, (h_n, c_n) = self.lstm(x)

		# for a global prediction, we only care about the last guess
		derniere_sortie = out[:, -1, :]

		# puts this guess into the linear layer, to have the final guess
		prediction = torch.sigmoid(self.fc(derniere_sortie))
		return prediction


def train_model(model, scaler):
	# ============== REAL DATA ====================
	train_df = pd.read_csv("./training_set.csv").ffill().bfill()
	val_df = pd.read_csv("./validation_set.csv").ffill().bfill()
	seq_len = 10
	
	
	if len(train_df) < seq_len or len(val_df) < seq_len:
		raise ValueError("The train/validation CSVs are too small for a 10-step LSTM window")

	# gets input variables, and output variable (light)
	X_train_raw = train_df.drop("Light", axis=1).values
	y_train_raw = train_df["Light"].astype(int).values
	X_val_raw = val_df.drop("Light", axis=1).values
	y_val_raw = val_df["Light"].astype(int).values

	# normalizes input variables using train-only statistics
	X_train_scaled = scaler.fit_transform(X_train_raw)
	X_val_scaled = scaler.transform(X_val_raw)
	joblib.dump(scaler, "ipc_scaler.gz")

	def create_sequences(X_data, y_data, seq_length):
		# creates the sequences for the lstm to be able to watch backwards
		X_seq = []
		y_seq = []

		# stops before end to avoid index error
		for i in range(len(X_data) - seq_length + 1):
			# watches seq_length consecutive lines
			X_seq.append(X_data[i : i + seq_length])

			# the guess to make : the label at the line right after the lines we watched
			y_seq.append(y_data[i + seq_length - 1])

		return np.array(X_seq), np.array(y_seq)

	X_train_numpy, y_train_numpy = create_sequences(X_train_scaled, y_train_raw, seq_len)
	X_val_numpy, y_val_numpy = create_sequences(X_val_scaled, y_val_raw, seq_len)

	# converts numpy arrays into tensors usable by pytorch
	X_tensor = torch.tensor(X_train_numpy, dtype=torch.float32)

	# use of .view(-1, 1) : trick to have y as [N, 1] instead of [N]
	y_tensor = torch.tensor(y_train_numpy, dtype=torch.float32).view(-1, 1)
	X_val_tensor = torch.tensor(X_val_numpy, dtype=torch.float32)
	y_val_tensor = torch.tensor(y_val_numpy, dtype=torch.float32).view(-1, 1)

	# converts again in tensors
	train_dataset = TensorDataset(X_tensor, y_tensor)

	# train loader to make small batches
	train_loader = DataLoader(train_dataset, batch_size=32, shuffle=True)

	# TODO : remove for final product
	print("--- Dimensions checks ---")
	print(f"X shape : {X_tensor.shape}")
	print(f"y shape : {y_tensor.shape}")

	# =============== TRAINING PREPARATION ======================
	# Loss function : Binary Cross Entropy, because the output is boolean
	criterion = nn.BCELoss()

	# Optimizer, to update weights at each itearation (Adam is the most standard)
	optimizer = optim.Adam(model.parameters(), lr=0.001)

	# variables for early stopping
	patience = 10
	best_val_loss = float("inf")
	train_loss_at_best_val = float("inf")
	epochs_no_improve = 0

	# ================ TRAINING LOOP ========================
	epochs = 100 # numbers of times it looks at the whole data

	print("Training beginning...")
	for epoch in range(epochs):
		model.train() # Puts the model in training mode
		train_loss = 0.0

		# iterates over the different batches
		for batch_X, batch_y in train_loader:
			# Resets gradients to 0 (gradients are the calculs of the previous step)
			optimizer.zero_grad()

			# makes a forward pass, so a guess
			predictions = model(batch_X)

			# calculates the error between guess and actual value
			loss = criterion(predictions, batch_y)

			# calculates how to update the weights, with a backpropagation
			loss.backward()

			# updates the weigths
			optimizer.step()

			# updates the train loss
			train_loss += loss.item() * batch_X.size(0)

		# averages the train loss
		train_loss /= len(train_loader.dataset)

		# checks how the model behaves on validation set
		model.eval()
		with torch.no_grad():
			val_preds = model(torch.tensor(X_val_tensor))
			val_loss = criterion(val_preds, torch.tensor(y_val_tensor)).item()

			if val_loss < best_val_loss:
				# updates the model, saves it
				best_val_loss = val_loss
				train_loss_at_best_val = train_loss
				epochs_no_improve = 0
				torch.save(model.state_dict(), model_path)
			else:
				epochs_no_improve += 1

				if epochs_no_improve >= patience:
					print(f"\nEarly stopping triggered at epoch : {epoch+1} - Best epoch : {epoch - patience + 1}")
					print(f"Epoch {epoch - patience + 1:02d}/{epochs} - Train Loss: {train_loss_at_best_val:.4f} - Validation Loss: {best_val_loss:.4f}")
					return # On casse la boucle for, l'entraînement s'arrête !

		# every twenty epochs, displays the error
		if (epoch + 1) % 20 == 0:
			print(f"Epoch {epoch+1:02d}/{epochs} - Train Loss: {train_loss:.4f} - Validation Loss: {val_loss:.4f}")

	print("Training finished !")


# new_model = MyIPCLSTM()
# new_scaler = MinMaxScaler()


# train_model(new_model, new_scaler)

