"""
BracketIQ - Historical Archetype Matching
============================================
Pulls pre-tournament stats for recent champions, builds a composite
"champion profile," and scores current teams on how closely they
match that profile.

The idea: teams that LOOK like past winners statistically have a
better shot than teams that don't, even at the same overall rating.

Champions (2021-2025):
  2021: Baylor
  2022: Kansas
  2023: UConn (4-seed)
  2024: UConn (1-seed, repeat)
  2025: Florida

We use Torvik's time machine snapshots to get pre-tournament stats,
ensuring we're comparing apples to apples — what did the champion
look like BEFORE they won, not after.
"""

import logging
import numpy as np
import pandas as pd

from config.weights import (
    ARCHETYPE_DIMENSION_WEIGHTS, CHAMPION_ARCHETYPE,
    CURRENT_YEAR, HISTORICAL_YEARS,
)
from scoring.normalize import percentile_rank

logger = logging.getLogger(__name__)

# Champions and their Torvik team names
CHAMPIONS = {
    2021: "Baylor",
    2022: "Kansas",
    2023: "Connecticut",
    2024: "Connecticut",
    2025: "Florida",
}

# Final Four teams (for a broader archetype sample)
FINAL_FOUR = {
    2021: ["Baylor", "Gonzaga", "Houston", "UCLA"],
    2022: ["Kansas", "North Carolina", "Villanova", "Duke"],
    2023: ["Connecticut", "San Diego St.", "Miami FL", "Florida Atlantic"],
    2024: ["Connecticut", "Purdue", "Alabama", "NC State"],
    2025: ["Florida", "Houston", "Auburn", "Duke"],
}

# Key stats to use for archetype comparison
# These are the stats that differentiate winners from the field
ARCHETYPE_STATS = [
    "adj_o",
    "adj_d",
    "net_efficiency",
    "barthag",
    "off_efg",
    "off_to",
    "off_or",
    "def_efg",
    "def_to",
    "ft_pct",
    "three_pct",
    "sos_overall",
    "wab",
    "tempo",
]


def _standardize_historical_df(df: pd.DataFrame) -> pd.DataFrame:
    """Standardize column names for historical Torvik CSV data."""
    col_rename = {
        "adjoe": "adj_o", "adjde": "adj_d", "adjt": "adj_t",
        "adj_t": "tempo", "sos": "sos_overall",
    }
    df = df.rename(columns={k: v for k, v in col_rename.items() if k in df.columns})
    if "adj_o" in df.columns and "adj_d" in df.columns:
        if "net_efficiency" not in df.columns:
            df["net_efficiency"] = df["adj_o"] - df["adj_d"]
    return df


def build_archetype_from_data(historical_dfs: dict[int, pd.DataFrame]) -> dict[str, float]:
    """
    Build the champion archetype from actual historical data.

    Instead of guessing percentile thresholds, we pull the actual
    pre-tournament stats for each champion, convert to percentiles
    within their year's field, and average across all champions.

    Args:
        historical_dfs: Dict of {year: DataFrame} from Torvik time machine
                        or season data. Each DataFrame should have all D1 teams.

    Returns:
        Dict mapping stat_name -> average percentile across champions.
    """
    champion_profiles = []

    for year, champ_name in CHAMPIONS.items():
        if year not in historical_dfs:
            logger.warning(f"No data for {year}, skipping {champ_name}.")
            continue

        df = _standardize_historical_df(historical_dfs[year])
        profile = _get_team_percentiles(df, champ_name)

        if profile:
            champion_profiles.append(profile)
            logger.info(f"  {year} {champ_name}: "
                       f"AdjO={profile.get('adj_o', 'N/A'):.0f}%ile, "
                       f"AdjD={profile.get('adj_d', 'N/A'):.0f}%ile, "
                       f"Net={profile.get('net_efficiency', 'N/A'):.0f}%ile")
        else:
            logger.warning(f"  Could not find {champ_name} in {year} data.")

    if not champion_profiles:
        logger.error("No champion profiles built. Using fallback archetype.")
        return _fallback_archetype()

    # Average across all champions
    archetype = {}
    for stat in ARCHETYPE_STATS:
        values = [p[stat] for p in champion_profiles if stat in p and not np.isnan(p[stat])]
        if values:
            archetype[stat] = float(np.mean(values))

    logger.info(f"Built archetype from {len(champion_profiles)} champions.")
    return archetype


