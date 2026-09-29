# Research : modèle « Liquidity Flow »

Banc de recherche **strictement parallèle** au moteur live. Rien dans `app/research/`
n'est importé par `app.main`, `TradingEngine` ou `SignalEngine`. Ce paquet ne peut pas
passer un ordre : il lit des CSV et écrit des rapports.

## Protocole (pré-enregistrement → validation)

1. **Pré-enregistrement** — `app/research/experiments.py` définit *avant toute mesure* :
   les hypothèses H1–H8, les ablations A1–A2, la grille de seuils `DISPLACEMENT_GRID`,
   la règle de sélection, les splits et la politique de verdict (`PROTOCOL`).
   Le runner en calcule un hash (`prereg_hash`) inscrit dans le rapport : un résultat
   ne peut pas modifier la question posée.
2. **Composants séparés** — sweep, displacement, structure (BOS/CHOCH), EMA13,
   liquidité HTF et alignement MTF sont portés par des champs distincts de chaque trade.
   Aucun score du type « sweep = +2 » n'existe.
3. **Splits chronologiques** — train 60 % / validation 20 % / OOS 10 % / holdout 10 %,
   découpés **dans le temps des trades** (jamais mélangés).
4. **Réglage limité au TRAIN** — la grille de displacement n'est évaluée que sur le
   train, avec une règle de sélection fixée à l'avance ; figée avant toute sortie
   sur validation/OOS/holdout.
5. **Walk-forward** — 4 plis expansifs (train initial 40 %, tests de 12,5 %),
   le dernier décile reste réservé au holdout.
6. **Contrôles** — `RANDOM_DIRECTION` (mêmes entrées, côté au hasard, stop ATR + 2R),
   `RANDOM_ELIGIBLE_ENTRY` (dates au hasard dans l'ensemble éligible, mêmes règles
   neutres) et, en référence informative, `BASELINE_CURRENT_ENGINE` (le moteur courant,
   filtres session/jour inclus).
7. **Verdict** — `EDGE NOT FOUND` si l'un des gate casse :
   - n(OOS) < 30,
   - IC95 de l'espérance OOS inclut 0,
   - PF(OOS) ≤ 1,
   - espérance(OOS) ≤ meilleur contrôle,
   - stabilité walk-forward < 75 % des plis.
   Sinon `CANDIDATE` — qui n'est **jamais** un déploiement : il exige la revue du
   holdout et une approbation manuelle (§12 : version de modèle, rollback possible).

## Exécution

```bash
python -m scripts.run_liquidity_research                 # run complet
python -m scripts.run_liquidity_research --control-draws 30   # smoke test
python -m scripts.run_liquidity_research --skip-dataset   # sans le dataset §11
python -m pytest tests/research -q                        # 48 tests unitaires
```

Sorties :

- `research/reports/liquidity_flow_report.json` — tout (machine-readable)
- `research/reports/liquidity_flow_report.md` — rapport lisible
- `research/reports/liquidity_trades_H*.csv` — trades auditables par hypothèse
- `research/reports/liquidity_sweeps.csv` — événements de sweep + contexte
- `research/datasets/observations_eurusd_m15.csv` — dataset d'observations §11
  (features + liquidité + régimes + labels futurs)

## Garde-fous anti-lookahead (vérifiés par tests)

- Une zone de liquidité n'existe qu'à partir de la clôture de sa barre confirmante
  (`available_at`), sur n'importe quel timeframe (M15 ou H4).
- Un signal naît d'une **barre fermée** ; le remplissage se fait à l'ouverture de la
  barre suivante.
- SL/TP : si les deux sont touchés dans la même barre → SL d'abord (convention
  conservative, identique au moteur backtest).
- « Bougie d'entrée » du modèle vidéo implémentée en `ENTRY_SIGNAL_CANDLE` = bougie de
  **signal** (fermée) — la bougie d'entrée réelle est inconnue à l'entrée.
- Un stop déjà franchi à l'ouverture d'entrée invalide le candidat (comme le moteur live).
- Alignement H4 : valeurs H4 uniquement si clôturées avant la décision M15, avec
  limite de fraîcheur 8 h.
- Labels futurs (`forward_labels`, MFE/MAE, hit_target/hit_stop) vivent dans
  `labels.py`/`dataset.py` et ne sont jamais joints aux features de décision.

## État / reporté (par contrôle, pas par oubli)

| Composant | État |
|---|---|
| H1–H8, A1–A2, splits, CI, walk-forward, contrôles, verdict | implémenté, testé |
| Dataset d'observations §11 | implémenté (CSV) |
| Multi-TF M5/H1 (§6) | **reporté** : nécessite une connexion MT5 — or la boucle live détient le terminal (connexion exclusive). Données H4 utilisées comme HTF. |
| PARTIAL_1R / RUNNER_TO_LIQUIDITY (§10) | reporté (sorties FIXED_RR, OPPOSITE_LIQUIDITY, TIME_EXIT testées) |
| Memory / similarité (§14), drift (§16), online learning (§15), registre de modèles (§12) | reportés — le spec impose une promotion contrôlée ; implémenter un sous-ensemble naïf donnerait une fausse assurance |
| Expectancy par symbole/session (§13) | partiel (régimes + slices par régime/heure dans le rapport) — un seul symètre, cellules trop petites |
| Options binaires (§19) | N/A (spot MT5). `evaluation.breakeven_wr()` fournit la formule si besoin. |

## Règle centrale

> Le bot ne doit pas apprendre à « prédire le marché » à partir de quelques trades.
> Il doit apprendre quelles configurations ont historiquement produit quels résultats,
> dans quels régimes, avec quelle incertitude — puis vérifier que cette relation
> survit sur des données qu'il n'a jamais vues.

Aucune ligne de ce paquet ne modifie le moteur live. Un rapport `CANDIDATE` n'autorise
rien : c'est un dossier à ouvrir, pas un interrupteur.
