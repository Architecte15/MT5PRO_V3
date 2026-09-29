# Liquidity Flow — rapport de recherche (hypothèses pré-enregistrées)

- Généré : 2026-09-23T19:04:20.299858+00:00
- Hash de pré-enregistrement (protocol + H1-H8 + ablations + grille) : `bab77edeb31f2eb4`
- Données : M15 16481 barres (2026-01-02 → 2026-09-01), H4 1165 barres
- Splits chronologiques : train 60% / validation 20% / OOS 10% / holdout 10% (dans le temps des trades)
- Détection sweeps : 4256 événements (3220 confirmés)

> Aucun composant n'est ajouté au moteur live. Ce document est un rapport, pas une autorisation de déploiement (spec §12-§18).

## Verdicts

| Hyp | Titre | n | OOS n | OOS espérance | OOS IC95 | OOS PF | WF + | Meilleur contrôle | VERDICT |
|---|---|--:|--:|--:|---|--:|--:|--:|---|
| H1 | Confirmed liquidity sweep alone | 3213 | 327 | 0.000069 | [0.000004, 0.000137] | 1.38 | 3/4 | -0.000015 | **CANDIDATE (holdout + manual approval required; auto-deploy forbidden)** |
| H2 | Sweep + displacement | 458 | 40 | 0.000068 | [-0.000426, 0.000573] | 1.11 | 2/4 | -0.000019 | **EDGE NOT FOUND** |
| H3 | Sweep + displacement + BOS | 239 | 20 | 0.000536 | [-0.000280, 0.001420] | 1.91 | 2/4 | -0.000004 | **EDGE NOT FOUND** |
| H4 | Sweep + displacement + BOS + EMA13 | 234 | 20 | 0.000536 | [-0.000280, 0.001420] | 1.91 | 2/4 | -0.000004 | **EDGE NOT FOUND** |
| H5 | Sweep of HTF liquidity + displacement | 54 | 8 | 0.000554 | [-0.000521, 0.001812] | 2.34 | 2/3 | -0.000015 | **EDGE NOT FOUND** |
| H6 | Sweep + displacement + BOS + MTF alignment | 155 | 9 | 0.000657 | [-0.000128, 0.001424] | 3.28 | 2/4 | -0.000001 | **EDGE NOT FOUND** |
| H7 | Sweep + displacement with opposite-liquidity target | 740 | 66 | -0.000059 | [-0.000153, 0.000022] | 0.56 | 3/4 | -0.000032 | **EDGE NOT FOUND** |
| H8 | Full combination (sweep + displacement + BOS + EMA13 + MTF) | 153 | 9 | 0.000657 | [-0.000128, 0.001424] | 3.28 | 2/4 | -0.000001 | **EDGE NOT FOUND** |

## H1 — Confirmed liquidity sweep alone

- Composants : sweep
- SL : `SWEEP_EXTREME` | TP : `FIXED_RR` | RR : 2.0
- Funnel : sweeps 4256 → classe 1036 écartés → zone HTF 0 → displacement 0 → BOS 0 → EMA13 0 → align HTF 0 → SL 0 → TP 0 → simulation 5 → **construits 3213**
- Verdict : **CANDIDATE (holdout + manual approval required; auto-deploy forbidden)**
  - all gates passed
- Diagnostic post-hoc (non pré-enregistré) : somme PnL tous splits = -0.028390 | PF train=0.9255410526316267 | PF validation=0.9001750256503601 | PF holdout=1.2019765287214315 → **STABILITY_CONCERN: train/validation PF < 1 — edge concentrated in the most recent period, likely regime; deployment NOT recommended**

| Split | n | Espérance (prix) | Espérance ~USD (0,01 lot) | IC95 | PF | WR | Max DD |
|---|--:|--:|--:|---|--:|--:|--:|
| train | 1934 | -0.000023 | -0.02 | [-0.000062, 0.000015] | 0.93 | 36.0% | 0.123470 |
| validation | 652 | -0.000025 | -0.03 | [-0.000074, 0.000025] | 0.90 | 35.9% | 0.028230 |
| oos | 327 | 0.000069 | 0.07 | [0.000004, 0.000137] | 1.38 | 37.9% | 0.009000 |
| holdout | 300 | 0.000033 | 0.03 | [-0.000016, 0.000081] | 1.20 | 39.0% | 0.007190 |

- Contrôles (OOS) : `{"random_direction": {"mean_expectancy": -1.5110633316512769e-05, "p95_expectancy": 7.014639259842991e-05, "share_draws_ge_real": 0.06, "draws": 100}, "random_eligible_entry": {"mean_expectancy": -1.5844616084617437e-05, "p95_expectancy": 9.836642968724135e-05, "share_draws_ge_real": 0.12, "draws": 100}}`
- Walk-forward : fold1 n=421 esp=0.000000, fold2 n=383 esp=0.000097, fold3 n=419 esp=-0.000022, fold4 n=409 esp=0.000031

