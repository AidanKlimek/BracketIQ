"""
BracketIQ - Matchup Analyzer
================================
Takes two teams and produces a head-to-head breakdown.

This goes beyond raw composite scores by asking: how do these two
teams' STYLES interact? A team's strengths matter more or less
depending on what the opponent is weak at.

Key matchup dimensions:
  1. Pace mismatch — who controls tempo?
  2. Offensive strength vs defensive strength
  3. Turnover battle — creation vs protection
  4. Rebounding edge
  5. Three-point variance — can the underdog get hot?
  6. Free throw reliability in a close game projection
  7. Trend momentum — who's peaking?
"""

import logging
import math
import numpy as np
import pandas as pd

from config.weights import CURRENT_YEAR

logger = logging.getLogger(__name__)

# Sentinel value for missing stats (avoids None math issues)
_MISSING = float("nan")


def analyze_matchup(
    team_a: dict,
    team_b: dict,
    composite_a: float | None = None,
    composite_b: float | None = None,
) -> dict:
    """
    Run a full head-to-head matchup analysis.

    Args:
        team_a: Dict of all stats for team A (raw + ESPN-derived).
        team_b: Dict of all stats for team B (raw + ESPN-derived).
        composite_a: Team A's composite score from the grader (optional).
        composite_b: Team B's composite score from the grader (optional).

    Returns:
        Dict with matchup breakdown, adjustments, and projected edge.
    """
    result = {
        "team_a": _get_name(team_a),
        "team_b": _get_name(team_b),
        "composite_a": composite_a,
        "composite_b": composite_b,
        "raw_edge": (composite_a or 0) - (composite_b or 0),
        "dimensions": {},
        "adjustments": {},
    }

    # Run each matchup dimension
    result["dimensions"]["pace"] = _pace_matchup(team_a, team_b)
    result["dimensions"]["offense_vs_defense"] = _off_def_matchup(team_a, team_b)
    result["dimensions"]["turnover_battle"] = _turnover_matchup(team_a, team_b)
    result["dimensions"]["rebounding"] = _rebounding_matchup(team_a, team_b)
    result["dimensions"]["three_point"] = _three_point_matchup(team_a, team_b)
    result["dimensions"]["free_throws"] = _free_throw_matchup(team_a, team_b)
    result["dimensions"]["momentum"] = _momentum_matchup(team_a, team_b)

    # Calculate net adjustment from matchup dimensions
    total_adj = 0.0
    for dim_name, dim_result in result["dimensions"].items():
        adj = dim_result.get("adjustment", 0.0)
        total_adj += adj

    result["net_adjustment"] = round(total_adj, 1)
    result["adjusted_edge"] = round(result["raw_edge"] + total_adj, 1)

    # Determine pick
    if result["adjusted_edge"] > 0:
        result["pick"] = _get_name(team_a)
        result["confidence"] = _edge_to_confidence(result["adjusted_edge"])
    elif result["adjusted_edge"] < 0:
        result["pick"] = _get_name(team_b)
        result["confidence"] = _edge_to_confidence(abs(result["adjusted_edge"]))
    else:
        result["pick"] = "Toss-up"
        result["confidence"] = "Low"

    return result


# =============================================================================
# Matchup Dimensions
# =============================================================================

def _pace_matchup(a: dict, b: dict) -> dict:
    """
    Evaluate tempo mismatch.

    When a fast team plays a slow team, the slow team usually wins
    the pace battle — it's easier to slow down than speed up.
    """
    tempo_a = _g(a, "adj_t", "tempo")
    tempo_b = _g(b, "adj_t", "tempo")

    if math.isnan(tempo_a) or math.isnan(tempo_b):
        return {"edge": "Unknown", "adjustment": 0.0, "detail": "Tempo data unavailable"}

    diff = abs(tempo_a - tempo_b)
    name_a = _get_name(a)
    name_b = _get_name(b)
    slower = name_a if tempo_a < tempo_b else name_b
    faster = name_a if tempo_a > tempo_b else name_b

    if diff < 3:
        return {
            "edge": "Neutral",
            "adjustment": 0.0,
            "detail": f"Similar pace ({tempo_a:.1f} vs {tempo_b:.1f}). No significant mismatch.",
        }

    adj = 0.5 if diff < 6 else 1.0
    adjustment = adj if slower == name_a else -adj

    return {
        "edge": slower,
        "adjustment": round(adjustment, 1),
        "detail": f"{faster} wants to push ({max(tempo_a, tempo_b):.1f}) but "
                  f"{slower} grinds ({min(tempo_a, tempo_b):.1f}). "
                  f"Pace control favors {slower}.",
    }


