import os
import sqlite3
import pandas as pd
import numpy as np
from flask import Flask, jsonify, request
from flask_cors import CORS
from sklearn.ensemble import RandomForestClassifier

app = Flask(__name__)
CORS(app)

DB_FILE = "trading_data.db"
model = RandomForestClassifier(n_estimators=100, random_state=42)
is_model_trained = False

# Initialisation de la base de données
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS ticks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    ask REAL,
                    bid REAL,
                    high_prev REAL,
                    low_prev REAL,
                    spread REAL,
                    target INTEGER DEFAULT 0
                )''')
    conn.commit()
    conn.close()

init_db()

# Entraînement du modèle
def train_model():
    global model, is_model_trained
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT ask, bid, high_prev, low_prev, spread, target FROM ticks", conn)
    conn.close()

    # Se réentraîne s'il y a au moins 50 enregistrements et plus d'une classe disponible
    if len(df) >= 50 and df['target'].nunique() > 1:
        X = df[['ask', 'bid', 'high_prev', 'low_prev', 'spread']]
        y = df['target']
        model.fit(X, y)
        is_model_trained = True

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "online",
        "system": "MTSPRO_V3 AI Scalper",
        "model_trained": is_model_trained
    })

@app.route('/api/tick', methods=['POST'])
def process_tick():
    global is_model_trained
    data = request.get_json()

    if not data or 'ask' not in data or 'bid' not in data:
        return jsonify({"status": "error", "message": "Donnees incompletes"}), 400

    ask = float(data['ask'])
    bid = float(data['bid'])
    high_prev = float(data.get('high_prev', 0))
    low_prev = float(data.get('low_prev', 0))
    spread = ask - bid

    # Label basé sur la cassure du momentum
    target = 1 if (ask > high_prev and high_prev > 0) else (2 if (bid < low_prev and low_prev > 0) else 0)

    # Stockage en base de données
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO ticks (ask, bid, high_prev, low_prev, spread, target) VALUES (?, ?, ?, ?, ?, ?)",
              (ask, bid, high_prev, low_prev, spread, target))
    conn.commit()
    conn.close()

    # Tentative d'entraînement
    try:
        train_model()
    except Exception:
        pass

    action = "NONE"

    # Prédiction avec l'IA
    if is_model_trained:
        features = pd.DataFrame([{
            'ask': ask,
            'bid': bid,
            'high_prev': high_prev,
            'low_prev': low_prev,
            'spread': spread
        }])
        pred = model.predict(features)[0]
        if pred == 1:
            action = "BUY"
        elif pred == 2:
            action = "SELL"
    else:
        # Stratégie de repli avant l'entraînement complet
        if ask >= high_prev and high_prev > 0:
            action = "BUY"
        elif bid <= low_prev and low_prev > 0:
            action = "SELL"

    return jsonify({
        "status": "success",
        "signal": {
            "action": action,
            "tp_points": 350.0,
            "sl_points": 150.0
        },
        "model_trained": is_model_trained
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