- Par régime : `{"DOWNTREND": {"n": 309, "expectancy": 7.57605177993669e-05, "pf": 1.3137649108698317, "win_rate": 0.39805825242718446}, "RANGE": {"n": 609, "expectancy": 8.62068965518696e-06, "pf": 1.0274825943569483, "win_rate": 0.3793103448275862}, "STRONG_DOWNTREND": {"n": 1156, "expectancy": -2.1626297577848833e-05, "pf": 0.9163095875736915, "win_rate": 0.3624567474048443}, "STRONG_UPTREND": {"n": 922, "expectancy": 1.2711496746217821e-05, "pf": 1.0519296379990677, "win_rate": 0.3676789587852495}, "UPTREND": {"n": 217, "expectancy": -0.0002017050691244356, "pf": 0.4383421018863834, "win_rate": 0.271889400921659}}`

## H2 — Sweep + displacement

- Composants : sweep, displacement
- SL : `SWEEP_EXTREME` | TP : `FIXED_RR` | RR : 2.0
- Funnel : sweeps 4256 → classe 1036 écartés → zone HTF 0 → displacement 2762 → BOS 0 → EMA13 0 → align HTF 0 → SL 0 → TP 0 → simulation 0 → **construits 458**
- Verdict : **EDGE NOT FOUND**
  - 95% CI of OOS expectancy includes/below 0: (-0.00042551249999998094, 0.0005726750000000309)
  - walk-forward stability 2/4 < 75%
- Diagnostic post-hoc (non pré-enregistré) : somme PnL tous splits = 0.111430 | PF train=1.2408933217693057 | PF validation=1.7747913188646685 | PF holdout=0.8307573415765046 → **no early-split concern**

| Split | n | Espérance (prix) | Espérance ~USD (0,01 lot) | IC95 | PF | WR | Max DD |
|---|--:|--:|--:|---|--:|--:|--:|
| train | 284 | 0.000235 | 0.23 | [-0.000063, 0.000530] | 1.24 | 40.8% | 0.034580 |
| validation | 92 | 0.000504 | 0.50 | [0.000105, 0.000922] | 1.77 | 39.1% | 0.022380 |
| oos | 40 | 0.000068 | 0.07 | [-0.000426, 0.000573] | 1.11 | 35.0% | 0.005890 |
| holdout | 42 | -0.000104 | -0.10 | [-0.000483, 0.000274] | 0.83 | 28.6% | 0.009580 |

- Contrôles (OOS) : `{"random_direction": {"mean_expectancy": -0.0001746145329984408, "p95_expectancy": 2.828957457661623e-05, "share_draws_ge_real": 0.01, "draws": 100}, "random_eligible_entry": {"mean_expectancy": -1.872147384833079e-05, "p95_expectancy": 0.00036085573310891416, "share_draws_ge_real": 0.38, "draws": 100}}`
- Walk-forward : fold1 n=57 esp=0.000131, fold2 n=60 esp=-0.000008, fold3 n=54 esp=0.000869, fold4 n=53 esp=-0.000203

- Par régime : `{"DOWNTREND": {"n": 51, "expectancy": 0.0005474509803922211, "pf": 1.7195876288660155, "win_rate": 0.4117647058823529}, "RANGE": {"n": 80, "expectancy": -2.5374999999949744e-05, "pf": 0.9755774783446114, "win_rate": 0.4375}, "STRONG_DOWNTREND": {"n": 175, "expectancy": 0.0001153714285714104, "pf": 1.1307811892731918, "win_rate": 0.3485714285714286}, "STRONG_UPTREND": {"n": 115, "expectancy": 0.00022773913043477238, "pf": 1.2985636114910681, "win_rate": 0.34782608695652173}, "UPTREND": {"n": 37, "expectancy": 0.0010583783783784046, "pf": 2.643306756189594, "win_rate": 0.5675675675675675}}`

## H3 — Sweep + displacement + BOS

- Composants : sweep, displacement, BOS
- SL : `SWEEP_EXTREME` | TP : `FIXED_RR` | RR : 2.0
- Funnel : sweeps 4256 → classe 1036 écartés → zone HTF 0 → displacement 2762 → BOS 219 → EMA13 0 → align HTF 0 → SL 0 → TP 0 → simulation 0 → **construits 239**
- Verdict : **EDGE NOT FOUND**
  - OOS n=20 < 30
  - 95% CI of OOS expectancy includes/below 0: (-0.00027961250000003247, 0.0014200375000001208)
  - walk-forward stability 2/4 < 75%
