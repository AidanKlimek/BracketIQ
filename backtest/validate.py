"""
BracketIQ - Backtest Validation
==================================
Scores past tournament fields (2021-2025) to verify the model
produces sensible rankings.

Key questions:
  - Would the eventual champion have been top-tier in our model?
  - Would Final Four teams have scored well?
  - Does the model flag known upsets?

This is NOT about getting a perfect bracket retroactively.
It's about making sure the model isn't structurally broken.
"""

import logging
import pandas as pd
import numpy as np

from data.torvik_scraper import fetch_team_results
from scoring.team_grader import grade_all_teams
from config.weights import HISTORICAL_YEARS

logger = logging.getLogger(__name__)

# Champions and their seeds
CHAMPIONS = {
    2021: {"team": "Baylor", "seed": 1},
    2022: {"team": "Kansas", "seed": 1},
    2023: {"team": "Connecticut", "seed": 4},
    2024: {"team": "Connecticut", "seed": 1},
    2025: {"team": "Florida", "seed": 1},
}

# Final Four teams and seeds
FINAL_FOUR = {
    2021: [
        {"team": "Baylor", "seed": 1},
        {"team": "Gonzaga", "seed": 1},
        {"team": "Houston", "seed": 2},
        {"team": "UCLA", "seed": 11},
    ],
    2022: [
        {"team": "Kansas", "seed": 1},
        {"team": "North Carolina", "seed": 8},
        {"team": "Villanova", "seed": 2},
        {"team": "Duke", "seed": 2},
    ],
    2023: [
        {"team": "Connecticut", "seed": 4},
        {"team": "San Diego St.", "seed": 5},
        {"team": "Miami FL", "seed": 5},
        {"team": "Florida Atlantic", "seed": 9},
    ],
    2024: [
        {"team": "Connecticut", "seed": 1},
        {"team": "Purdue", "seed": 1},
        {"team": "Alabama", "seed": 1},
        {"team": "NC State", "seed": 11},
    ],
    2025: [
        {"team": "Florida", "seed": 1},
        {"team": "Houston", "seed": 1},
        {"team": "Auburn", "seed": 1},
        {"team": "Duke", "seed": 2},
    ],
}


def run_backtest() -> dict:
    """
    Run the full backtest across all historical years.

    Returns a summary dict with results per year and overall metrics.
    """
    print("🏀 BracketIQ — Backtest Validation\n")
    print("Scoring past tournament fields to validate the model...\n")

    results = {}

    for year in HISTORICAL_YEARS:
        print(f"{'='*60}")
        print(f"  {year} SEASON")
        print(f"{'='*60}")

        try:
            df = fetch_team_results(year)
            if df.empty:
                print(f"  ❌ No data for {year}")
                continue
        except Exception as e:
            print(f"  ❌ Failed to fetch {year}: {e}")
            continue

        # Grade the field
        rankings = grade_all_teams(df)
        year_result = _evaluate_year(year, rankings)
        results[year] = year_result

    # Overall summary
    _print_summary(results)
    return results


