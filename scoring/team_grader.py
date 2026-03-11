"""
BracketIQ - Team Grading Engine
==================================
The core scoring algorithm. Takes normalized stats from Torvik and ESPN,
applies the three-tier weighting system, and produces a composite score
(0-100) for every team.

Tiers:
  Base (40%)       — Efficiency, shooting, four factors
  Context (35%)    — SOS, trends, volatility, resume
  Tournament (25%) — Archetype, upset profile, FT reliability, seed
"""

import logging
import pandas as pd
import numpy as np

from config.weights import (
    TIER_WEIGHTS, BASE_WEIGHTS, CONTEXT_WEIGHTS, TOURNAMENT_WEIGHTS,
    STAT_POLARITY, OUTPUT_CONFIG,
)
from scoring.normalize import percentile_rank

logger = logging.getLogger(__name__)


# =============================================================================
# Column Mapping: Torvik raw names -> our internal stat names
# =============================================================================
# Torvik's columns don't always match our config names exactly.
# This maps what Torvik gives us to what our weights expect.

TORVIK_COLUMN_MAP = {
    # Base layer
    "adj_o": "adj_o",
    "adj_d": "adj_d",
    "net_efficiency": "net_efficiency",
    "barthag": "barthag",
    "opp_oe": "opp_oe",              # Opponent offensive efficiency
    "opp_de": "opp_de",              # Opponent defensive efficiency

    # Context layer
    "sos": "sos_overall",
    "ncsos": "sos_noncon",
    "elite_sos": "sos_elite",
    "elite_noncon_sos": "sos_elite_noncon",
    "wab": "wab",
    "qual_o": "qual_o",              # Quality offense rating
    "qual_d": "qual_d",              # Quality defense rating
    "qual_games": "qual_games",      # Number of quality games
    "qual_barthag": "qual_barthag",  # Barthag in quality games

    # Tournament layer
    "adj_t": "tempo",
    "seed": "seed",
}

# ESPN aggregate stat names -> our internal stat names
ESPN_COLUMN_MAP = {
    "three_pct": "three_pct",
    "ft_pct": "ft_pct",
    "fg_pct": "fg_pct",
    "avg_turnoverPoints": "avg_turnover_points",
    "avg_fastBreakPoints": "avg_fast_break_points",
    "avg_pointsInPaint": "avg_paint_points",
    "avg_largestLead": "avg_largest_lead",
    "avg_totalTurnovers": "avg_turnovers",
    "avg_assists": "avg_assists",
    "avg_steals": "avg_steals",
    "avg_blocks": "avg_blocks",
    "avg_offensiveRebounds": "avg_off_rebounds",
    "avg_defensiveRebounds": "avg_def_rebounds",
    "ft_pct_std": "ft_consistency",
    "std_margin": "volatility_scoring",
    "close_game_record": "close_game_record",
}


def map_torvik_columns(torvik_df: pd.DataFrame) -> pd.DataFrame:
    """Rename Torvik columns to our internal stat names."""
    rename = {k: v for k, v in TORVIK_COLUMN_MAP.items() if k in torvik_df.columns}
    return torvik_df.rename(columns=rename)


def map_espn_columns(espn_stats: dict) -> dict:
    """Rename ESPN stat keys to our internal stat names."""
    return {ESPN_COLUMN_MAP.get(k, k): v for k, v in espn_stats.items()}


# =============================================================================
# Percentile Normalization for All Stats
# =============================================================================

