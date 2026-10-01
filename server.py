import os
import sqlite3
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DB_FILE = "trading_data.db"
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

# --- ROUTE RACINE (Pour vérifier que le serveur marche dans le navigateur) ---
@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "online",
        "message": "Serveur de Scalping XAUUSD opérationnel !",
        "endpoint": "/api/tick"
    }), 200

# --- ROUTE DU BOT MT5 ---
@app.route('/api/tick', methods=['POST'])
def process_tick():
    global last_price
    
    # Accepte le format JSON classique ou les données nettoyées
    data = request.get_json(silent=True) or {}

    if 'ask' not in data or 'bid' not in data:
        return jsonify({"status": "error", "message": "Données ask/bid manquantes"}), 400

    ask = float(data['ask'])
    bid = float(data['bid'])
    spread = ask - bid
    mid_price = (ask + bid) / 2.0
    
    # Calcul du delta par rapport au tick précédent
    tick_delta = mid_price - last_price if last_price > 0 else 0.0
    last_price = mid_price

    # Logique Agressive Micro-Scalping
    action = "NONE"
    
    # Déclenchement dès 0.05$ de mouvement
    if tick_delta > (spread * 0.5):
        action = "BUY"
    elif tick_delta < -(spread * 0.5):
        action = "SELL"

    return jsonify({
        "status": "success",
        "signal": {
            "action": action,
            "tp_points": 60.0,
            "sl_points": 50.0
        },
        "tick_delta": round(tick_delta, 3)
    }), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
