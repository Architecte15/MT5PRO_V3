import os
import sqlite3
import pandas as pd
from flask import Flask, jsonify, request
from flask_cors import CORS
from sklearn.ensemble import RandomForestClassifier

app = Flask(__name__)
CORS(app)

DB_FILE = "trading_data.db"
model = RandomForestClassifier(n_estimators=30, max_depth=5, random_state=42)
is_model_trained = False
last_price = 0.0

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS ticks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    ask REAL, bid REAL, spread REAL, tick_delta REAL, target INTEGER DEFAULT 0
                )''')
    conn.commit()
    conn.close()

init_db()

@app.route('/api/tick', methods=['POST'])
def process_tick():
    global is_model_trained, last_price
    data = request.get_json()

    if not data or 'ask' not in data or 'bid' not in data:
        return jsonify({"status": "error", "message": "Données incomplètes"}), 400

    ask = float(data['ask'])
    bid = float(data['bid'])
    spread = ask - bid
    mid_price = (ask + bid) / 2.0
    
    # Delta par rapport au dernier tick reçu
    tick_delta = mid_price - last_price if last_price > 0 else 0.0
    last_price = mid_price

    # Logique Agressive : si la variation de prix dépasse le spread, c'est une impulsion
    action = "NONE"
    
    # Seuil d'impulsion ultra-sensible (0.05$ sur l'Or)
    if tick_delta > (spread * 0.5):
        action = "BUY"
    elif tick_delta < -(spread * 0.5):
        action = "SELL"

    return jsonify({
        "status": "success",
        "signal": {
            "action": action,
            "tp_points": 100.0,  # 10 pips / 1$ sur XAUUSD
            "sl_points": 80.0   # SL serré pour couper direct
        },
        "tick_delta": round(tick_delta, 3)
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
