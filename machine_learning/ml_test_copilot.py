from ml_script import MyIPCLSTM, train_model, model_path, scaler_path
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import confusion_matrix, precision_score, recall_score, f1_score, balanced_accuracy_score
import torch
import os
import pandas as pd
import numpy as np
import joblib

def get_light_for_line(df):
    X_raw = df.drop("Light", axis=1).values
    y_true_raw = df["Light"].astype(float).values

    # normalizes with the scaler used for training
    X_scaled = scaler.transform(X_raw)

    # preparation for sequences
    seq_len = 30
    X_sequences = []
    y_true_labels = []

    for i in range(len(X_scaled) - seq_len + 1):
        # takes 10 lines to look at
        X_sequences.append(X_scaled[i : i + seq_len])
        # takes the last line, which is the target
        y_true_labels.append(y_true_raw[i + seq_len - 1])

    # If not enough data for a sequence
    if len(X_sequences) == 0:
        print("❌ Not enough lines for a 10 lines sequence")
        return

    # Converts the sequence in a tensor PyTorch
    # final dimension is [nb_tests, 10, 79]
    X_tensor = torch.tensor(np.array(X_sequences), dtype=torch.float32)

    # indicates to not update any parameters with the tests
    model.eval()
    with torch.no_grad():
        # tests all sequences at once
        logits = model(X_tensor)
        predictions_brutes = torch.sigmoid(logits)

    # transforms pytorch in numpy, to be able to read it easily
    probabilites = predictions_brutes.numpy().flatten()
    
    # if proba > 0.5, predicted on, else off
    y_pred = (probabilites > 0.5).astype(int)
    y_true = np.array(y_true_labels).astype(int)

    # calculus of the accuracy of the model
    nb_correct = (y_pred == y_true).sum()
    total_tests = len(y_true)
    accuracy = (nb_correct / total_tests) * 100
    cm = confusion_matrix(y_true, y_pred)
    precision_on = precision_score(y_true, y_pred, zero_division=0)
    recall_on = recall_score(y_true, y_pred, zero_division=0)
    f1_on = f1_score(y_true, y_pred, zero_division=0)
    balanced_acc = balanced_accuracy_score(y_true, y_pred) * 100

    print(f"\n=========================================")
    print(f"📊 Test set results ")
    print(f"=========================================")
    print(f"▶️ Number of {seq_len}-row sequences tested : {total_tests}")
    print(f"🎯 Model accuracy : {accuracy:.2f}%\n")
    print(f"⚖️ Balanced accuracy : {balanced_acc:.2f}%")
    print(f"🧮 Confusion matrix: TN={cm[0,0]} FP={cm[0,1]} FN={cm[1,0]} TP={cm[1,1]}")
    print(f"🔎 ON precision/recall/F1 : {precision_on:.3f} / {recall_on:.3f} / {f1_on:.3f}\n")


    # Uncomment to see the details of the tests
    '''
    print("Details of the tests :")
    print("-" * 50)
    for i in range( total_tests):
        real = "ON" if y_true[i] == 1 else "OFF"
        ai = "ON" if y_pred[i] == 1 else "OFF"
        
        # calculates confidence
        confidence = probabilites[i] if y_pred[i] == 1 else (1 - probabilites[i])
        
        status = "✅" if y_pred[i] == y_true[i] else "❌"
        
        print(f"Test {i+1:02d} -> {status} real: {real} | AI: {ai} (Confidence: {confidence*100:.1f}%)")
    '''

# creates an empty model and an empty scaler
scaler = MinMaxScaler()
model = MyIPCLSTM()

# checks for existence of model or not. Loads existing one or train a new one
if os.path.exists(model_path) and os.path.exists(scaler_path):
    print("found an exitsing model, loading it...")
    model.load_state_dict(torch.load(model_path, weights_only=True))
    scaler = joblib.load(scaler_path)

else:
    print("no pre existing model found, training a new one")
    train_model(model, scaler)
    model.load_state_dict(torch.load(model_path, weights_only=True))


df = pd.read_csv("./test_set.csv").ffill().bfill()

get_light_for_line(df)