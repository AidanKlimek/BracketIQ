"""
BracketIQ - Normalization Engine
===================================
Converts raw stats from Torvik and ESPN into percentile ranks (0-100)
so they can be combined with weights in the scoring engine.

Why percentiles instead of z-scores?
  - Percentiles are bounded (0-100), so no single stat can blow up the score
  - They're intuitive: 90th percentile means better than 90% of teams
  - They handle non-normal distributions (like SOS) gracefully

We normalize against the full D1 field (363+ teams), not just the 68
tournament teams, because that gives a truer picture of where teams sit.
"""

import logging
import pandas as pd
import numpy as np
from scipy import stats as scipy_stats

from config.weights import STAT_POLARITY

logger = logging.getLogger(__name__)


def percentile_rank(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    """
    Convert a Series of raw values to percentile ranks (0-100).

    Args:
        series: Raw stat values (one per team).
        higher_is_better: If True, highest value = 100th percentile.
                          If False, lowest value = 100th percentile (e.g., defensive stats).

    Returns:
        Series of percentile ranks (0-100), same index as input.
    """
    # Drop NaNs for ranking, then map back
    valid = series.dropna()
    if valid.empty:
        return pd.Series(np.nan, index=series.index)

    # Rank using average method for ties
    if higher_is_better:
        ranks = valid.rank(method="average", ascending=True)
    else:
        ranks = valid.rank(method="average", ascending=False)

    # Convert ranks to percentiles (0-100)
    percentiles = (ranks - 1) / (len(valid) - 1) * 100 if len(valid) > 1 else pd.Series(50.0, index=valid.index)

    # Map back to original index (NaN stays NaN)
    result = pd.Series(np.nan, index=series.index)
    result[valid.index] = percentiles

    return result


def normalize_dataframe(df: pd.DataFrame, stat_columns: list[str] | None = None) -> pd.DataFrame:
    """
    Normalize specified columns in a DataFrame to percentile ranks.

    Uses STAT_POLARITY from config to determine direction for each stat.
    Stats not in STAT_POLARITY default to higher_is_better=True.
    Stats with polarity=None (like tempo) are left as raw values.

    Args:
        df: DataFrame with raw stats (one row per team).
        stat_columns: List of column names to normalize.
                      If None, normalizes all numeric columns.

    Returns:
        New DataFrame with same structure but percentile-ranked values.
        Original columns are preserved with '_raw' suffix.
    """
    if stat_columns is None:
        stat_columns = df.select_dtypes(include=[np.number]).columns.tolist()

    result = df.copy()

    normalized_count = 0
    skipped = []

    for col in stat_columns:
        if col not in df.columns:
            skipped.append(col)
            continue

        # Check polarity
        polarity = STAT_POLARITY.get(col)

        if polarity is None:
            # Neutral stat (like tempo) — keep raw value
            logger.debug(f"Skipping {col} (neutral polarity)")
            continue

        # Preserve raw value
        result[f"{col}_raw"] = df[col]

        # Normalize
        result[col] = percentile_rank(df[col], higher_is_better=polarity)
        normalized_count += 1

    if skipped:
        logger.debug(f"Columns not found in data: {skipped}")

    logger.info(f"Normalized {normalized_count} columns to percentile ranks.")
    return result


def normalize_torvik(torvik_df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize Torvik data specifically.

    Handles the known Torvik columns and their polarities.
    """
    # Columns we want to normalize from Torvik data
    torvik_stats = [
        "adj_o", "adj_d", "barthag",
        "off_efg", "off_to", "off_or", "off_ftr",
        "def_efg", "def_to", "def_or", "def_ftr",
        "net_efficiency",
    ]

    # Filter to columns that actually exist in this dataset
    available = [col for col in torvik_stats if col in torvik_df.columns]

    if not available:
        logger.warning("No recognized Torvik stat columns found. Returning raw data.")
        return torvik_df

    return normalize_dataframe(torvik_df, stat_columns=available)


def normalize_espn_aggregates(espn_stats: dict, all_teams_stats: list[dict]) -> dict:
    """
    Normalize a single team's ESPN aggregated stats against the full field.

    Since ESPN data comes as per-team dicts (from aggregate_season_stats),
    not a DataFrame, this function takes one team's stats and the full
    list of all teams' stats, builds a temporary DataFrame, normalizes,
    and returns the percentile-ranked values for the target team.

    Args:
        espn_stats: Single team's aggregated stats dict.
        all_teams_stats: List of all teams' aggregated stats dicts.

    Returns:
        Dict with percentile-ranked values for the target team.
    """
    if not all_teams_stats:
        return espn_stats

    # Build DataFrame from all teams
    df = pd.DataFrame(all_teams_stats)

    # Find the target team's index
    # We'll add it to the end if it's not already in the list
    target_idx = len(df)
    target_row = pd.DataFrame([espn_stats])
    df = pd.concat([df, target_row], ignore_index=True)

    # ESPN stats and their polarity (higher = better unless noted)
    espn_polarity = {
        "avg_turnoverPoints": True,       # More pts off opponent TOs = better
        "avg_fastBreakPoints": True,
        "avg_pointsInPaint": True,
        "avg_largestLead": True,
        "avg_totalTurnovers": False,      # Fewer own turnovers = better
        "avg_assists": True,
        "avg_steals": True,
        "avg_blocks": True,
        "avg_offensiveRebounds": True,
        "avg_defensiveRebounds": True,
        "avg_totalRebounds": True,
        "ft_pct": True,
        "three_pct": True,
        "fg_pct": True,
        "ft_pct_std": False,              # Lower FT volatility = better
        "std_margin": False,              # Lower scoring volatility = better
        "std_score": False,               # More consistent scoring = better
        "close_game_record": True,
        "avg_margin": True,
        "win_pct": True,
    }

    # Normalize available columns
    for col, higher_is_better in espn_polarity.items():
        if col in df.columns:
            df[col] = percentile_rank(df[col], higher_is_better=higher_is_better)

    # Extract the target team's row
    result = df.iloc[target_idx].to_dict()
    return result


def get_team_percentiles(torvik_df: pd.DataFrame, team_name: str) -> dict:
    """
    Quick lookup: get all percentile-ranked stats for a specific team.

    Args:
        torvik_df: Raw Torvik DataFrame (will be normalized internally).
        team_name: Team name to look up (partial match).

    Returns:
        Dict of stat_name -> percentile_value for the matched team.
    """
    normalized = normalize_torvik(torvik_df)

    # Find team (case-insensitive partial match)
    mask = normalized["team"].str.lower().str.contains(team_name.lower(), na=False)
    matches = normalized[mask]

    if matches.empty:
        logger.warning(f"No team found matching '{team_name}'")
        return {}

    team_row = matches.iloc[0]

    # Build result dict with both raw and percentile values
    result = {"team": team_row.get("team", team_name)}

    for col in normalized.columns:
        if col.endswith("_raw"):
            base = col.replace("_raw", "")
            result[f"{base}_percentile"] = team_row.get(base)
            result[f"{base}_raw"] = team_row.get(col)

    return result


# =============================================================================
# CLI Test
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    print("🏀 BracketIQ — Normalization Engine Test\n")

    # Pull Torvik data
    from data.torvik_scraper import fetch_all_torvik_data

    print("Fetching Torvik data...")
    raw_df = fetch_all_torvik_data()
    print(f"  {len(raw_df)} teams loaded.\n")

    # Normalize
    print("Normalizing...")
    norm_df = normalize_torvik(raw_df)

    # Show a few examples
    test_teams = ["Duke", "Houston", "Gonzaga", "Drake"]
    for name in test_teams:
        pcts = get_team_percentiles(raw_df, name)
        if pcts:
            team = pcts.get("team", name)
            adj_o_p = pcts.get("adj_o_percentile", "N/A")
            adj_d_p = pcts.get("adj_d_percentile", "N/A")
            adj_o_r = pcts.get("adj_o_raw", "N/A")
            adj_d_r = pcts.get("adj_d_raw", "N/A")
            net_p = pcts.get("net_efficiency_percentile", "N/A")

            def _f(v):
                return f"{v:.1f}" if isinstance(v, (int, float)) else "N/A"

            print(f"  {team:<20s} AdjO: {_f(adj_o_r):>6s} ({_f(adj_o_p):>5s}%ile)  "
                  f"AdjD: {_f(adj_d_r):>6s} ({_f(adj_d_p):>5s}%ile)  "
                  f"Net: ({_f(net_p):>5s}%ile)")

    # Sanity check: top 10 by net efficiency percentile
    print(f"\n  Top 10 by Net Efficiency Percentile:")
    if "net_efficiency" in norm_df.columns:
        top = norm_df.nlargest(10, "net_efficiency")[["team", "net_efficiency", "adj_o", "adj_d"]]
        top.columns = ["Team", "Net %ile", "AdjO %ile", "AdjD %ile"]
        print(top.to_string(index=False))

    print("\n✅ Normalization test complete.")