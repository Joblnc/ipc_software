import sys
import os
import pandas as pd
root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_path not in sys.path:
    sys.path.append(root_path)

from flask import Flask, jsonify, request, send_from_directory
from server.data_collection import toggle_light
from machine_learning.ml_test import get_light_for_one_line

app = Flask(__name__, static_folder=".", static_url_path="")


async def set_light_state(is_on):
    """Connect this to the relay, MQTT topic, or device command."""
    await toggle_light()
    return "set_light_state finished"
    
    


def make_estimation(payload):
    """Connect this to the estimation logic or model inference."""
    # make a ssh request to get some data. Idea : shell script 

    #false df, replace with result of the ssh request
    df = pd.read_csv("server/datas/data_09_06_2026.csv")
    return get_light_for_one_line(df)


def get_device_status():
    """Return the current hardware and application status."""
    raise NotImplementedError("Implement get_device_status() in your backend.")


@app.get("/")
def index():
    return send_from_directory(".", "index.html")


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "service": "Internet of plants backend"})


@app.get("/api/status")
def status():
    try:
        return jsonify(get_device_status())
    except NotImplementedError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 501


@app.post("/api/light")
async def light():
    payload = request.get_json(silent=True) or {}
    is_on = bool(payload.get("is_on", False))

    try:
        result = await set_light_state(is_on)
        print(result)
        return jsonify({"ok": True, "is_on": is_on, "result": result})
    except NotImplementedError as exc:
        return jsonify({"ok": False, "is_on": is_on, "message": str(exc)}), 501


@app.post("/api/estimate")
def estimate():
    payload = request.get_json(silent=True) or {}

    try:
        result = make_estimation(payload)
        light_results = [{'actual': int(result[0]), 'prediction' : int(result[1])}]
        print(light_results)
        return jsonify({"ok": True, "message": light_results})
    except NotImplementedError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 501


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)