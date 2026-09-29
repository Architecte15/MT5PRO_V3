# Python Trading Engine v0.4 — Broker Realistic + Liquidity Flow

Moteur de trading Python modulaire avec backtest causal, simulation broker-réaliste, paper trading et adaptateur MetaTrader 5. Le modèle **Liquidity Flow** reste expérimental et n'est jamais promu automatiquement en live.

## Corrections critiques conservées

- `lookback_bars` pour rendre le retest réellement atteignable.
- `_filling_mode(symbol)` pour respecter les capacités MT5 (FOK/IOC/RETURN).
- `symbol_select(symbol, True)` avant les appels de données MT5.
- backend matplotlib `Agg`.
- fenêtre glissante de 800 bougies.
- alignement HTF uniquement avec bougies dont la clôture est disponible.
- validation anti-biais du SL : BUY `SL < Entry`, SELL `SL > Entry`.
- score minimum piloté par la configuration.

## Résolution des contraintes du petit compte

Le projet distingue désormais deux objectifs :

### `broker_realistic`

Simulation des contraintes d'un compte broker :

- capital initial configurable (17,65 USD par défaut) ;
- levier 1:100 par défaut ;
- EURUSD ;
- FOK requis par défaut ;
- volume minimum 0,01 ;
- volume step 0,01 ;
- marge disponible ;
- une seule position simultanée par défaut ;
- sizing fondé sur le risque **et** plafonné par la marge ;
- coûts de commission/slippage configurables ;
- P&L en USD, unités de prix et pips ;
- drawdown en USD et en pourcentage.

Si le volume calculé est inférieur au minimum broker, le moteur peut utiliser le volume minimum **uniquement** si son risque reste sous `max_min_volume_risk_percent`. Sinon l'ordre est rejeté proprement.

### `research_unconstrained`

Mode de recherche permettant d'étudier l'edge sans imposer la limite d'une seule position ou du capital de démonstration. Il ne représente pas une capacité d'exécution réelle.

## Circuit breaker

Après une série de pertes :

1. risque réduit progressivement ;
2. plancher de multiplicateur configurable ;
3. pause après le seuil de pertes consécutives ;
4. cooldown en nombre de bougies.

Le système ne fait jamais de martingale automatique.

## Backtest

Compte réaliste :

```bash
python -m app.main --mode backtest \
  --data backtests/datasets/EURUSD_M15.csv \
  --htf-data backtests/datasets/EURUSD_H4.csv \
  --backtest-profile broker_realistic \
  --starting-equity 17.65
```

Recherche :

```bash
python -m app.main --mode backtest \
  --data backtests/datasets/EURUSD_M15.csv \
  --htf-data backtests/datasets/EURUSD_H4.csv \
  --backtest-profile research_unconstrained \
  --starting-equity 10000
```

Les rapports sont écrits dans `backtests/reports/`.

## Liquidity Flow

Pipeline expérimental :

```text
MARKET DATA
    ↓
FEATURE EXTRACTION
    ↓
SWEEP / DISPLACEMENT / BOS / EMA13
    ↓
OUTCOME LABEL
    ↓
TRAIN → VALIDATION → OOS → FINAL HOLDOUT
    ↓
95% CI + contrôles
    ↓
EDGE_FOUND / EDGE_NOT_FOUND / EDGE_NOT_ENOUGH_EVIDENCE
```

Exécution :

```bash
python -m scripts.liquidity_flow_research \
  --data backtests/datasets/EURUSD_M15.csv
```

Un résultat positif sur TRAIN seul ne suffit jamais à promouvoir le modèle. Le holdout final reste intouché jusqu'à la validation.

## Configuration et live

Validation générale :

```bash
python -m scripts.validate_config
```

Validation live explicite :

```bash
python -m scripts.validate_config --live
```

Le mode live reste séparé et exige les variables `.env` :

```text
MT5_LOGIN=
MT5_PASSWORD=
MT5_SERVER=
TRADING_MODE=live
TRADING_SYMBOL=EURUSD
```

Aucun identifiant réel ne doit être placé dans Git.

## Reproductibilité Git

Le projet est maintenant conçu pour être versionné :

```bash
git init
git add .
git commit -m "Baseline Python trading engine v0.4"
```

Les tests sentinelles détectent notamment la disparition de `lookback_bars`, `_filling_mode`, `symbol_select`, `Agg`, de la fenêtre 800 et des protections SL.

## Tests

```bash
pytest -q
```

Le pipeline doit conserver les propriétés suivantes avant toute nouvelle réécriture : anti-lookahead, retest atteignable, filling mode dynamique, sélection MT5 du symbole, SL valide et backtest causal.

## Protection d'exécution live — anti-doublon / anti-hedging

Le moteur applique désormais un garde-fou cross-processus avant chaque entrée :

- verrou atomique par symbole via SQLite (`runtime/execution_guard.sqlite3`) ;
- fingerprint unique `symbol + candle clôturée + direction + strategy_id` ;
- resynchronisation MT5 après acquisition du verrou et après exécution ;
- `max_positions_per_symbol: 1` par défaut ;
- hedging et entrée opposée désactivés par défaut ;
- cooldown après exécution ;
- récupération des verrous périmés après un crash.

Cela protège également le cas où deux instances du bot tournent simultanément : un simple contrôle `get_positions()` n'est pas suffisant car les deux processus peuvent lire zéro position avant d'envoyer chacun un ordre. Le verrou SQLite sérialise l'étape critique.

Les paramètres sont dans `execution:`. Les identifiants MT5 restent uniquement dans `.env` et ne doivent jamais être commités.

## Stratégie expérimentale First H4 Range → M5 Re-entry