- Diagnostic post-hoc (non pré-enregistré) : somme PnL tous splits = 0.076360 | PF train=1.2411191803186081 | PF validation=1.5843920145189658 | PF holdout=1.2300593276202287 → **no early-split concern**

| Split | n | Espérance (prix) | Espérance ~USD (0,01 lot) | IC95 | PF | WR | Max DD |
|---|--:|--:|--:|---|--:|--:|--:|
| train | 156 | 0.000275 | 0.27 | [-0.000166, 0.000739] | 1.24 | 39.1% | 0.046830 |
| validation | 39 | 0.000495 | 0.50 | [-0.000300, 0.001321] | 1.58 | 41.0% | 0.010350 |
| oos | 20 | 0.000536 | 0.54 | [-0.000280, 0.001420] | 1.91 | 50.0% | 0.003920 |
| holdout | 24 | 0.000145 | 0.15 | [-0.000426, 0.000782] | 1.23 | 37.5% | 0.006450 |

- Contrôles (OOS) : `{"random_direction": {"mean_expectancy": -9.111960867127754e-05, "p95_expectancy": 0.00019396648924269392, "share_draws_ge_real": 0.0, "draws": 100}, "random_eligible_entry": {"mean_expectancy": -4.22916360068926e-06, "p95_expectancy": 0.00047288898054940456, "share_draws_ge_real": 0.01, "draws": 100}}`
- Walk-forward : fold1 n=26 esp=-0.000227, fold2 n=33 esp=-0.000784, fold3 n=28 esp=0.000641, fold4 n=22 esp=0.000495

- Par régime : `{"DOWNTREND": {"n": 24, "expectancy": 0.0007545833333333085, "pf": 1.6899047619046956, "win_rate": 0.5}, "RANGE": {"n": 53, "expectancy": -0.0002764150943396404, "pf": 0.7886612810155726, "win_rate": 0.41509433962264153}, "STRONG_DOWNTREND": {"n": 96, "expectancy": 0.00024135416666663106, "pf": 1.2591432725645357, "win_rate": 0.3333333333333333}, "STRONG_UPTREND": {"n": 53, "expectancy": 0.0009903773584905814, "pf": 2.463747908533071, "win_rate": 0.4716981132075472}, "UPTREND": {"n": 13, "expectancy": -0.00021230769230778506, "pf": 0.8357142857142306, "win_rate": 0.38461538461538464}}`

## H4 — Sweep + displacement + BOS + EMA13

- Composants : sweep, displacement, BOS, EMA13
- SL : `SWEEP_EXTREME` | TP : `FIXED_RR` | RR : 2.0
- Funnel : sweeps 4256 → classe 1036 écartés → zone HTF 0 → displacement 2762 → BOS 219 → EMA13 5 → align HTF 0 → SL 0 → TP 0 → simulation 0 → **construits 234**
- Verdict : **EDGE NOT FOUND**
  - OOS n=20 < 30
  - 95% CI of OOS expectancy includes/below 0: (-0.00027961250000003247, 0.0014200375000001208)
  - walk-forward stability 2/4 < 75%
- Diagnostic post-hoc (non pré-enregistré) : somme PnL tous splits = 0.070600 | PF train=1.2137461800149583 | PF validation=1.5843920145189658 | PF holdout=1.2300593276202287 → **no early-split concern**

| Split | n | Espérance (prix) | Espérance ~USD (0,01 lot) | IC95 | PF | WR | Max DD |
|---|--:|--:|--:|---|--:|--:|--:|
| train | 151 | 0.000245 | 0.25 | [-0.000194, 0.000741] | 1.21 | 38.4% | 0.042630 |
| validation | 39 | 0.000495 | 0.50 | [-0.000300, 0.001321] | 1.58 | 41.0% | 0.010350 |
| oos | 20 | 0.000536 | 0.54 | [-0.000280, 0.001420] | 1.91 | 50.0% | 0.003920 |
| holdout | 24 | 0.000145 | 0.15 | [-0.000425, 0.000782] | 1.23 | 37.5% | 0.006450 |

- Contrôles (OOS) : `{"random_direction": {"mean_expectancy": -9.111960867127754e-05, "p95_expectancy": 0.00019396648924269392, "share_draws_ge_real": 0.0, "draws": 100}, "random_eligible_entry": {"mean_expectancy": -4.22916360068926e-06, "p95_expectancy": 0.00047288898054940456, "share_draws_ge_real": 0.01, "draws": 100}}`
- Walk-forward : fold1 n=23 esp=-0.000205, fold2 n=33 esp=-0.000784, fold3 n=28 esp=0.000641, fold4 n=22 esp=0.000495

