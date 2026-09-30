import os
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Permet à l'interface Lovable de lire l'API

dernier_signal = {
    "action": "NONE",
    "tp_points": 350.0,
    "sl_points": 150.0
}

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "online",
        "system": "MTSPRO_V3 API",
        "message": "Serveur de trading actif"
    })

@app.route('/api/tick', methods=['POST'])
def process_tick():
    global dernier_signal
    data = request.get_json()

    if not data or 'ask' not in data or 'bid' not in data:
        return jsonify({"status": "error", "message": "Donnes incompletes"}), 400

    ask = float(data['ask'])
    bid = float(data['bid'])
    high_prev = float(data.get('high_prev', 0))
    low_prev = float(data.get('low_prev', 0))

    if ask > high_prev and high_prev > 0:
        dernier_signal["action"] = "BUY"
    elif bid < low_prev and low_prev > 0:
        dernier_signal["action"] = "SELL"
    else:
        dernier_signal["action"] = "NONE"

    return jsonify({"status": "success", "signal": dernier_signal})

@app.route('/api/signal', methods=['GET'])
def get_signal():
    return jsonify(dernier_signal)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
