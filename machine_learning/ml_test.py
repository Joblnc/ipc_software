from machine_learning.ml_script import MyIPCLSTM, train_model, model_path, scaler_path
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import confusion_matrix, precision_score, recall_score, f1_score, balanced_accuracy_score

import torch
import os
import pandas as pd
import numpy as np
import joblib

from pathlib import Path

CURRENT_FOLDER = Path(__file__).parent

test_set_path = CURRENT_FOLDER / "test_set.csv"

def get_light_for_lines(df):
	X_raw = df.drop("Light", axis=1).values
	y_true_raw = df["Light"].values

	# 2. Normalisation avec le BON scaler de l'entraînement
	X_scaled = scaler.transform(X_raw)

	# 3. Création de TOUTES les fenêtres glissantes de 10 lignes possibles
	seq_len = 10
	X_sequences = []
	y_true_labels = []

	for i in range(len(X_scaled) - seq_len + 1):
		# On prend un bloc de 10 lignes pour l'IA
		X_sequences.append(X_scaled[i : i + seq_len])

		# La vraie réponse correspond à la dernière ligne de ce bloc
		y_true_labels.append(y_true_raw[i + seq_len - 1])

	# S'il n'y a pas assez de données pour faire au moins une séquence
	if len(X_sequences) == 0:
		print("❌ Pas assez de lignes dans le fichier pour créer une séquence de 10 !")
		return

	# Conversion en Tenseur PyTorch d'un coup !
	# La dimension finale sera [Nombre_de_tests, 10, 79]
	X_tensor = torch.tensor(np.array(X_sequences), dtype=torch.float32)

	# 4. Mode Évaluation et Inférence globale
	model.eval()
	with torch.no_grad():
		# L'IA traite TOUTES les fenêtres en une seule micro-seconde
		predictions_brutes = model(X_tensor)

	# Conversion des résultats PyTorch en tableaux Numpy plats
	probabilites = predictions_brutes.numpy().flatten()

	# Si probabilité > 0.5 -> l'IA dit 1 (Allumé), sinon 0 (Éteint)
	y_pred = (probabilites > 0.5).astype(int)
	y_true = np.array(y_true_labels).astype(int)

	# 5. Calcul de la performance (Accuracy)
	nb_correct = (y_pred == y_true).sum()
	total_tests = len(y_true)
	accuracy = (nb_correct / total_tests) * 100
	cm = confusion_matrix(y_true, y_pred)
	precision_on = precision_score(y_true, y_pred, zero_division=0)
	recall_on = recall_score(y_true, y_pred, zero_division=0)
	f1_on = f1_score(y_true, y_pred, zero_division=0)
	balanced_acc = balanced_accuracy_score(y_true, y_pred) * 100

	# print(f"\n=========================================")
	# print(f"📊 Test set results ")
	# print(f"=========================================")
	# print(f"▶️ Number of {seq_len}-row sequences tested : {total_tests}")
	# print(f"🎯 Model accuracy : {accuracy:.2f}%\n")
	# print(f"⚖️ Balanced accuracy : {balanced_acc:.2f}%")
	# print(f"🧮 Confusion matrix: TN={cm[0,0]} FP={cm[0,1]} FN={cm[1,0]} TP={cm[1,1]}")
	# print(f"🔎 ON precision/recall/F1 : {precision_on:.3f} / {recall_on:.3f} / {f1_on:.3f}\n")

	# print("Détail des 15 premiers tests :")
	# print("-" * 50)
	# for i in range(total_tests):
	# 	reel = "ALLUMÉE" if y_true[i] == 1 else "ÉTEINTE"
	# 	ia = "ALLUMÉE" if y_pred[i] == 1 else "ÉTEINTE"

	# 	# Calcul de la confiance réelle de son choix
	# 	confiance = probabilites[i] if y_pred[i] == 1 else (1 - probabilites[i])
	# 	statut = "✅" if y_pred[i] == y_true[i] else "❌"
	# 	print(f"Test {i+1:02d} -> {statut} Réel: {reel} | IA: {ia} (Confiance: {confiance*100:.1f}%)")


def get_light_for_one_line(df):
	X_raw = df.drop("Light", axis=1)[-10:].values
	y_true_raw = df["Light"][-10:].values

	# 2. Normalisation avec le BON scaler de l'entraînement
	X_scaled = scaler.transform(X_raw)

	# 3. Création de TOUTES les fenêtres glissantes de 10 lignes possibles
	seq_len = 10
	X_sequences = []
	y_true_labels = []

	for i in range(len(X_scaled) - seq_len + 1):
		# On prend un bloc de 10 lignes pour l'IA
		X_sequences.append(X_scaled[i : i + seq_len])

		# La vraie réponse correspond à la dernière ligne de ce bloc
		y_true_labels.append(y_true_raw[i + seq_len - 1])

	# S'il n'y a pas assez de données pour faire au moins une séquence
	if len(X_sequences) == 0:
		print("❌ Pas assez de lignes dans le fichier pour créer une séquence de 10 !")
		return

	# Conversion en Tenseur PyTorch d'un coup !
	# La dimension finale sera [Nombre_de_tests, 10, 79]
	X_tensor = torch.tensor(np.array(X_sequences), dtype=torch.float32)

	# 4. Mode Évaluation et Inférence globale
	model.eval()
	with torch.no_grad():
		# L'IA traite TOUTES les fenêtres en une seule micro-seconde
		predictions_brutes = model(X_tensor)

	# Conversion des résultats PyTorch en tableaux Numpy plats
	probabilites = predictions_brutes.numpy().flatten()

	# Si probabilité > 0.5 -> l'IA dit 1 (Allumé), sinon 0 (Éteint)
	y_pred = (probabilites > 0.5).astype(int)
	y_true = np.array(y_true_labels).astype(int)

	if y_true.size != 1 or y_pred.size != 1:
		print("❌ Something unexpected happened when making numpy arrays !")
		return
	
	return y_true[0], y_pred[0]

scaler = MinMaxScaler()
model = MyIPCLSTM()

if os.path.exists(model_path) and os.path.exists(scaler_path):
	print("found an exitsing model, loading it...")
	model.load_state_dict(torch.load(model_path, weights_only=True))
	scaler = joblib.load(scaler_path)
else:
	print("no pre existing model found, training a new one")
	train_model(model, scaler)
	model.load_state_dict(torch.load(model_path, weights_only=True))

#torch.save(model.state_dict(), model_path)

# TODO: to change when we have more test data
df = df = pd.read_csv(test_set_path)

get_light_for_lines(df)