- Par régime : `{"DOWNTREND": {"n": 24, "expectancy": 0.0007545833333333085, "pf": 1.6899047619046956, "win_rate": 0.5}, "RANGE": {"n": 52, "expectancy": -0.00033942307692309717, "pf": 0.7453837276399231, "win_rate": 0.40384615384615385}, "STRONG_DOWNTREND": {"n": 94, "expectancy": 0.00029117021276592087, "pf": 1.3212064311699891, "win_rate": 0.3404255319148936}, "STRONG_UPTREND": {"n": 51, "expectancy": 0.0008927450980392257, "pf": 2.2696597880645926, "win_rate": 0.45098039215686275}, "UPTREND": {"n": 13, "expectancy": -0.00021230769230778506, "pf": 0.8357142857142306, "win_rate": 0.38461538461538464}}`

## H5 — Sweep of HTF liquidity + displacement

- Composants : sweep:HTF, displacement
- SL : `SWEEP_EXTREME` | TP : `FIXED_RR` | RR : 2.0
- Funnel : sweeps 4256 → classe 1036 écartés → zone HTF 3032 → displacement 134 → BOS 0 → EMA13 0 → align HTF 0 → SL 0 → TP 0 → simulation 0 → **construits 54**
- Verdict : **EDGE NOT FOUND**
  - OOS n=8 < 30
  - 95% CI of OOS expectancy includes/below 0: (-0.0005213125000000852, 0.0018124999999999947)
  - walk-forward stability 2/3 < 75%
- Diagnostic post-hoc (non pré-enregistré) : somme PnL tous splits = 0.003300 | PF train=0.5789636984176416 | PF validation=4.463087248322169 | PF holdout=2.0599999999999357 → **STABILITY_CONCERN: train/validation PF < 1 — edge concentrated in the most recent period, likely regime; deployment NOT recommended**

| Split | n | Espérance (prix) | Espérance ~USD (0,01 lot) | IC95 | PF | WR | Max DD |
|---|--:|--:|--:|---|--:|--:|--:|
| train | 35 | -0.000388 | -0.39 | [-0.000939, 0.000217] | 0.58 | 37.1% | 0.018970 |
| validation | 7 | 0.001474 | 1.47 | [-0.000334, 0.002823] | 4.46 | 57.1% | 0.001760 |
| oos | 8 | 0.000554 | 0.55 | [-0.000521, 0.001812] | 2.34 | 37.5% | 0.003310 |
| holdout | 4 | 0.000530 | 0.53 | [-0.001000, 0.002060] | 2.06 | 50.0% | 0.001420 |

- Contrôles (OOS) : `{"random_direction": {"mean_expectancy": -1.4647655419629257e-05, "p95_expectancy": 0.0009690660384665262, "share_draws_ge_real": 0.08, "draws": 100}, "random_eligible_entry": {"mean_expectancy": -3.8588123486647805e-05, "p95_expectancy": 0.0007564379712786366, "share_draws_ge_real": 0.14, "draws": 100}}`
- Walk-forward : fold1 n=7 esp=-0.000589, fold2 n=3 esp=0.000150, fold3 n=5 esp=0.001696, fold4 n=9 esp=0.000357

- Par régime : `{"DOWNTREND": {"n": 10, "expectancy": -0.0009630000000000916, "pf": 0.21897810218976, "win_rate": 0.1}, "RANGE": {"n": 9, "expectancy": -0.00019777777777771653, "pf": 0.7520891364903493, "win_rate": 0.3333333333333333}, "STRONG_DOWNTREND": {"n": 14, "expectancy": -0.0005178571428572365, "pf": 0.4613670133729317, "win_rate": 0.21428571428571427}, "STRONG_UPTREND": {"n": 14, "expectancy": 0.0003778571428572234, "pf": 1.8088685015291706, "win_rate": 0.6428571428571429}, "UPTREND": {"n": 7, "expectancy": 0.0023814285714286614, "pf": 17.50495049504723, "win_rate": 0.8571428571428571}}`

## H6 — Sweep + displacement + BOS + MTF alignment

- Composants : sweep, displacement, BOS, MTF
- SL : `SWEEP_EXTREME` | TP : `FIXED_RR` | RR : 2.0
- Funnel : sweeps 4256 → classe 1036 écartés → zone HTF 0 → displacement 2479 → BOS 414 → EMA13 0 → align HTF 172 → SL 0 → TP 0 → simulation 0 → **construits 155**
- Verdict : **EDGE NOT FOUND**
  - OOS n=9 < 30
  - 95% CI of OOS expectancy includes/below 0: (-0.00012783333333335592, 0.0014244444444445005)
  - walk-forward stability 2/4 < 75%
