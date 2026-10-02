import os
import sqlite3
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DB_FILE = "trading_data.db"
last_prices = {}

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS ticks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    symbol TEXT,
                    ask REAL, bid REAL, spread REAL, tick_delta REAL, target INTEGER DEFAULT 0
                )''')
    conn.commit()
    conn.close()

init_db()

@app.route('/api/tick', methods=['POST'])
def process_tick():
    global last_prices
    
    data = request.get_json(silent=True) or {}

    if 'ask' not in data or 'bid' not in data:
        return jsonify({"status": "error", "message": "Données ask/bid manquantes"}), 400

    # Symbole reçu de MT5 (ex: "XAUUSD.s" ou "XAUUSD.sc")
    symbol = data.get('symbol', 'XAUUSD')
    ask = float(data['ask'])
    bid = float(data['bid'])
    spread = ask - bid
    mid_price = (ask + bid) / 2.0
    
    prev_price = last_prices.get(symbol, 0.0)
    tick_delta = mid_price - prev_price if prev_price > 0 else 0.0
    
    last_prices[symbol] = mid_price

    action = "NONE"
    
    if prev_price > 0:
        if tick_delta > (spread * 0.5):
            action = "BUY"
        elif tick_delta < -(spread * 0.5):
            action = "SELL"

    return jsonify({
        "status": "success",
        "signal": {
            "symbol": XAUUSD.sc XAUUSD.S,        # ✅ Nom exact du symbole précisé ici
            "action": action,
            "tp_points": 60.0,
            "sl_points": 50.0
        },
        "tick_delta": round(tick_delta, 3)
    }), 200
