
import pandas as pd

# 1. Chargement des données
df = pd.read_csv("xauusd_1year.csv")
df["time"] = pd.to_datetime(df["time"])
df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
df["mois"] = df["time"].dt.to_period("M")

capital_initial = 50.0
solde = capital_initial
peak = capital_initial
max_drawdown = 0.0

sl_dist = 1.5
tp_dist = 3.0
pourcentage_risque = 0.05
risque_max_usd = 100.0
spread_cost = 0.20

trades = []
position = None
pertes_consecutives = 0
max_pertes_consecutives = 0

for i in range(50, len(df)):
    prix = df["close"].iloc[i]
    haut_prev = df["high"].iloc[i-1]
    bas_prev = df["low"].iloc[i-1]
    ema = df["ema50"].iloc[i]
    horodate = df["time"].iloc[i]
    heure = horodate.hour
    mois_actuel = df["mois"].iloc[i]

    if solde <= 2.0:
        print(f"COMPTE LIQUIDE le {horodate} - Solde : {solde:.2f} USD")
        break

    if solde > peak:
        peak = solde
    dd = (peak - solde) / peak * 100
    if dd > max_drawdown:
        max_drawdown = dd

    if position is not None:
        if position["type"] == "BUY":
            if prix >= position["tp"]:
                gain = (position["risque"] * 2.0) - position["spread"]
                solde += gain
                pertes_consecutives = 0
                trades.append({"date": horodate, "mois": mois_actuel, "resultat": "WIN", "pnl": gain, "solde": solde})
                position = None
            elif prix <= position["sl"]:
                perte = position["risque"] + position["spread"]
                solde -= perte
                pertes_consecutives += 1
                if pertes_consecutives > max_pertes_consecutives:
                    max_pertes_consecutives = pertes_consecutives
                trades.append({"date": horodate, "mois": mois_actuel, "resultat": "LOSS", "pnl": -perte, "solde": solde})
                position = None

        elif position["type"] == "SELL":
            if prix <= position["tp"]:
                gain = (position["risque"] * 2.0) - position["spread"]
                solde += gain
                pertes_consecutives = 0
                trades.append({"date": horodate, "mois": mois_actuel, "resultat": "WIN", "pnl": gain, "solde": solde})
                position = None
            elif prix >= position["sl"]:
                perte = position["risque"] + position["spread"]
                solde -= perte
                pertes_consecutives += 1
                if pertes_consecutives > max_pertes_consecutives:
                    max_pertes_consecutives = pertes_consecutives
                trades.append({"date": horodate, "mois": mois_actuel, "resultat": "LOSS", "pnl": -perte, "solde": solde})
                position = None

    if position is None:
        if 8 <= heure <= 18:
            risque_actuel = min(solde * pourcentage_risque, risque_max_usd)
            if prix > haut_prev and prix > ema:
                position = {"type": "BUY", "sl": prix - sl_dist, "tp": prix + tp_dist, "risque": risque_actuel, "spread": spread_cost}
            elif prix < bas_prev and prix < ema:
                position = {"type": "SELL", "sl": prix + sl_dist, "tp": prix - tp_dist, "risque": risque_actuel, "spread": spread_cost}

df_trades = pd.DataFrame(trades)
wins = df_trades[df_trades["resultat"] == "WIN"]
losses = df_trades[df_trades["resultat"] == "LOSS"]

print("\n================ RAPPORT DE BACKTEST DÉTAILLÉ ================")
print(f"Capital Initial            : {capital_initial:.2f} USD")
print(f"Solde Final                : {solde:.2f} USD")
print(f"Profit Net                 : {solde - capital_initial:+.2f} USD")
print(f"Drawdown Maximum           : {max_drawdown:.2f}%")
print(f"Pertes Consecutives Max    : {max_pertes_consecutives} trades d affilee")
print(f"Win Rate Global            : {(len(wins)/len(df_trades)*100):.2f}% ({len(wins)}V / {len(losses)}P)")
print("---------------------------------------------------------------")
print("PERFORMANCES MOIS PAR MOIS :")

if not df_trades.empty:
    group_mois = df_trades.groupby("mois")
    for mois, group in group_mois:
        pnl_mois = group["pnl"].sum()
        trades_mois = len(group)
        wins_mois = len(group[group["resultat"] == "WIN"])
        wr_mois = (wins_mois / trades_mois * 100) if trades_mois > 0 else 0
        solde_fin_mois = group["solde"].iloc[-1]
        print(f"  Mois {mois} : PnL = {pnl_mois:+8.2f} USD | Trades = {trades_mois:3d} | WinRate = {wr_mois:5.1f}% | Solde = {solde_fin_mois:8.2f} USD")

print("===============================================================")