- Diagnostic post-hoc (non pré-enregistré) : somme PnL tous splits = 0.047190 | PF train=1.162934362934335 | PF validation=1.9789251844045006 | PF holdout=1.5578947368419795 → **no early-split concern**

| Split | n | Espérance (prix) | Espérance ~USD (0,01 lot) | IC95 | PF | WR | Max DD |
|---|--:|--:|--:|---|--:|--:|--:|
| train | 108 | 0.000176 | 0.18 | [-0.000334, 0.000722] | 1.16 | 38.9% | 0.042550 |
| validation | 27 | 0.000688 | 0.69 | [-0.000197, 0.001593] | 1.98 | 40.7% | 0.008630 |
| oos | 9 | 0.000657 | 0.66 | [-0.000128, 0.001424] | 3.28 | 66.7% | 0.001910 |
| holdout | 11 | 0.000337 | 0.34 | [-0.000635, 0.001260] | 1.56 | 45.5% | 0.003610 |

- Contrôles (OOS) : `{"random_direction": {"mean_expectancy": -9.948486456494019e-05, "p95_expectancy": 0.0005585350520586717, "share_draws_ge_real": 0.0, "draws": 100}, "random_eligible_entry": {"mean_expectancy": -1.0687490993076391e-06, "p95_expectancy": 0.0008827950350315483, "share_draws_ge_real": 0.11, "draws": 100}}`
- Walk-forward : fold1 n=23 esp=-0.001452, fold2 n=19 esp=-0.000433, fold3 n=15 esp=0.001036, fold4 n=13 esp=0.000741

- Par régime : `{"DOWNTREND": {"n": 16, "expectancy": 0.0003125000000000072, "pf": 1.2548419979612588, "win_rate": 0.4375}, "RANGE": {"n": 31, "expectancy": 0.00018064516129030268, "pf": 1.2015838732901007, "win_rate": 0.41935483870967744}, "STRONG_DOWNTREND": {"n": 61, "expectancy": 0.00026327868852456043, "pf": 1.288123430211648, "win_rate": 0.3770491803278688}, "STRONG_UPTREND": {"n": 32, "expectancy": 0.0006499999999999978, "pf": 1.764144011755996, "win_rate": 0.46875}, "UPTREND": {"n": 15, "expectancy": -1.8000000000043907e-05, "pf": 0.981263011797319, "win_rate": 0.4}}`

## H7 — Sweep + displacement with opposite-liquidity target

- Composants : sweep, displacement, opposite_liquidity_target
- SL : `SWEEP_EXTREME` | TP : `OPPOSITE_LIQUIDITY` | RR : 2.0
- Funnel : sweeps 4256 → classe 1036 écartés → zone HTF 0 → displacement 2479 → BOS 0 → EMA13 0 → align HTF 0 → SL 0 → TP 1 → simulation 0 → **construits 740**
- Verdict : **EDGE NOT FOUND**
  - 95% CI of OOS expectancy includes/below 0: (-0.00015318560606062016, 2.212878787880791e-05)
  - OOS PF=0.5580865603645232
  - OOS expectancy -0.000059 <= best control -0.000032
- Diagnostic post-hoc (non pré-enregistré) : somme PnL tous splits = 0.039130 | PF train=2.1614398691026864 | PF validation=0.9955780164244823 | PF holdout=1.1585760517800152 → **STABILITY_CONCERN: train/validation PF < 1 — edge concentrated in the most recent period, likely regime; deployment NOT recommended**

| Split | n | Espérance (prix) | Espérance ~USD (0,01 lot) | IC95 | PF | WR | Max DD |
|---|--:|--:|--:|---|--:|--:|--:|
| train | 462 | 0.000092 | 0.09 | [0.000045, 0.000136] | 2.16 | 93.7% | 0.005850 |
| validation | 157 | -0.000000 | -0.00 | [-0.000051, 0.000047] | 1.00 | 86.6% | 0.006820 |
| oos | 66 | -0.000059 | -0.06 | [-0.000153, 0.000022] | 0.56 | 84.8% | 0.005400 |
| holdout | 55 | 0.000009 | 0.01 | [-0.000047, 0.000059] | 1.16 | 90.9% | 0.001670 |

- Contrôles (OOS) : `{"random_direction": {"mean_expectancy": -5.526988398101634e-05, "p95_expectancy": 0.0001482747774895773, "share_draws_ge_real": 0.49, "draws": 100}, "random_eligible_entry": {"mean_expectancy": -3.189531407272247e-05, "p95_expectancy": 0.0002541409567211308, "share_draws_ge_real": 0.61, "draws": 100}}`
- Walk-forward : fold1 n=97 esp=0.000050, fold2 n=89 esp=0.000019, fold3 n=101 esp=0.000010, fold4 n=90 esp=-0.000036