def build_archetype_from_f4(historical_dfs: dict[int, pd.DataFrame]) -> dict[str, float]:
    """
    Build archetype from ALL Final Four teams (broader sample).

    Using 4 teams per year x 5 years = 20 data points gives a more
    stable archetype than champions alone (5 data points).
    """
    f4_profiles = []

    for year, teams in FINAL_FOUR.items():
        if year not in historical_dfs:
            logger.warning(f"No data for {year}, skipping.")
            continue

        df = _standardize_historical_df(historical_dfs[year])
        for team_name in teams:
            profile = _get_team_percentiles(df, team_name)
            if profile:
                f4_profiles.append(profile)

    if not f4_profiles:
        return _fallback_archetype()

    archetype = {}
    for stat in ARCHETYPE_STATS:
        values = [p[stat] for p in f4_profiles if stat in p and not np.isnan(p[stat])]
        if values:
            archetype[stat] = float(np.mean(values))

    logger.info(f"Built F4 archetype from {len(f4_profiles)} teams.")
    return archetype


def score_team_similarity(
    team_percentiles: dict[str, float],
    archetype: dict[str, float],
) -> float:
    """
    Score how similar a team's profile is to the champion archetype.

    Uses weighted Euclidean distance, then converts to a 0-100 score
    where 100 = perfect match and 0 = maximally different.

    Args:
        team_percentiles: Dict of stat -> percentile for the current team.
        archetype: Dict of stat -> average percentile from champions.

    Returns:
        Similarity score (0-100).
    """
    total_distance = 0.0
    total_weight = 0.0

    for stat, archetype_value in archetype.items():
        team_value = team_percentiles.get(stat)

        if team_value is None or (isinstance(team_value, float) and np.isnan(team_value)):
            continue

        # Get dimension weight (how much this stat matters for archetype matching)
        weight = ARCHETYPE_DIMENSION_WEIGHTS.get(f"{stat}_percentile", 0.05)

        # Distance is the absolute difference in percentiles (0-100 scale)
        distance = abs(float(team_value) - archetype_value)

        total_distance += distance * weight
        total_weight += weight

    if total_weight == 0:
        return 50.0  # Neutral if no stats to compare

    # Normalize: max possible distance is 100, so weighted avg distance is 0-100
    avg_distance = total_distance / total_weight

    # Use exponential decay so teams close to archetype score much higher
    # than teams far away. Linear scoring compresses the top too much.
    # With decay factor of 0.006:
    #   distance 10 -> 94
    #   distance 20 -> 89
    #   distance 40 -> 79
    #   distance 60 -> 70
    #   distance 80 -> 62
    similarity = 100 * np.exp(-0.006 * avg_distance)

    return round(similarity, 1)


def add_archetype_scores(
    df: pd.DataFrame,
    archetype: dict[str, float],
) -> pd.DataFrame:
    """
    Add archetype similarity scores to a full team DataFrame.

    Args:
        df: DataFrame with percentile-ranked stats (post-normalization).
        archetype: Champion archetype from build_archetype_from_data().

    Returns:
        Same DataFrame with 'archetype_similarity' column added.
    """
    result = df.copy()

    scores = []
    for _, row in result.iterrows():
        team_pcts = {}
        for stat in ARCHETYPE_STATS:
            val = row.get(stat)
            if val is not None and not (isinstance(val, float) and np.isnan(val)):
                team_pcts[stat] = float(val)
        score = score_team_similarity(team_pcts, archetype)
        scores.append(score)

    result["archetype_similarity"] = scores
    logger.info(f"Added archetype scores for {len(result)} teams.")
    return result


# =============================================================================
# Helpers
# =============================================================================