def _off_def_matchup(a: dict, b: dict) -> dict:
    """
    Compare each team's offense against the other's defense.
    """
    adj_o_a = _g(a, "adj_o")
    adj_d_a = _g(a, "adj_d")
    adj_o_b = _g(b, "adj_o")
    adj_d_b = _g(b, "adj_d")

    if any(math.isnan(v) for v in [adj_o_a, adj_d_a, adj_o_b, adj_d_b]):
        return {"edge": "Unknown", "adjustment": 0.0, "detail": "Efficiency data unavailable"}

    name_a = _get_name(a)
    name_b = _get_name(b)

    # Team A's offense vs Team B's defense
    a_off_edge = adj_o_a - adj_d_b
    # Team B's offense vs Team A's defense
    b_off_edge = adj_o_b - adj_d_a

    net = a_off_edge - b_off_edge
    adjustment = max(-3.0, min(3.0, net / 5.0))

    if abs(net) < 3:
        edge = "Even"
    elif net > 0:
        edge = name_a
    else:
        edge = name_b

    return {
        "edge": edge,
        "adjustment": round(adjustment, 1),
        "detail": f"{name_a} offense vs {name_b} defense: {a_off_edge:+.1f} | "
                  f"{name_b} offense vs {name_a} defense: {b_off_edge:+.1f}",
        "a_off_vs_b_def": round(a_off_edge, 1),
        "b_off_vs_a_def": round(b_off_edge, 1),
    }


def _turnover_matchup(a: dict, b: dict) -> dict:
    """
    Turnover creation vs ball security.
    """
    a_steals = _g(a, "avg_steals")
    b_steals = _g(b, "avg_steals")
    a_tos = _g(a, "avg_turnovers")
    b_tos = _g(b, "avg_turnovers")

    if any(math.isnan(v) for v in [a_steals, b_steals, a_tos, b_tos]):
        return {"edge": "Unknown", "adjustment": 0.0, "detail": "Turnover data unavailable"}

    name_a = _get_name(a)
    name_b = _get_name(b)

    # A benefits when A_steals is high AND B_turnovers is high
    a_advantage = (a_steals / 10) * (b_tos / 10)
    b_advantage = (b_steals / 10) * (a_tos / 10)

    net = a_advantage - b_advantage
    adjustment = max(-2.0, min(2.0, net * 3))

    if abs(net) < 0.1:
        edge = "Even"
    elif net > 0:
        edge = name_a
    else:
        edge = name_b

    return {
        "edge": edge,
        "adjustment": round(adjustment, 1),
        "detail": f"{name_a}: {a_steals:.1f} stl, {a_tos:.1f} TO | "
                  f"{name_b}: {b_steals:.1f} stl, {b_tos:.1f} TO",
    }


def _rebounding_matchup(a: dict, b: dict) -> dict:
    """
    Rebounding edge — particularly offensive rebounds.
    """
    a_oreb = _g(a, "avg_off_rebounds")
    b_oreb = _g(b, "avg_off_rebounds")
    a_dreb = _g(a, "avg_def_rebounds")
    b_dreb = _g(b, "avg_def_rebounds")

    if any(math.isnan(v) for v in [a_oreb, b_oreb, a_dreb, b_dreb]):
        return {"edge": "Unknown", "adjustment": 0.0, "detail": "Rebound data unavailable"}

    name_a = _get_name(a)
    name_b = _get_name(b)

    a_board_edge = a_oreb - b_dreb
    b_board_edge = b_oreb - a_dreb

    net = a_board_edge - b_board_edge
    adjustment = max(-1.5, min(1.5, net / 3))

    if abs(net) < 1:
        edge = "Even"
    elif net > 0:
        edge = name_a
    else:
        edge = name_b

    return {
        "edge": edge,
        "adjustment": round(adjustment, 1),
        "detail": f"{name_a}: {a_oreb:.1f} OREB, {a_dreb:.1f} DREB | "
                  f"{name_b}: {b_oreb:.1f} OREB, {b_dreb:.1f} DREB",
    }