- Par régime : `{"DOWNTREND": {"n": 87, "expectancy": 5.609195402300887e-05, "pf": 1.6062111801244185, "win_rate": 0.9080459770114943}, "RANGE": {"n": 127, "expectancy": 4.6456692913288046e-06, "pf": 1.0327413984461, "win_rate": 0.905511811023622}, "STRONG_DOWNTREND": {"n": 269, "expectancy": 7.286245353159132e-05, "pf": 1.9655172413790785, "win_rate": 0.9070631970260223}, "STRONG_UPTREND": {"n": 194, "expectancy": 4.242268041236177e-05, "pf": 1.5255427841632831, "win_rate": 0.9123711340206185}, "UPTREND": {"n": 63, "expectancy": 9.253968253971076e-05, "pf": 3.491452991453033, "win_rate": 0.9523809523809523}}`

## H8 — Full combination (sweep + displacement + BOS + EMA13 + MTF)

- Composants : sweep, displacement, BOS, EMA13, MTF
- SL : `SWEEP_EXTREME` | TP : `FIXED_RR` | RR : 2.0
- Funnel : sweeps 4256 → classe 1036 écartés → zone HTF 0 → displacement 2479 → BOS 414 → EMA13 8 → align HTF 166 → SL 0 → TP 0 → simulation 0 → **construits 153**
- Verdict : **EDGE NOT FOUND**
  - OOS n=9 < 30
  - 95% CI of OOS expectancy includes/below 0: (-0.00012783333333335592, 0.0014244444444445005)
  - walk-forward stability 2/4 < 75%
- Diagnostic post-hoc (non pré-enregistré) : somme PnL tous splits = 0.051390 | PF train=1.2064085447262698 | PF validation=1.9789251844045006 | PF holdout=1.5578947368419795 → **no early-split concern**

| Split | n | Espérance (prix) | Espérance ~USD (0,01 lot) | IC95 | PF | WR | Max DD |
|---|--:|--:|--:|---|--:|--:|--:|
| train | 106 | 0.000219 | 0.22 | [-0.000269, 0.000756] | 1.21 | 39.6% | 0.038350 |
| validation | 27 | 0.000688 | 0.69 | [-0.000197, 0.001593] | 1.98 | 40.7% | 0.008630 |
| oos | 9 | 0.000657 | 0.66 | [-0.000128, 0.001424] | 3.28 | 66.7% | 0.001910 |
| holdout | 11 | 0.000337 | 0.34 | [-0.000635, 0.001260] | 1.56 | 45.5% | 0.003610 |

- Contrôles (OOS) : `{"random_direction": {"mean_expectancy": -9.948486456494019e-05, "p95_expectancy": 0.0005585350520586717, "share_draws_ge_real": 0.0, "draws": 100}, "random_eligible_entry": {"mean_expectancy": -1.0687490993076391e-06, "p95_expectancy": 0.0008827950350315483, "share_draws_ge_real": 0.11, "draws": 100}}`
- Walk-forward : fold1 n=21 esp=-0.001390, fold2 n=19 esp=-0.000433, fold3 n=15 esp=0.001036, fold4 n=13 esp=0.000741

- Par régime : `{"DOWNTREND": {"n": 16, "expectancy": 0.0003125000000000072, "pf": 1.2548419979612588, "win_rate": 0.4375}, "RANGE": {"n": 31, "expectancy": 0.00018064516129030268, "pf": 1.2015838732901007, "win_rate": 0.41935483870967744}, "STRONG_DOWNTREND": {"n": 59, "expectancy": 0.0003433898305084435, "pf": 1.3930927435001337, "win_rate": 0.3898305084745763}, "STRONG_UPTREND": {"n": 32, "expectancy": 0.0006499999999999978, "pf": 1.764144011755996, "win_rate": 0.46875}, "UPTREND": {"n": 15, "expectancy": -1.8000000000043907e-05, "pf": 0.981263011797319, "win_rate": 0.4}}`

## Ablations (rapport seul — aucune adoption automatique)

### A1 — sl_mode sur l'entrée « H2 »

| Variante | n | Espérance (prix) | PF | WR | OOS n | OOS espérance |
|---|--:|--:|--:|--:|--:|--:|
| `SWEEP_EXTREME` | 458 | 0.000243 | 1.29 | 38.9% | 40 | 0.000068 |
| `ENTRY_SIGNAL_CANDLE` | 456 | 0.000016 | 1.04 | 33.1% | 40 | -0.000065 |
| `STRUCTURE` | 455 | 0.000276 | 1.32 | 38.7% | 40 | 0.000420 |
| `ATR_BASED` | 458 | 0.000082 | 1.13 | 35.6% | 40 | -0.000132 |

### A2 — tp_mode sur l'entrée « H2 »