def _evaluate_year(year: int, rankings: pd.DataFrame) -> dict:
    """Evaluate model performance for a single year."""
    result = {}

    # Find champion
    champ_info = CHAMPIONS.get(year)
    if champ_info:
        champ_name = champ_info["team"]
        champ_seed = champ_info["seed"]
        champ_row = _find_team(rankings, champ_name)

        if champ_row is not None:
            rank: int = int(str(champ_row.name)) if champ_row.name is not None else 999
            composite = float(champ_row["composite"])
            tier = champ_row["tier"]
            result["champion"] = {
                "team": champ_name,
                "seed": champ_seed,
                "model_rank": rank,
                "composite": composite,
                "tier": tier,
            }
            print(f"\n  🏆 Champion: {champ_name} (#{champ_seed} seed)")
            print(f"     Model Rank: #{rank} | Score: {composite:.1f} | Tier: {tier}")

            if rank <= 5:
                print(f"     ✅ Top 5 — model correctly identified elite team")
            elif rank <= 15:
                print(f"     ⚠️  Top 15 — model had them as strong but not top tier")
            else:
                print(f"     ❌ Ranked #{rank} — model missed on this champion")
        else:
            print(f"\n  ❌ Could not find {champ_name} in rankings")
            result["champion"] = None

    # Find Final Four teams
    f4_teams = FINAL_FOUR.get(year, [])
    f4_results = []
    print(f"\n  Final Four:")

    for f4 in f4_teams:
        f4_name = f4["team"]
        f4_seed = f4["seed"]
        f4_row = _find_team(rankings, f4_name)

        if f4_row is not None:
            rank: int = int(str(f4_row.name)) if f4_row.name is not None else 999
            composite = float(f4_row["composite"])
            tier = f4_row["tier"]
            f4_results.append({
                "team": f4_name,
                "seed": f4_seed,
                "model_rank": rank,
                "composite": composite,
                "tier": tier,
            })
            flag = "✅" if rank <= 25 else "⚠️" if rank <= 50 else "❌"
            print(f"    {flag} {f4_name:<22s} Seed: {f4_seed:>2d} | "
                  f"Rank: #{rank:<3d} | Score: {composite:.1f} [{tier}]")
        else:
            print(f"    ❌ {f4_name} not found in rankings")

    result["final_four"] = f4_results

    # Top 10 that year for context
    print(f"\n  Model's Top 10 for {year}:")
    for idx, row in rankings.head(10).iterrows():
        marker = ""
        if champ_info and champ_info["team"].lower() in row["team"].lower():
            marker = " 🏆"
        for f4 in f4_teams:
            if f4["team"].lower() in row["team"].lower():
                marker = " ⭐"
                break
        print(f"    {idx:>3d}. {row['team']:<22s} {row['composite']:>5.1f} [{row['tier']}]{marker}")

    result["top_10"] = rankings.head(10)[["team", "composite", "tier"]].to_dict("records")
    return result


def _find_team(rankings: pd.DataFrame, name: str) -> pd.Series | None:
    """Find a team in rankings by partial name match."""
    mask = rankings["team"].str.lower().str.contains(name.lower(), na=False)
    if mask.any():
        return rankings[mask].iloc[0]
    # Try individual words for tricky names
    for word in name.split():
        if len(word) > 3:
            mask = rankings["team"].str.lower().str.contains(word.lower(), na=False)
            if mask.any():
                return rankings[mask].iloc[0]
    return None


def _print_summary(results: dict):
    """Print overall backtest summary."""
    print(f"\n{'='*60}")
    print(f"  BACKTEST SUMMARY")
    print(f"{'='*60}")

    champ_ranks = []
    f4_in_top25 = 0
    f4_total = 0

    for year, res in results.items():
        if res.get("champion"):
            champ_ranks.append(res["champion"]["model_rank"])
        for f4 in res.get("final_four", []):
            f4_total += 1
            if f4["model_rank"] <= 25:
                f4_in_top25 += 1

    if champ_ranks:
        avg_rank = float(np.mean(champ_ranks))
        print(f"\n  Champions:")
        print(f"    Average model rank: #{avg_rank:.1f}")
        print(f"    Ranked in top 5:    {sum(1 for r in champ_ranks if r <= 5)}/{len(champ_ranks)}")
        print(f"    Ranked in top 10:   {sum(1 for r in champ_ranks if r <= 10)}/{len(champ_ranks)}")
        print(f"    Individual ranks:   {champ_ranks}")
    else:
        avg_rank = 999.0

    if f4_total > 0:
        print(f"\n  Final Four Teams:")
        print(f"    In model's top 25:  {f4_in_top25}/{f4_total} ({f4_in_top25/f4_total*100:.0f}%)")

    print(f"\n  Interpretation:")
    if avg_rank <= 5:
        print(f"    ✅ Model consistently identifies champions as elite teams.")
    elif champ_ranks and avg_rank <= 15:
        print(f"    ⚠️  Model identifies champions as strong but not always top-tier.")
        print(f"       Consider adjusting weights to better capture what makes winners.")
    else:
        print(f"    ❌ Model struggles to identify champions. Significant tuning needed.")

    print()


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    run_backtest()
    print("✅ Backtest complete.")