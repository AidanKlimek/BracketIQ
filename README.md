# 🏀 BracketIQ

A data-driven March Madness bracket tool that goes beyond the four factors.

BracketIQ combines team efficiency metrics, strength of schedule, trend analysis, historical archetype matching, and upset profiling to score and rank NCAA tournament teams — then provides head-to-head matchup analysis for building your bracket.

## How It Works

### Tool 1: Team Scoring Algorithm
Every D1 team receives a composite score (0–100) built from three weighted tiers:

| Tier | Weight | What It Captures |
|------|--------|------------------|
| **Base Layer** | 40% | Adjusted efficiency, four factors, shooting splits |
| **Context Layer** | 35% | Strength of schedule, recent trends, volatility, resume quality |
| **Tournament Layer** | 25% | Historical archetype matching, upset profile, FT reliability, seed |

### Tool 2: Matchup Analyzer
Feed in two teams and get a head-to-head breakdown that adjusts raw scores based on stylistic interaction — pace mismatch, perimeter vs. interior, turnover battle, and more.

## Data Sources

- **[Bart Torvik (T-Rank)](https://barttorvik.com)** — Adjusted efficiency, four factors, SOS, tempo
- **[ESPN](https://www.espn.com/mens-college-basketball/)** — Box scores, game-level stats (bench points, paint points, fast break points, points off turnovers)

## Quick Start

### Prerequisites
- Python 3.10+
- pip

### Installation

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/bracketiq.git
cd bracketiq

# Create virtual environment
python -m venv venv
source venv/bin/activate        # macOS/Linux
# venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your preferences (no API keys needed)
```

### Usage

```bash
# Generate full power rankings
python main.py rank

# Score a specific team
python main.py score "Duke"

# Run a matchup analysis
python main.py matchup "Duke" "North Carolina"

# Launch the web UI
streamlit run output/web_app.py

# Export rankings to CSV
python main.py export

# Backtest against past tournaments
python main.py backtest
```

## Project Structure

```
bracketiq/
├── config/
│   └── weights.py              # All weights, thresholds, tier definitions
├── data/
│   ├── torvik_scraper.py       # Pulls adjusted stats from Bart Torvik
│   ├── espn_scraper.py         # Pulls raw team stats from ESPN API
│   ├── historical.py           # Pulls 5 years of tournament results
│   └── cache/                  # Local data cache (gitignored)
├── scoring/
│   ├── normalize.py            # Z-scores / percentile ranking
│   ├── team_grader.py          # Composite scoring engine
│   ├── trend.py                # Recent form / volatility calculations
│   └── archetype.py            # Historical winner profile matching
├── matchup/
│   ├── analyzer.py             # Head-to-head style comparison
│   └── upset_factor.py         # Upset likelihood scoring
├── output/
│   ├── csv_export.py           # Export rankings to CSV
│   └── web_app.py              # Streamlit web UI
├── backtest/
│   └── validate.py             # Score past winners, compare to field
├── main.py                     # CLI entry point
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## Configuration

All scoring weights live in `config/weights.py`. The model uses three tiers with adjustable sub-weights. Tweak any value and rerun — everything recalculates automatically. See the config file for detailed documentation on every parameter.

## Backtesting

BracketIQ includes a validation module that scores past tournament fields (2021–2025) to verify the model produces sensible rankings. It checks whether eventual champions scored in the top tier and whether flagged upsets actually occurred.

## Disclaimer

This tool is for entertainment and personal bracket-building purposes. It will not produce a perfect bracket — nothing can. The goal is to give you better decision points than raw efficiency rankings alone.

## Contributing

Contributions welcome! If you have ideas for new stats, better weight tuning, or improved data sources, open an issue or PR.

## License

MIT