| Variante | n | Espérance (prix) | PF | WR | OOS n | OOS espérance |
|---|--:|--:|--:|--:|--:|--:|
| `FIXED_RR` | 458 | 0.000243 | 1.29 | 38.9% | 40 | 0.000068 |
| `OPPOSITE_LIQUIDITY` | 458 | 0.000033 | 1.38 | 92.4% | 40 | -0.000067 |
| `TIME_EXIT` | 458 | 0.000274 | 1.29 | 31.4% | 40 | 0.000049 |

## Réglage de la grille displacement (TRAIN uniquement)

Règle pré-enregistrée : max TRAIN expectancy among grid candidates with >= 15 TRAIN trades; ties -> default params

- **H2** — choisi : grille #2 `{"weak_atr": 0.8, "moderate_atr": 1.2, "strong_atr": 2.0, "window": 3, "min_dir_candles": 2}`
  - grille #0 `{"weak_atr": 0.6, "moderate_atr": 0.8, "strong_atr": 1.2, "window": 3, "min_dir_candles": 2}` → train n=462, espérance=0.000198
  - grille #1 `{"weak_atr": 0.6, "moderate_atr": 1.0, "strong_atr": 1.6, "window": 3, "min_dir_candles": 2}` → train n=366, espérance=0.000214
  - grille #2 `{"weak_atr": 0.8, "moderate_atr": 1.2, "strong_atr": 2.0, "window": 3, "min_dir_candles": 2}` → train n=284, espérance=0.000235
- **H3** — choisi : grille #2 `{"weak_atr": 0.8, "moderate_atr": 1.2, "strong_atr": 2.0, "window": 3, "min_dir_candles": 2}`
  - grille #0 `{"weak_atr": 0.6, "moderate_atr": 0.8, "strong_atr": 1.2, "window": 3, "min_dir_candles": 2}` → train n=202, espérance=0.000218
  - grille #1 `{"weak_atr": 0.6, "moderate_atr": 1.0, "strong_atr": 1.6, "window": 3, "min_dir_candles": 2}` → train n=177, espérance=0.000205
  - grille #2 `{"weak_atr": 0.8, "moderate_atr": 1.2, "strong_atr": 2.0, "window": 3, "min_dir_candles": 2}` → train n=156, espérance=0.000275
- **H4** — choisi : grille #2 `{"weak_atr": 0.8, "moderate_atr": 1.2, "strong_atr": 2.0, "window": 3, "min_dir_candles": 2}`
  - grille #0 `{"weak_atr": 0.6, "moderate_atr": 0.8, "strong_atr": 1.2, "window": 3, "min_dir_candles": 2}` → train n=195, espérance=0.000198
  - grille #1 `{"weak_atr": 0.6, "moderate_atr": 1.0, "strong_atr": 1.6, "window": 3, "min_dir_candles": 2}` → train n=172, espérance=0.000178
  - grille #2 `{"weak_atr": 0.8, "moderate_atr": 1.2, "strong_atr": 2.0, "window": 3, "min_dir_candles": 2}` → train n=151, espérance=0.000245
- **H5** — choisi : grille #0 `{"weak_atr": 0.6, "moderate_atr": 0.8, "strong_atr": 1.2, "window": 3, "min_dir_candles": 2}`
  - grille #0 `{"weak_atr": 0.6, "moderate_atr": 0.8, "strong_atr": 1.2, "window": 3, "min_dir_candles": 2}` → train n=35, espérance=-0.000388
  - grille #1 `{"weak_atr": 0.6, "moderate_atr": 1.0, "strong_atr": 1.6, "window": 3, "min_dir_candles": 2}` → train n=23, espérance=-0.000411
  - grille #2 `{"weak_atr": 0.8, "moderate_atr": 1.2, "strong_atr": 2.0, "window": 3, "min_dir_candles": 2}` → train n=13, espérance=-0.000362
- **H6** — choisi : grille #0 `{"weak_atr": 0.6, "moderate_atr": 0.8, "strong_atr": 1.2, "window": 3, "min_dir_candles": 2}`
  - grille #0 `{"weak_atr": 0.6, "moderate_atr": 0.8, "strong_atr": 1.2, "window": 3, "min_dir_candles": 2}` → train n=108, espérance=0.000176
  - grille #1 `{"weak_atr": 0.6, "moderate_atr": 1.0, "strong_atr": 1.6, "window": 3, "min_dir_candles": 2}` → train n=92, espérance=0.000101
  - grille #2 `{"weak_atr": 0.8, "moderate_atr": 1.2, "strong_atr": 2.0, "window": 3, "min_dir_candles": 2}` → train n=84, espérance=0.000052