def _get_team_percentiles(df: pd.DataFrame, team_name: str) -> dict[str, float] | None:
    """
    Get a team's percentile-ranked stats from a full-field DataFrame.

    Normalizes the relevant stats across the full field, then extracts
    the target team's percentiles.
    """
    # Find team name column
    team_col = None
    for candidate in ["team", "team_name", "name"]:
        if candidate in df.columns:
            team_col = candidate
            break
    if team_col is None:
        return None

    # Find the team
    mask = df[team_col].str.lower().str.contains(team_name.lower(), na=False)
    if not mask.any():
        return None

    team_idx = df[mask].index[0]

    # Polarity for normalization
    polarity = {
        "adj_o": True, "adj_d": False, "net_efficiency": True,
        "barthag": True, "off_efg": True, "off_to": False,
        "off_or": True, "def_efg": False, "def_to": True,
        "ft_pct": True, "three_pct": True, "sos_overall": True,
        "wab": True, "tempo": True,  # For archetype, treat tempo directionally
    }

    # Map common Torvik column name variants
    col_map = {
        "adjoe": "adj_o", "adjde": "adj_d", "adj_t": "tempo",
        "sos": "sos_overall",
    }

    profile = {}
    for stat in ARCHETYPE_STATS:
        # Find the actual column name in this DataFrame
        actual_col = stat
        if stat not in df.columns:
            # Try mapped names
            for raw, mapped in col_map.items():
                if mapped == stat and raw in df.columns:
                    actual_col = raw
                    break
            else:
                continue

        if actual_col not in df.columns:
            continue

        # Compute percentile rank for this stat
        higher_is_better = polarity.get(stat, True)
        pct_series = percentile_rank(df[actual_col], higher_is_better=higher_is_better)
        profile[stat] = float(pct_series.iloc[team_idx])

    return profile if profile else None


def _fallback_archetype() -> dict[str, float]:
    """
    Fallback archetype using hardcoded estimates if historical data unavailable.

    Based on general knowledge of recent champions' profiles.
    """
    return {
        "adj_o": 92.0,
        "adj_d": 90.0,
        "net_efficiency": 95.0,
        "barthag": 95.0,
        "off_efg": 75.0,
        "off_to": 70.0,
        "off_or": 50.0,
        "def_efg": 80.0,
        "def_to": 55.0,
        "ft_pct": 65.0,
        "three_pct": 60.0,
        "sos_overall": 75.0,
        "wab": 90.0,
        "tempo": 55.0,
    }


# =============================================================================
# CLI Test
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    print("🏀 BracketIQ — Archetype Builder Test\n")

    from data.torvik_scraper import fetch_team_results

    # Step 1: Try to build archetype from historical data
    print("Fetching historical data (2021-2025)...")
    print("(This may take a moment on first run)\n")

    historical = {}
    for year in HISTORICAL_YEARS:
        try:
            # Use CSV only for historical — avoids JSON merge issues on older years
            df = fetch_team_results(year)
            if not df.empty:
                historical[year] = df
                print(f"  {year}: {len(df)} teams loaded")
        except Exception as e:
            print(f"  {year}: Failed — {e}")

    if historical:
        print(f"\nBuilding champion archetype...")
        archetype = build_archetype_from_data(historical)

        print(f"\n📊 Champion Archetype Profile:")
        for stat, pct in sorted(archetype.items()):
            print(f"  {stat:<20s} {pct:>5.1f} percentile")

        # Also build F4 archetype for comparison
        print(f"\nBuilding Final Four archetype...")
        f4_archetype = build_archetype_from_f4(historical)

        print(f"\n📊 Final Four Archetype Profile:")
        for stat, pct in sorted(f4_archetype.items()):
            champ_val = archetype.get(stat, 0)
            diff = pct - champ_val
            print(f"  {stat:<20s} {pct:>5.1f}%ile  (champ diff: {diff:+.1f})")

        # Step 2: Score current teams against the archetype
        print(f"\nScoring 2026 teams against champion archetype...")
        from data.torvik_scraper import fetch_all_torvik_data
        current_df = fetch_all_torvik_data()

        # Normalize current data for comparison
        from scoring.normalize import percentile_rank as pr
        scored_df = add_archetype_scores(current_df, archetype)

        # Show top 15 by archetype similarity
        top = scored_df.nlargest(15, "archetype_similarity")[
            ["team", "archetype_similarity", "adj_o", "adj_d"]
        ]
        print(f"\n  Top 15 by Archetype Similarity:")
        for _, row in top.iterrows():
            print(f"    {row['team']:<22s} Similarity: {row['archetype_similarity']:>5.1f}")

    else:
        print("\nNo historical data available. Using fallback archetype.")
        archetype = _fallback_archetype()
        print(f"  Fallback: {archetype}")

    print("\n✅ Archetype test complete.")