def _three_point_matchup(a: dict, b: dict) -> dict:
    """
    Three-point shooting as a variance factor.
    """
    a_3pct = _g(a, "three_pct")
    b_3pct = _g(b, "three_pct")
    a_3rate = _g(a, "three_pt_rate")
    b_3rate = _g(b, "three_pt_rate")

    if math.isnan(a_3pct) or math.isnan(b_3pct):
        return {"edge": "Unknown", "adjustment": 0.0, "detail": "3PT data unavailable"}

    name_a = _get_name(a)
    name_b = _get_name(b)

    diff = a_3pct - b_3pct
    adjustment = max(-1.0, min(1.0, diff * 10))

    a_volume = f"({a_3rate*100:.0f}% of shots)" if not math.isnan(a_3rate) else ""
    b_volume = f"({b_3rate*100:.0f}% of shots)" if not math.isnan(b_3rate) else ""

    if abs(diff) < 0.02:
        edge = "Even"
    elif diff > 0:
        edge = name_a
    else:
        edge = name_b

    return {
        "edge": edge,
        "adjustment": round(adjustment, 1),
        "detail": f"{name_a}: {a_3pct*100:.1f}% {a_volume} | "
                  f"{name_b}: {b_3pct*100:.1f}% {b_volume}",
    }


def _free_throw_matchup(a: dict, b: dict) -> dict:
    """
    Free throw reliability — critical in projected close games.
    """
    a_ft = _g(a, "ft_pct")
    b_ft = _g(b, "ft_pct")
    a_ft_vol = _g(a, "volatility_ft_pct")
    b_ft_vol = _g(b, "volatility_ft_pct")

    if math.isnan(a_ft) or math.isnan(b_ft):
        return {"edge": "Unknown", "adjustment": 0.0, "detail": "FT data unavailable"}

    name_a = _get_name(a)
    name_b = _get_name(b)

    diff = a_ft - b_ft

    # Volatility penalty: inconsistent FT shooting is riskier
    vol_a = 0.0 if math.isnan(a_ft_vol) else a_ft_vol
    vol_b = 0.0 if math.isnan(b_ft_vol) else b_ft_vol

    effective_diff = diff - (vol_a - vol_b) * 2
    adjustment = max(-1.5, min(1.5, effective_diff * 10))

    if abs(diff) < 0.03:
        edge = "Even"
    elif diff > 0:
        edge = name_a
    else:
        edge = name_b

    vol_note_a = f" (±{vol_a*100:.0f}%)" if vol_a > 0 else ""
    vol_note_b = f" (±{vol_b*100:.0f}%)" if vol_b > 0 else ""

    return {
        "edge": edge,
        "adjustment": round(adjustment, 1),
        "detail": f"{name_a}: {a_ft*100:.1f}%{vol_note_a} | "
                  f"{name_b}: {b_ft*100:.1f}%{vol_note_b}",
    }


def _momentum_matchup(a: dict, b: dict) -> dict:
    """
    Recent trend comparison — who's peaking heading into the game?
    """
    a_trend = _g(a, "trend_scoring_margin")
    b_trend = _g(b, "trend_scoring_margin")

    if math.isnan(a_trend) or math.isnan(b_trend):
        return {"edge": "Unknown", "adjustment": 0.0, "detail": "Trend data unavailable"}

    name_a = _get_name(a)
    name_b = _get_name(b)

    diff = a_trend - b_trend
    adjustment = max(-2.0, min(2.0, diff / 5))

    a_dir = "↑" if a_trend > 0 else "↓"
    b_dir = "↑" if b_trend > 0 else "↓"

    if abs(diff) < 2:
        edge = "Even"
    elif diff > 0:
        edge = name_a
    else:
        edge = name_b

    return {
        "edge": edge,
        "adjustment": round(adjustment, 1),
        "detail": f"{name_a}: {a_trend:+.1f} {a_dir} | "
                  f"{name_b}: {b_trend:+.1f} {b_dir}",
    }


