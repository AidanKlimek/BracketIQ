# BracketIQ — Weight Tuning Guide

All weights live in one file: `config/weights.py`. Change a number, save, re-run. No code changes needed anywhere else.

---

## The Rules

1. **Sub-weights within each tier must sum to 1.0.** If you increase one stat, decrease another by the same amount.

2. **Tier weights must also sum to 1.0.** Currently: Base 0.40 + Context 0.35 + Tournament 0.25 = 1.0.

3. **Run the backtest after changes** (`python main.py backtest`) to make sure you didn't break anything. Champions should still average top 10.

---

## Tier Weights — The Big Levers

At the top of `config/weights.py`:

```python
TIER_WEIGHTS = {
    "base": 0.40,       # How much raw efficiency matters
    "context": 0.35,    # How much schedule/trends/consistency matter
    "tournament": 0.25, # How much March-specific factors matter
}
```

**If you think efficiency is king:** Increase `base`, decrease `context` or `tournament`.

**If you think momentum and schedule matter more:** Increase `context`, decrease `base`.

**If you think March is chaos and upsets/archetypes should weigh more:** Increase `tournament`.

Example — making it more "March Madness" flavored:
```python
TIER_WEIGHTS = {
    "base": 0.35,
    "context": 0.35,
    "tournament": 0.30,
}
```

---

## Base Layer — Efficiency & Shooting (40%)

```python
BASE_WEIGHTS = {
    "adj_o": 0.18,          # Offensive efficiency
    "adj_d": 0.18,          # Defensive efficiency
    "net_efficiency": 0.14, # Combined margin
    "barthag": 0.10,        # Torvik power rating
    "off_efg": 0.08,        # Effective FG%
    "off_to": 0.05,         # Turnover rate
    "off_or": 0.03,         # Offensive rebounding
    "off_ftr": 0.02,        # Free throw rate
    "def_efg": 0.08,        # Opponent effective FG%
    "def_to": 0.04,         # Forced turnover rate
    "def_or": 0.03,         # Opponent offensive rebounding
    "def_ftr": 0.02,        # Opponent free throw rate
    "three_pct": 0.03,      # 3-point shooting
    "ft_pct": 0.02,         # Free throw shooting
}
# Must sum to 1.0
```

**Common tweaks:**

"I think defense wins championships":
```python
"adj_d": 0.22,    # was 0.18
"adj_o": 0.14,    # was 0.18
```

"I think turnovers lose games":
```python
"off_to": 0.08,   # was 0.05 — penalize careless teams more
"def_to": 0.06,   # was 0.04 — reward teams that force turnovers
"off_or": 0.01,   # was 0.03 — reduce rebounding to compensate
"off_ftr": 0.01,  # was 0.02
```

"I think free throw shooting is critical":
```python
"ft_pct": 0.05,   # was 0.02
"off_ftr": 0.01,  # was 0.02 — take from somewhere to compensate
```

---

## Context Layer — Schedule, Trends, Resume (35%)

```python
CONTEXT_WEIGHTS = {
    "sos_overall": 0.14,            # Strength of schedule
    "sos_noncon": 0.06,             # Non-conference SOS
    "sos_elite": 0.05,              # Elite opponent SOS
    "sos_elite_noncon": 0.03,       # Elite non-conference SOS
    "wab": 0.12,                    # Wins Above Bubble
    "qual_barthag": 0.08,           # Power rating in quality games
    "qual_o": 0.05,                 # Offense in quality games
    "qual_d": 0.05,                 # Defense in quality games
    "qual_games": 0.04,             # Number of quality games
    "trend_off_efficiency": 0.06,   # Offense trending up/down
    "trend_def_efficiency": 0.06,   # Defense trending up/down
    "trend_scoring_margin": 0.06,   # Margin trending up/down
    "volatility_scoring": 0.05,     # Scoring consistency
    "volatility_turnovers": 0.05,   # Turnover consistency
    "volatility_ft_pct": 0.05,      # FT% consistency
    "close_game_record": 0.05,      # Record in close games
}
# Must sum to 1.0
```

**Common tweaks:**

"I think playing a tough schedule is the #1 indicator":
```python
"sos_overall": 0.20,   # was 0.14
"sos_elite": 0.08,     # was 0.05
"qual_games": 0.02,    # was 0.04 — trim elsewhere
"sos_noncon": 0.03,    # was 0.06
```

"I think recent momentum is everything heading into March":
```python
"trend_off_efficiency": 0.10,   # was 0.06
"trend_def_efficiency": 0.10,   # was 0.06
"trend_scoring_margin": 0.08,   # was 0.06
"sos_elite_noncon": 0.00,       # was 0.03 — sacrifice this
"qual_games": 0.00,             # was 0.04
```

"I think consistency matters more than peaks":
```python
"volatility_scoring": 0.08,     # was 0.05
"volatility_turnovers": 0.07,   # was 0.05
"volatility_ft_pct": 0.07,      # was 0.05
"qual_o": 0.02,                  # was 0.05 — take from here
"qual_d": 0.02,                  # was 0.05
```

---

## Tournament Layer — March Factors (25%)

```python
TOURNAMENT_WEIGHTS = {
    "archetype_similarity": 0.28,       # Match to past champion profile
    "upset_three_pt_var": 0.08,         # 3PT variance (upset potential)
    "upset_def_efficiency": 0.08,       # Elite defense (upset potential)
    "upset_tempo_control": 0.06,        # Pace control (upset potential)
    "upset_turnover_creation": 0.06,    # TO creation (upset potential)
    "seed_bonus": 0.05,                 # Committee seed
    "ft_pct_close_games": 0.10,         # FT% in pressure games
    "ft_consistency": 0.07,             # FT% reliability
    "conf_tournament_result": 0.12,     # Conference tournament result
    "tempo": 0.10,                      # Tempo factor
}
# Must sum to 1.0
```

**Common tweaks:**

"I trust the selection committee more":
```python
"seed_bonus": 0.12,            # was 0.05
"archetype_similarity": 0.21, # was 0.28 — take from here
```

"I want to flag more upsets":
```python
"upset_three_pt_var": 0.12,        # was 0.08
"upset_def_efficiency": 0.12,      # was 0.08
"upset_tempo_control": 0.08,       # was 0.06
"upset_turnover_creation": 0.08,   # was 0.06
"archetype_similarity": 0.18,      # was 0.28 — reduce to compensate
```

"I think free throws decide tournament games":
```python
"ft_pct_close_games": 0.15,   # was 0.10
"ft_consistency": 0.12,       # was 0.07
"upset_tempo_control": 0.03,  # was 0.06 — trim elsewhere
"tempo": 0.05,                # was 0.10
```

---

## Stat Polarity — Direction Matters

In `STAT_POLARITY`, every stat is marked `True` (higher = better), `False` (lower = better), or `None` (neutral).

You should almost never need to change these unless you add a new stat. But if something feels backwards in the rankings — like a team with great defense scoring poorly on a defensive stat — check that the polarity is correct.

---

## Workflow for Tuning

1. **Make your changes** in `config/weights.py`
2. **Verify sums** — each weight group must sum to 1.0
3. **Run backtest**: `python main.py backtest`
4. **Check:** Do champions still rank top 10? Do Final Four teams still mostly land in top 25?
5. **Run current rankings**: `python main.py rank`
6. **Gut check:** Does the top 25 pass the eye test?
7. **Repeat** until you're satisfied

---

## Nuclear Option: Reset to Defaults

If you've tweaked things into oblivion and want to start over, the original weights are saved in the git history. Run:

```bash
git checkout config/weights.py
```

This restores the original file from your last commit.