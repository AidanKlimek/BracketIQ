"""
BracketIQ - Data Integrator
===============================
Merges Torvik season stats with ESPN game-by-game derived stats
into a single comprehensive DataFrame ready for the team grader.

This is the bridge between raw data and scoring. It:
  1. Pulls Torvik data (adjusted efficiency, SOS, WAB, etc.)
  2. For each team, pulls ESPN box scores and computes trends/volatility
  3. Merges everything into one row per team
  4. Passes the merged data to the grader

The ESPN pull is the slow part (~30 sec per team due to polite delays).
For the full 68 tournament teams, expect ~35 minutes on first run.
All data is cached, so subsequent runs are near-instant.
"""

import logging
import pandas as pd
import numpy as np

from data.torvik_scraper import fetch_all_torvik_data
from data.espn_scraper import (
    fetch_teams,
    find_espn_id,
    fetch_team_season_boxscores,
)
from scoring.trend import compute_all_espn_stats

from config.weights import CURRENT_YEAR

logger = logging.getLogger(__name__)


def build_full_dataset(
    team_names: list[str] | None = None,
    year: int | None = None,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """
    Build the complete dataset by merging Torvik + ESPN data.

    Args:
        team_names: List of team names to pull ESPN data for.
                    If None, only Torvik data is used (fast, but partial).
                    Pass tournament team names for full scoring.
        year: Season year. Defaults to CURRENT_YEAR.
        force_refresh: Bypass all caches.

    Returns:
        DataFrame with one row per team, all available stats merged.
    """
    if year is None:
        year = CURRENT_YEAR

    # Step 1: Torvik base data (all 365 teams, fast)
    logger.info("Loading Torvik data...")
    torvik_df = fetch_all_torvik_data(year, force_refresh)
    logger.info(f"  Torvik: {len(torvik_df)} teams, {len(torvik_df.columns)} columns.")

    # If no ESPN teams requested, return Torvik only
    if not team_names:
        return torvik_df

    # Step 2: ESPN game-by-game data for requested teams
    logger.info(f"Loading ESPN data for {len(team_names)} teams...")
    espn_teams_df = fetch_teams(force_refresh)
    espn_stats = {}

    for i, name in enumerate(team_names):
        logger.info(f"  [{i+1}/{len(team_names)}] Processing {name}...")

        espn_id = find_espn_id(name, espn_teams_df)
        if espn_id is None:
            logger.warning(f"    Could not find ESPN ID for '{name}', skipping.")
            continue

        # Pull all game box scores
        game_df = fetch_team_season_boxscores(espn_id, year, force_refresh)
        if game_df.empty:
            logger.warning(f"    No box score data for '{name}', skipping.")
            continue

        # Compute all ESPN-derived stats
        stats = compute_all_espn_stats(game_df)
        if stats:
            espn_stats[name] = stats
            logger.info(f"    Got {len(stats)} stats from {len(game_df)} games.")

    # Step 3: Merge ESPN stats into Torvik DataFrame
    if espn_stats:
        torvik_df = _merge_espn_into_torvik(torvik_df, espn_stats)

    logger.info(f"Final dataset: {len(torvik_df)} teams, {len(torvik_df.columns)} columns.")
    return torvik_df


def _merge_espn_into_torvik(torvik_df: pd.DataFrame, espn_stats: dict[str, dict]) -> pd.DataFrame:
    """
    Merge ESPN-derived stats into the Torvik DataFrame.

    Matches teams by name (fuzzy) and adds ESPN columns.
    Teams without ESPN data get NaN for those columns.
    """
    df = torvik_df.copy()

    # Initialize ESPN columns with NaN
    all_espn_keys: set[str] = set()
    for stats in espn_stats.values():
        all_espn_keys.update(stats.keys())

    for key in all_espn_keys:
        if key not in df.columns:
            df[key] = np.nan

    # Match and merge
    matched = 0
    for team_name, stats in espn_stats.items():
        # Find the matching row in Torvik data
        mask = df["team"].str.lower().str.contains(team_name.lower(), na=False)

        if not mask.any():
            # Try partial matching
            for word in team_name.split():
                if len(word) > 3:
                    mask = df["team"].str.lower().str.contains(word.lower(), na=False)
                    if mask.any():
                        break

        if mask.any():
            idx = df[mask].index[0]
            for key, value in stats.items():
                df.at[idx, key] = value
            matched += 1
        else:
            logger.warning(f"Could not match ESPN data for '{team_name}' to Torvik.")

    logger.info(f"Merged ESPN data: {matched}/{len(espn_stats)} teams matched.")
    return df


def get_tournament_teams(torvik_df: pd.DataFrame) -> list[str]:
    """
    Extract likely tournament teams from Torvik data.

    Torvik includes a 'seed' column for tournament teams.
    If seeds aren't set yet, falls back to top 68 by WAB.
    """
    if "seed" in torvik_df.columns:
        seeded = torvik_df[torvik_df["seed"].notna() & (torvik_df["seed"] > 0)]
        if len(seeded) >= 30:
            return seeded["team"].tolist()

    # Fallback: top 68 by WAB (or barthag if WAB unavailable)
    if "wab" in torvik_df.columns:
        return torvik_df.nlargest(68, "wab")["team"].tolist()
    elif "barthag" in torvik_df.columns:
        return torvik_df.nlargest(68, "barthag")["team"].tolist()
    else:
        return torvik_df.head(68)["team"].tolist()


# =============================================================================
# CLI Test
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    print("🏀 BracketIQ — Data Integrator Test\n")

    # Test with a small set of teams (3 for speed)
    test_teams = ["Duke", "Houston", "Drake"]

    print(f"Building full dataset for {test_teams}...\n")
    df = build_full_dataset(team_names=test_teams)

    # Check which ESPN columns made it in
    espn_cols = [c for c in df.columns if any(
        c.startswith(prefix) for prefix in ["trend_", "volatility_", "close_", "avg_", "ft_pct", "three_pct", "fg_pct", "off_ftr"]
    )]
    print(f"ESPN-derived columns added: {len(espn_cols)}")
    print(f"  {sorted(espn_cols)}\n")

    # Show merged data for test teams
    for name in test_teams:
        mask = df["team"].str.lower().str.contains(name.lower(), na=False)
        if mask.any():
            row = df[mask].iloc[0]

            def _f(val):
                if isinstance(val, float) and not np.isnan(val):
                    return f"{val:.3f}"
                return "N/A"

            def _f1(val):
                if isinstance(val, float) and not np.isnan(val):
                    return f"{val:.1f}"
                return "N/A"

            def _ft(val):
                if isinstance(val, float) and not np.isnan(val):
                    return f"{val:+.1f}"
                return "N/A"

            print(f"  {row['team']}:")
            print(f"    Torvik — AdjO: {row.get('adj_o', 'N/A'):.1f}, AdjD: {row.get('adj_d', 'N/A'):.1f}")
            print(f"    ESPN  — FT%: {_f(row.get('ft_pct'))}, "
                  f"3PT%: {_f(row.get('three_pct'))}, "
                  f"Volatility: {_f1(row.get('volatility_scoring'))}, "
                  f"Trend: {_ft(row.get('trend_scoring_margin'))}, "
                  f"Close: {_f(row.get('close_game_record'))}")
        print()

    # Now grade with full data
    print("Grading with merged data...")
    from scoring.team_grader import grade_all_teams
    rankings = grade_all_teams(df)

    print(f"\nTop 10:")
    for idx, row in rankings.head(10).iterrows():
        print(f"  {idx:>3d}. {row['team']:<22s} {row['composite']:>5.1f}  [{row['tier']}]  "
              f"(B:{row['base_score']:>4.1f} C:{row['context_score']:>4.1f} T:{row['tournament_score']:>4.1f})")

    print("\n✅ Integration test complete.")