# =============================================================================
# Helpers
# =============================================================================

def _g(stats: dict, *keys) -> float:
    """
    Get a stat value, trying multiple keys. Returns NaN if not found.
    Always returns float — never None — so math operations are safe.
    """
    for key in keys:
        val = stats.get(key)
        if val is not None:
            try:
                f = float(val)
                if not math.isnan(f):
                    return f
            except (ValueError, TypeError):
                continue
    return _MISSING


def _get_name(stats: dict) -> str:
    return str(stats.get("team", stats.get("name", "Unknown")))


def _edge_to_confidence(edge: float) -> str:
    """Convert a numeric edge to a confidence label."""
    if edge >= 8:
        return "Very High"
    elif edge >= 5:
        return "High"
    elif edge >= 3:
        return "Moderate"
    elif edge >= 1:
        return "Slight"
    else:
        return "Toss-up"


# =============================================================================
# Pretty Print
# =============================================================================

def print_matchup(result: dict) -> None:
    """Pretty-print a matchup analysis."""
    a = result["team_a"]
    b = result["team_b"]

    print(f"\n{'='*65}")
    print(f"  MATCHUP: {a} vs {b}")
    print(f"{'='*65}")

    if result["composite_a"] and result["composite_b"]:
        print(f"\n  Composite Scores: {a} {result['composite_a']:.1f} | {b} {result['composite_b']:.1f}")
        print(f"  Raw Edge: {a} {result['raw_edge']:+.1f}")

    print(f"\n  {'DIMENSION':<25s} {'EDGE':<20s} {'ADJ':>6s}")
    print(f"  {'-'*55}")

    for dim_name, dim in result["dimensions"].items():
        edge_str = dim.get("edge", "?")
        adj = dim.get("adjustment", 0)
        adj_str = f"{adj:+.1f}" if adj != 0 else "  --"
        print(f"  {dim_name:<25s} {edge_str:<20s} {adj_str:>6s}")
        if dim.get("detail"):
            print(f"    {dim['detail']}")

    print(f"\n  {'-'*55}")
    print(f"  {'Net Matchup Adjustment':<25s} {'':20s} {result['net_adjustment']:+.1f}")

    if result["composite_a"] and result["composite_b"]:
        print(f"  {'Adjusted Edge':<25s} {result['pick']:<20s} {result['adjusted_edge']:+.1f}")

    print(f"\n  >> PICK: {result['pick']} (Confidence: {result['confidence']})")
    print(f"{'='*65}\n")


# =============================================================================
# CLI Test
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    print("🏀 BracketIQ — Matchup Analyzer Test\n")

    from data.integrator import build_full_dataset
    from scoring.team_grader import grade_all_teams

    # Build data for test teams
    test_teams = ["Duke", "Houston"]
    print(f"Loading data for {test_teams}...")
    df = build_full_dataset(team_names=test_teams)

    # Grade
    print("Grading teams...")
    rankings = grade_all_teams(df)

    # Get team stats and scores
    def _get_team_data(name: str, data: pd.DataFrame, ranks: pd.DataFrame) -> tuple[dict | None, float | None]:
        mask = data["team"].str.lower().str.contains(name.lower(), na=False)
        if not mask.any():
            return None, None
        stats = data[mask].iloc[0].to_dict()
        rank_mask = ranks["team"].str.lower().str.contains(name.lower(), na=False)
        score = float(ranks[rank_mask].iloc[0]["composite"]) if rank_mask.any() else None
        return stats, score

    duke_stats, duke_score = _get_team_data("Duke", df, rankings)
    houston_stats, houston_score = _get_team_data("Houston", df, rankings)

    if duke_stats and houston_stats:
        print(f"\nRunning matchup: Duke vs Houston...")
        result = analyze_matchup(
            duke_stats, houston_stats,
            composite_a=duke_score,
            composite_b=houston_score,
        )
        print_matchup(result)

    print("✅ Matchup analyzer test complete.")