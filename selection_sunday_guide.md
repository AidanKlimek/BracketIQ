# BracketIQ — Selection Sunday Guide

Follow these steps in order. Total time: ~45 minutes (mostly waiting for ESPN data to cache).

---

## Step 1: Update Conference Tournament Results (~5 min)

Open `config/tournament.py` in VSCode.

Find the `CONF_TOURNEY_RESULTS` dictionary and fill in results as you know them:

```python
CONF_TOURNEY_RESULTS = {
    # Won conference tournament = 100
    # Lost in championship game = 75
    # Lost in semifinal = 50
    # Lost in quarterfinal = 25
    # Lost earlier = 0
    
    "Duke": 100,
    "North Carolina": 75,
    "Virginia": 50,
    # ... add all teams you've tracked
}
```

You don't need every team — focus on the ones likely to make the tournament. Any team not listed defaults to 0.

Save the file.

---

## Step 2: Fill in the 68 Tournament Teams (~15 min)

Watch the Selection Sunday show. As teams are announced, fill in `TOURNAMENT_TEAMS` in the same `config/tournament.py` file:

```python
TOURNAMENT_TEAMS = {
    "Duke": {"seed": 1, "region": "East"},
    "Houston": {"seed": 1, "region": "South"},
    "Michigan": {"seed": 1, "region": "West"},
    "Florida": {"seed": 1, "region": "Midwest"},
    "Alabama": {"seed": 2, "region": "East"},
    # ... all 68 teams with their seed and region
}
```

**Important:** The team names must match what Torvik uses. Common tricky names:
- Use `"Connecticut"` not `"UConn"`
- Use `"St. John's"` not `"Saint John's"`
- Use `"NC State"` not `"North Carolina State"`
- Use `"Miami FL"` not just `"Miami"`

If unsure, run `python main.py rank` and look at the team names in the output.

Also fill in the play-in matchups if you want to track those:

```python
PLAYIN_MATCHUPS = [
    {"team_a": "Team1", "team_b": "Team2", "seed": 16, "winner": None},
    {"team_a": "Team3", "team_b": "Team4", "seed": 16, "winner": None},
    {"team_a": "Team5", "team_b": "Team6", "seed": 11, "winner": None},
    {"team_a": "Team7", "team_b": "Team8", "seed": 11, "winner": None},
]
```

Set `TOURNAMENT_FINALIZED = True` at the top of the file.

Save the file.

---

## Step 3: Clear Stale Caches (~1 min)

Open your terminal in the BracketIQ project folder and run:

```bash
python main.py cache clear-current
```

This clears all current season data (Torvik + ESPN) but preserves the 2021-2025 historical data used for archetype matching.

You should see something like:
```
🗑️  Cleared XX current season cached files.
   Historical data (2021-2025) preserved for archetype matching.
```

---

## Step 4: Pull Fresh Data for All 68 Teams (~35 min)

Run:

```bash
python main.py rank --tournament
```

This will:
1. Pull fresh Torvik data for all 365 D1 teams
2. Pull ESPN game-by-game box scores for all 68 tournament teams
3. Compute trends, volatility, shooting splits, and close game stats
4. Build the champion archetype from historical data
5. Grade and rank all teams

**This is the slow step.** Each of the 68 teams requires ~30 ESPN API calls (one per game), with a 1-second polite delay between each. Walk away, make food, come back.

Once it finishes, all data is cached. Every subsequent command is instant.

---

## Step 5: Launch the Web UI

```bash
python -m streamlit run output/web_app.py
```

Your browser should open to `localhost:8501`.

---

## Step 6: Build Your Bracket

In the web UI:

1. **Power Rankings page:** Check "Include ESPN data" — it loads instantly from cache. Review the full rankings and tier distribution. Screenshot or download the CSV.

2. **Matchup Analyzer page:** Go matchup by matchup through the bracket. Select Team A and Team B for each first-round game, click Analyze. Read the dimension breakdown. Make your pick. Download the CSV if you want records.

3. **Team Report page:** If you're torn on a pick, pull up the detailed report for each team. Look at their strengths/weaknesses breakdown and whether they match the champion archetype.

---

## Step 7 (Optional): Between Tournament Rounds

If you want to refresh data between rounds (e.g., after the First Four, between Round 1 and Round 2):

```bash
python main.py cache clear-espn-games
python main.py rank --tournament
python -m streamlit run output/web_app.py
```

This picks up any late stat corrections. Usually unnecessary — the pre-tournament pull captures everything that matters.

---

## Quick Reference Commands

| What | Command |
|------|---------|
| Quick rankings (Torvik only) | `python main.py rank` |
| Full tournament rankings | `python main.py rank --tournament` |
| Single team deep dive | `python main.py score "Duke"` |
| Head-to-head matchup | `python main.py matchup "Duke" "Houston"` |
| Export rankings to CSV | `python main.py export --tournament` |
| Check cache status | `python main.py cache status` |
| Clear current season cache | `python main.py cache clear-current` |
| Clear everything | `python main.py cache clear` |
| Refresh all data | `python main.py refresh` |
| Launch web UI | `python -m streamlit run output/web_app.py` |