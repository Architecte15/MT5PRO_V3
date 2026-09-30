
import pandas as pd

df = pd.read_csv("xauusd_1year.csv")
df["time"] = pd.to_datetime(df["time"])
df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()

capital_initial = 50.0
solde = capital_initial
sl_dist = 1.5
tp_dist = 3.0
pourcentage_risque = 0.05
risque_max_usd = 100.0
spread_cost = 0.20

trades = []
position = None

for i in range(50, len(df)):
    prix = df["close"].iloc[i]
    haut_prev = df["high"].iloc[i-1]
    bas_prev = df["low"].iloc[i-1]
    ema = df["ema50"].iloc[i]
    horodate = df["time"].iloc[i]
    heure = horodate.hour

    if solde <= 2.0:
        break

    if position is not None:
        if position["type"] == "BUY":
            if prix >= position["tp"]:
                gain = (position["risque"] * 2.0) - position["spread"]
                solde += gain
                trades.append({"resultat": "WIN", "pnl": gain})
                position = None
            elif prix <= position["sl"]:
                perte = position["risque"] + position["spread"]
                solde -= perte
                trades.append({"resultat": "LOSS", "pnl": -perte})
                position = None

        elif position["type"] == "SELL":
            if prix <= position["tp"]:
                gain = (position["risque"] * 2.0) - position["spread"]
                solde += gain
                trades.append({"resultat": "WIN", "pnl": gain})
                position = None
            elif prix >= position["sl"]:
                perte = position["risque"] + position["spread"]
                solde -= perte
                trades.append({"resultat": "LOSS", "pnl": -perte})
                position = None

    if position is None:
        if 8 <= heure <= 18:
            risque_actuel = min(solde * pourcentage_risque, risque_max_usd)
            if prix > haut_prev and prix > ema:
                position = {"type": "BUY", "sl": prix - sl_dist, "tp": prix + tp_dist, "risque": risque_actuel, "spread": spread_cost}
            elif prix < bas_prev and prix < ema:
                position = {"type": "SELL", "sl": prix + sl_dist, "tp": prix - tp_dist, "risque": risque_actuel, "spread": spread_cost}

