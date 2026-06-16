import sys
import os
root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_path not in sys.path:
    sys.path.append(root_path)

from flask import Flask, jsonify, request, send_from_directory
from server.data_collection import toggle_light, get_light_status

from predict_csv import predict_csv
from frequency_collector import collect_frequency_lines

app = Flask(__name__, static_folder=".", static_url_path="")

HERE = os.path.dirname(os.path.abspath(__file__))
# bundled sample used when no live collection is requested / possible
SAMPLE_CSV = os.path.join(HERE, "input.csv")
# where freshly collected sweeps are written before being fed to the model
LIVE_CSV = os.path.join(HERE, "live_input.csv")


async def set_light_state(is_on):
    """Connect this to the relay, MQTT topic, or device command."""
    await toggle_light()
    return "set_light_state finished"
    
    


def make_estimation(payload):
    """Collect frequency sweeps live from the Arduino and predict the light state.

    Data source:
      - by default        : collect fresh sweeps from the Arduino (live)
      - payload["csv"]     : an explicit CSV path (skips collection, for testing)
      - payload["sample"]  : True -> use the bundled input.csv (offline demo)

    Returns the predictor's dict: {"prediction": bool, "probability_on": float}
    or {"ok": False, "error": ...} on failure.
    """
    if payload.get("csv"):
        return predict_csv(payload["csv"])
    if payload.get("sample"):
        return predict_csv(SAMPLE_CSV)

    # collect at least seq_len sweeps (the model's window) live from the Arduino,
    # save them, then run the model on them
    num_lines = max(int(payload.get("num_lines", 10)), 10)
    df = collect_frequency_lines(
        num_lines=num_lines,
        timeout=float(payload.get("timeout", 30.0)),
    )
    df.to_csv(LIVE_CSV, index=False)
    return predict_csv(LIVE_CSV)


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
async def estimate():
    payload = request.get_json(silent=True) or {}

    try:
        result = make_estimation(payload)
    except Exception as exc:  # collection / IO failures
        return jsonify({"ok": False, "message": str(exc)}), 500

    # the predictor signals failure with an "error" key instead of a prediction
    if "error" in result:
        return jsonify({"ok": False, "message": result["error"]}), 500

    # the real light state from the lamp (None if it can't be reached)
    actual = await get_light_status()

    light_results = [{
        "prediction": int(bool(result["prediction"])),
        "actual": int(bool(actual)) if actual is not None else None,
        "probability_on": result.get("probability_on"),
    }]
    print(light_results)
    return jsonify({"ok": True, "message": light_results})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)