Une seconde stratégie expérimentale a été ajoutée à partir du cahier des charges fourni : elle construit, pour chaque journée en heure de New York, la plage du **premier chandelier H4**, attend sa clôture complète, puis surveille les clôtures M5.

Séquence causale :

1. premier H4 de la journée clôturé → `Range High / Range Low` ;
2. clôture M5 au-dessus du `Range High` ou sous le `Range Low` ;
3. clôture M5 ultérieure de réintégration dans la plage ;
4. entrée à l'ouverture de la bougie M5 suivante ;
5. SELL après sweep du High, BUY après sweep du Low ;
6. SL sur l'extrême du mouvement de cassure ; fallback structurel optionnel si le SL dépasse `max_sl_points` ;
7. TP fixe à 2R.

Les mèches seules ne valident pas la cassure. Plusieurs configurations peuvent être prises dans la même journée si `allow_multiple_per_day=true`.

La stratégie est **research/paper-only** par défaut et ne modifie pas le moteur LIVE. Les performances présentées dans la source utilisateur ne sont pas considérées comme validées par le projet : elles doivent être reproduites sur des données historiques avec séparation temporelle et coûts d'exécution.

Exemple :

```bash
python -m app.main --mode range_backtest --data backtests/datasets/EURUSD_M5.csv --htf-data backtests/datasets/EURUSD_H4.csv
```

Rapports : `backtests/reports/range4h_trades.csv` et `backtests/reports/range4h_metrics.json`.


## Live DEMO MT5 — H4 Range / M5

Le mode `live` exécute réellement les ordres via `MT5Broker`, mais la configuration livrée impose par défaut un garde-fou **compte démo** (`MetaQuotes-Demo`). Les identifiants ne doivent jamais être placés dans le code. Utilisez `.env` :

```text
MT5_LOGIN=...
MT5_PASSWORD=...
MT5_SERVER=MetaQuotes-Demo
TRADING_SYMBOL=EURUSD
TRADING_MODE=live
MT5_EXPECTED_SERVER=MetaQuotes-Demo
```

Lancement continu sur le compte démo :

```bash
python -m scripts.run_live_demo --interval 5
```

Un cycle unique de diagnostic :

```bash
python -m scripts.run_live_demo --once
```

La stratégie live principale est `four_hour_range` : première H4 de la journée New York clôturée, breakout M5 confirmé par clôture, réintégration M5, puis entrée sur la nouvelle bougie. Après une configuration terminée, l'état revient en attente afin de pouvoir détecter une nouvelle opportunité au cours de la même journée. Le moteur n'attend donc pas une seule entrée quotidienne, mais ne déclenche que sur une nouvelle séquence causale breakout → re-entry.

Garde-fous live : une position EURUSD maximum, pas de hedging, pas d'entrée opposée tant qu'une position existe, déduplication par bougie/setup/direction, verrou inter-processus, délai minimal de 5 minutes entre trades remplis, maximum 12 trades par jour, contrôle de marge, spread, SL et capacité de remplissage broker.

## Adaptive Market Learning (v8)

Le moteur contient désormais une couche de **mémoire adaptative persistante**. Elle ne prétend pas prédire le marché et ne modifie pas une règle après un seul trade.

Pipeline :

```text
M5 closed candle
    ↓
Opportunity scan (trend / pullback / momentum)
    ↓
Context fingerprint
    ↓
Entry + snapshot des features
    ↓
Position MT5
    ↓
Position close / TP / SL
    ↓
Outcome réel (profit + coûts disponibles)
    ↓
Bayesian/Jeffreys posterior par contexte
    ↓
Risk multiplier adaptatif
    ↓
Nouvelles décisions
```

La mémoire est stockée dans `runtime/adaptive_memory.sqlite3`. Un contexte n'est appris qu'après clôture du trade. Le modèle utilise une borne de confiance et un minimum d'observations ; il ne transforme donc pas une perte isolée en changement de stratégie.

### Opportunités adaptatives

Si la stratégie H4 Range/M5 ou le moteur principal ne confirme pas de setup, le scanner adaptatif peut rechercher une configuration M5 indépendante :

- tendance HTF alignée ;
- tendance EMA13/EMA50 cohérente ;
- pullback vers EMA13 ;
- bougie de reprise directionnelle ;
- cassure du high/low de la bougie précédente ;
- momentum minimal mesuré par ATR ;
- structure cohérente.

Le scanner examine BUY et SELL à chaque nouvelle bougie M5 clôturée. Il ne force toutefois jamais un ordre lorsqu'aucune configuration ne satisfait les critères.

### Apprentissage après chaque trade

Pour chaque position suivie, le bot conserve notamment :

- direction ;
- régime ;
- session ;
- alignement HTF ;
- type de pullback ;
- momentum ;
- volatilité ;
- position par rapport à EMA13 ;
- biais structurel ;
- entry / SL / TP.

Après la clôture, il ajoute le P&L et le résultat au contexte historique. Le risque peut alors être réduit pour les contextes historiquement faibles et restauré progressivement pour les contextes suffisamment documentés.

### Principe de sécurité

Le modèle adaptatif est **borné** : il ne peut pas augmenter le risque au-dessus du risque de base. Une nouvelle version de modèle doit être validée séparément avant toute modification structurelle des règles de trading.


## Major FX multi-symbol live/demo scanning

The live/demo runner can scan several major Forex pairs in the same MT5 session. Default symbols:
`EURUSD, GBPUSD, USDJPY, USDCHF, AUDUSD, USDCAD, NZDUSD`.

Override with `TRADING_SYMBOLS`, for example:
`TRADING_SYMBOLS=EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD,NZDUSD`

Each symbol gets its own strategy engine and broker-derived point size. A symbol unavailable in the terminal is skipped when `execution.skip_unavailable_symbols=true`; no synthetic order is created for unavailable symbols.