def normalize_all_stats(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize all scoreable stats to percentile ranks (0-100).

    Uses STAT_POLARITY to determine direction. Columns not in
    STAT_POLARITY are left as-is.
    """
    result = df.copy()

    all_weight_stats = set(BASE_WEIGHTS.keys()) | set(CONTEXT_WEIGHTS.keys()) | set(TOURNAMENT_WEIGHTS.keys())

    normalized_count = 0
    for col in all_weight_stats:
        if col not in result.columns:
            continue

        polarity = STAT_POLARITY.get(col)
        if polarity is None:
            # Neutral stat — skip normalization
            continue

        # Save raw value
        result[f"{col}_raw"] = result[col]
        result[col] = percentile_rank(result[col], higher_is_better=polarity)
        normalized_count += 1

    logger.info(f"Normalized {normalized_count} stat columns to percentiles.")
    return result


# =============================================================================
# Tier Scoring
# =============================================================================

def score_tier(row: pd.Series, weights: dict) -> tuple[float, dict]:
    """
    Calculate a tier score for a single team.

    Args:
        row: Team's percentile-ranked stats (one row from normalized DataFrame).
        weights: Sub-weight dict for this tier (e.g., BASE_WEIGHTS).

    Returns:
        Tuple of (tier_score 0-100, breakdown dict showing each stat's contribution).
    """
    total_score = 0.0
    total_weight_used = 0.0
    breakdown = {}

    for stat, weight in weights.items():
        value = row.get(stat)

        # Skip missing stats
        if value is None or (isinstance(value, float) and np.isnan(value)):
            breakdown[stat] = {"value": None, "weight": weight, "contribution": 0}
            continue

        value = float(value)
        contribution = value * weight
        total_score += contribution
        total_weight_used += weight
        breakdown[stat] = {
            "value": round(float(value), 1),
            "weight": weight,
            "contribution": round(contribution, 2),
        }

    # Redistribute weight from missing stats proportionally
    if total_weight_used > 0 and total_weight_used < 1.0:
        scale_factor = 1.0 / total_weight_used
        total_score *= scale_factor

    return round(total_score, 2), breakdown


def grade_team(row: pd.Series) -> dict:
    """
    Calculate the full composite grade for a single team.

    Returns a dict with:
        - composite: Final 0-100 score
        - tier: Letter tier (S/A/B/C/D/F)
        - base_score, context_score, tournament_score: Per-tier scores
        - breakdown: Detailed per-stat contributions
    """
    base_score, base_breakdown = score_tier(row, BASE_WEIGHTS)
    context_score, context_breakdown = score_tier(row, CONTEXT_WEIGHTS)
    tournament_score, tournament_breakdown = score_tier(row, TOURNAMENT_WEIGHTS)

    # Weighted composite
    composite = (
        base_score * TIER_WEIGHTS["base"] +
        context_score * TIER_WEIGHTS["context"] +
        tournament_score * TIER_WEIGHTS["tournament"]
    )

    # Clamp to 0-100
    composite = max(0, min(100, composite))

    # Assign letter tier
    tier_label = "F"
    for (low, high), label in OUTPUT_CONFIG["tier_labels"].items():
        if low <= composite <= high:
            tier_label = label
            break

    return {
        "composite": round(composite, 1),
        "tier": tier_label,
        "base_score": round(base_score, 1),
        "context_score": round(context_score, 1),
        "tournament_score": round(tournament_score, 1),
        "breakdown": {
            "base": base_breakdown,
            "context": context_breakdown,
            "tournament": tournament_breakdown,
        },
    }


# =============================================================================
# Full Field Grading
# =============================================================================

def grade_all_teams(torvik_df: pd.DataFrame, espn_data: dict | None = None) -> pd.DataFrame:
    """
    Grade every team in the dataset.

    Args:
        torvik_df: Raw Torvik DataFrame (will be mapped and normalized internally).
        espn_data: Optional dict of {team_name: aggregated_espn_stats}.
                   If provided, ESPN stats are merged before grading.

    Returns:
        DataFrame with columns: team, composite, tier, base_score,
        context_score, tournament_score, plus all raw/percentile stats.
    """
    logger.info("Grading all teams...")

    # Step 1: Map Torvik columns to internal names
    df = map_torvik_columns(torvik_df)

    # Step 2: Merge ESPN data if available
    if espn_data:
        logger.info(f"Merging ESPN data for {len(espn_data)} teams...")
        for team_name, stats in espn_data.items():
            mapped_stats = map_espn_columns(stats)
            # Find matching row in df
            mask = df["team"].str.lower().str.contains(team_name.lower(), na=False)
            if mask.any():
                idx = df[mask].index[0]
                for key, value in mapped_stats.items():
                    if key not in df.columns:
                        df[key] = np.nan
                    df.at[idx, key] = value

    # Step 3: Add archetype similarity scores
    try:
        from scoring.archetype import build_archetype_from_data, add_archetype_scores
        from data.torvik_scraper import fetch_team_results
        from config.weights import HISTORICAL_YEARS

        historical = {}
        for year in HISTORICAL_YEARS:
            try:
                hist_df = fetch_team_results(year)
                if not hist_df.empty:
                    historical[year] = hist_df
            except Exception:
                pass

        if historical:
            archetype = build_archetype_from_data(historical)
            if archetype:
                # Normalize first so archetype can compare percentiles
                temp_df = normalize_all_stats(df)
                temp_df = add_archetype_scores(temp_df, archetype)
                df["archetype_similarity"] = temp_df["archetype_similarity"]
                logger.info("Archetype scores added to grading.")
    except Exception as e:
        logger.warning(f"Archetype scoring skipped: {e}")

    # Step 4: Normalize all stats to percentiles
    df = normalize_all_stats(df)

    # Step 4: Grade each team
    grades = []
    for idx, row in df.iterrows():
        grade = grade_team(row)
        grades.append({
            "team": row.get("team", "Unknown"),
            "conf": row.get("conf", ""),
            "composite": grade["composite"],
            "tier": grade["tier"],
            "base_score": grade["base_score"],
            "context_score": grade["context_score"],
            "tournament_score": grade["tournament_score"],
        })

    grades_df = pd.DataFrame(grades)
    grades_df = grades_df.sort_values("composite", ascending=False).reset_index(drop=True)
    grades_df.index = grades_df.index + 1  # 1-indexed ranking
    grades_df.index.name = "rank"

    logger.info(f"Graded {len(grades_df)} teams.")
    return grades_df


def get_team_report(team_name: str, torvik_df: pd.DataFrame) -> dict | None:
    """
    Generate a detailed scoring report for a single team.

    Shows composite score, tier breakdown, and per-stat contributions.
    Useful for understanding WHY a team got its score.
    """
    df = map_torvik_columns(torvik_df)
    df = normalize_all_stats(df)

    mask = df["team"].str.lower().str.contains(team_name.lower(), na=False)
    matches = df[mask]

    if matches.empty:
        logger.warning(f"No team found matching '{team_name}'")
        return None

    row = matches.iloc[0]
    grade = grade_team(row)
    grade["team"] = row.get("team", team_name)
    grade["conf"] = row.get("conf", "")

    return grade


def print_team_report(report: dict) -> None:
    """Pretty-print a team's scoring report."""
    if not report:
        print("No report available.")
        return

    team = report["team"]
    conf = report.get("conf", "")
    print(f"\n{'='*60}")
    print(f"  {team} ({conf})")
    print(f"  Composite Score: {report['composite']} — Tier: {report['tier']}")
    print(f"{'='*60}")
    print(f"  Base Layer:       {report['base_score']:>5.1f} / 100  (weight: {TIER_WEIGHTS['base']*100:.0f}%)")
    print(f"  Context Layer:    {report['context_score']:>5.1f} / 100  (weight: {TIER_WEIGHTS['context']*100:.0f}%)")
    print(f"  Tournament Layer: {report['tournament_score']:>5.1f} / 100  (weight: {TIER_WEIGHTS['tournament']*100:.0f}%)")

    # Show top contributors and weaknesses in each tier
    for tier_name, tier_breakdown in report["breakdown"].items():
        available = {k: v for k, v in tier_breakdown.items() if v["value"] is not None}
        if not available:
            continue

        sorted_stats = sorted(available.items(), key=lambda x: x[1]["contribution"], reverse=True)

        print(f"\n  {tier_name.upper()} — Top Strengths:")
        for stat, info in sorted_stats[:3]:
            print(f"    {stat:<30s} {info['value']:>5.1f}%ile  (contributes {info['contribution']:>5.1f})")

        print(f"  {tier_name.upper()} — Weaknesses:")
        for stat, info in sorted_stats[-3:]:
            print(f"    {stat:<30s} {info['value']:>5.1f}%ile  (contributes {info['contribution']:>5.1f})")

    print()


# =============================================================================
# CLI Test
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    print("🏀 BracketIQ — Team Grader Test\n")

    from data.torvik_scraper import fetch_all_torvik_data

    print("Fetching data...")
    torvik_df = fetch_all_torvik_data()

    # Grade all teams
    print("\nGrading all teams...")
    rankings = grade_all_teams(torvik_df)

    # Show top 25
    print(f"\n{'='*60}")
    print(f"  BracketIQ Power Rankings — Top 25")
    print(f"{'='*60}")
    top25 = rankings.head(25)
    for idx, row in top25.iterrows():
        print(f"  {idx:>3d}. {row['team']:<22s} {row['composite']:>5.1f}  [{row['tier']}]  "
              f"(B:{row['base_score']:>4.1f} C:{row['context_score']:>4.1f} T:{row['tournament_score']:>4.1f})")

    # Detailed reports for a few teams
    print("\n" + "="*60)
    print("  Detailed Team Reports")
    print("="*60)

    for name in ["Duke", "Houston", "Drake"]:
        report = get_team_report(name, torvik_df)
        if report:
            print_team_report(report)

    # Show tier distribution
    print(f"\nTier Distribution:")
    for tier in ["S", "A", "B", "C", "D", "F"]:
        count = len(rankings[rankings["tier"] == tier])
        bar = "█" * count
        print(f"  {tier}: {count:>3d} {bar}")

    print("\n✅ Team grader test complete.")