- **H7** — choisi : grille #0 `{"weak_atr": 0.6, "moderate_atr": 0.8, "strong_atr": 1.2, "window": 3, "min_dir_candles": 2}`
  - grille #0 `{"weak_atr": 0.6, "moderate_atr": 0.8, "strong_atr": 1.2, "window": 3, "min_dir_candles": 2}` → train n=462, espérance=0.000092
  - grille #1 `{"weak_atr": 0.6, "moderate_atr": 1.0, "strong_atr": 1.6, "window": 3, "min_dir_candles": 2}` → train n=366, espérance=0.000055
  - grille #2 `{"weak_atr": 0.8, "moderate_atr": 1.2, "strong_atr": 2.0, "window": 3, "min_dir_candles": 2}` → train n=284, espérance=0.000049
- **H8** — choisi : grille #0 `{"weak_atr": 0.6, "moderate_atr": 0.8, "strong_atr": 1.2, "window": 3, "min_dir_candles": 2}`
  - grille #0 `{"weak_atr": 0.6, "moderate_atr": 0.8, "strong_atr": 1.2, "window": 3, "min_dir_candles": 2}` → train n=106, espérance=0.000219
  - grille #1 `{"weak_atr": 0.6, "moderate_atr": 1.0, "strong_atr": 1.6, "window": 3, "min_dir_candles": 2}` → train n=90, espérance=0.000150
  - grille #2 `{"weak_atr": 0.8, "moderate_atr": 1.2, "strong_atr": 2.0, "window": 3, "min_dir_candles": 2}` → train n=82, espérance=0.000105

## Référence : moteur courant

`{"available": true, "source": "backtests\\reports\\trades.csv", "n": 49, "expectancy": 0.0010293877551021183, "expectancy_usd_001lot": 1.0293877551021182, "win_rate": 0.5510204081632653, "note": "R\u00e9f\u00e9rence informative : moteur courant avec filtres session/jour, \u00e9chantillon et p\u00e9riode diff\u00e9rents \u2014 pas un contr\u00f4le \u00e9quivalent."}`

## Notes et limites (honnêteté du rapport)

- Module strictement parallèle : app/research n'est importé par aucun code live (app.main / TradingEngine / SignalEngine inchangés).
- Aucune hypothèse n'est déployée automatiquement : un verdict CANDIDATE exige revue du holdout + approbation manuelle (spec §12 : MODEL VERSION, rollback).
- §19 binaires : N/A — ce bot exécute du spot MT5. formule BE_WR = LOSS/(WIN+LOSS) disponible dans app.research.evaluation.breakeven_wr pour tout usage futur.
- Périodes d'entrée multi-TF : M15 (sweep/displacement/BOS/EMA13) + H4 (liquidité HTF, alignement). M5/H1 non disponibles sans pause de la boucle live (connexion MT5 exclusive) — expériences LTF reportées (spec §6).
- Seuils de displacement : grille pré-enregistrée, sélection sur TRAIN uniquement, figée avant validation/OOS/holdout (spec §4).
- Contrôles : RANDOM_DIRECTION (mêmes entrées, côté au hasard, stop ATR + 2R) et RANDOM_ELIGIBLE_ENTRY (dates au hasard dans l'ensemble éligible, mêmes règles neutres) ; BASELINE_CURRENT_ENGINE en référence informative. Ces contrôles utilisent un stop ATR neutre : battre RANDOM_DIRECTION avec un stop SWEEP_EXTREME peut refléter la qualité du placement de stop autant que celle du timing de direction.
- Diagnostics marqués « post-hoc » (somme PnL tous splits, PF train/validation) ne font PAS partie de la politique de verdict pré-enregistrée — ils informent la décision humaine sans la remplacer.
- Ablation H7 (post-hoc) : OPPOSITE_LIQUIDITY n'imposait qu'une distance minimale de 5 points à la cible → cibles quasi immédiates, WR ~90% mais PF OOS < 1. Toute révision (ex. distance min ≥ 1×ATR) devra être pré-enregistrée AVANT retest.
- Chevauchement de positions : ce backtest, comme le moteur, autorise les trades superposés alors que le live est à max_open_positions=1 — le sous-ensemble réalisable en live est plus petit que n_total.
- Composants reportés (non implémentés cette phase, par design contrôlé) : memory/similarité §14, drift §16, online learning §15, registre de modèles §12, sorties PARTIAL/RUNNER §10, régimes par symbole/session §13 (cellules trop petites sur un seul symètre — reportés).
- Métriques en unités de prix EURUSD ; conversion indicative USD @0,01 lot = prix × 1000 (spread et latence non inclus).
- Échantillons : un verdict de déploiement exige n_OOS ≥ 30, IC95 > 0, PF > 1, supériorité sur les deux contrôles et stabilité walk-forward ≥ 75%.
