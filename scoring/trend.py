"""
BracketIQ - Trend & Volatility Analysis
==========================================
Takes game-by-game ESPN box scores and computes:
  - Recent form trends (last N games vs season average)
  - Volatility / consistency metrics (std dev of key stats)
  - Close game performance
  - FT reliability under pressure

These feed directly into the Context Layer of the scoring engine.
"""

import logging
import pandas as pd
import numpy as np

from config.weights import TREND_CONFIG

logger = logging.getLogger(__name__)


def compute_trends(game_df: pd.DataFrame) -> dict:
    """
    Compute trend metrics by comparing recent games to season average.

    A positive trend means the team is improving heading into March.
    A negative trend means they're slumping.

    Uses weighted decay so the most recent game matters most.

    Args:
        game_df: DataFrame from espn_scraper.fetch_team_season_boxscores().
                 Must have 'date' column and be sorted chronologically.

    Returns:
        Dict with trend values (positive = improving, negative = declining).
    """
    if game_df.empty or len(game_df) < 5:
        logger.warning("Not enough games for trend analysis.")
        return {}

    lookback = TREND_CONFIG["lookback_games"]
    use_decay = TREND_CONFIG["trend_weight_decay"]
    decay = TREND_CONFIG["decay_factor"]

    # Sort by date to ensure chronological order
    df = game_df.sort_values("date").copy()

    # Split into recent and full season
    recent = df.tail(lookback)
    season = df

    trends = {}

    # --- Scoring margin trend ---
    season_margin = season["margin"].mean()
    if use_decay:
        recent_margin = _weighted_mean(recent["margin"], decay)
    else:
        recent_margin = recent["margin"].mean()
    trends["trend_scoring_margin"] = recent_margin - season_margin

    # --- Offensive trend (points scored) ---
    season_off = season["team_score"].mean()
    if use_decay:
        recent_off = _weighted_mean(recent["team_score"], decay)
    else:
        recent_off = recent["team_score"].mean()
    trends["trend_off_efficiency"] = recent_off - season_off

    # --- Defensive trend (points allowed) ---
    # Negative change in opp score = defense improving
    season_def = season["opponent_score"].mean()
    if use_decay:
        recent_def = _weighted_mean(recent["opponent_score"], decay)
    else:
        recent_def = recent["opponent_score"].mean()
    # Flip sign: fewer points allowed = positive trend
    trends["trend_def_efficiency"] = season_def - recent_def

    # --- Turnover trend ---
    if "totalTurnovers" in df.columns:
        to_col = pd.to_numeric(df["totalTurnovers"], errors="coerce")
        season_to = to_col.mean()
        recent_to_vals = pd.to_numeric(recent["totalTurnovers"], errors="coerce")
        if use_decay:
            recent_to = _weighted_mean(recent_to_vals, decay)
        else:
            recent_to = recent_to_vals.mean()
        # Fewer turnovers = positive trend
        trends["trend_turnovers"] = season_to - recent_to

    return trends


def compute_volatility(game_df: pd.DataFrame) -> dict:
    """
    Compute volatility (consistency) metrics from game-by-game data.

    Lower volatility = more consistent = better for tournament play.
    A team that swings between 90 and 55 points is riskier than one
    that consistently scores 72.

    Args:
        game_df: DataFrame from espn_scraper.fetch_team_season_boxscores().

    Returns:
        Dict with std dev values for key metrics.
    """
    if game_df.empty or len(game_df) < 5:
        return {}

    vol = {}

    # Scoring volatility
    vol["volatility_scoring"] = game_df["margin"].std()

    # Turnover volatility
    if "totalTurnovers" in game_df.columns:
        to_col = pd.to_numeric(game_df["totalTurnovers"], errors="coerce")
        vol["volatility_turnovers"] = to_col.std()

    # FT% volatility (game-by-game FT%)
    ft_pcts = _game_ft_percentages(game_df)
    if len(ft_pcts) >= 5:
        vol["volatility_ft_pct"] = ft_pcts.std()

    return vol


def compute_close_game_stats(game_df: pd.DataFrame) -> dict:
    """
    Compute close game performance metrics.

    Close games (margin <= 5) reveal how a team performs under pressure.
    This is critical for tournament projections.

    Args:
        game_df: DataFrame from espn_scraper.fetch_team_season_boxscores().

    Returns:
        Dict with close game record, FT% in close games, etc.
    """
    if game_df.empty:
        return {}

    stats = {}

    # Close game record
    close = game_df[game_df["margin"].abs() <= 5]
    stats["close_games_played"] = len(close)

    if len(close) > 0:
        close_wins = (close["result"] == "W").sum()
        stats["close_game_record"] = close_wins / len(close)

        # FT% in close games specifically
        ft_pcts = _game_ft_percentages(close)
        if len(ft_pcts) > 0:
            stats["ft_pct_close_games"] = ft_pcts.mean()
    else:
        # No close games — default to neutral
        stats["close_game_record"] = 0.5
        stats["ft_pct_close_games"] = None

    return stats


def compute_shooting_splits(game_df: pd.DataFrame) -> dict:
    """
    Compute season shooting percentages from game-by-game data.

    These fill the base layer gaps where Torvik JSON failed to provide
    four factors data.

    Args:
        game_df: DataFrame from espn_scraper.fetch_team_season_boxscores().

    Returns:
        Dict with shooting percentages calculated from totals.
    """
    if game_df.empty:
        return {}

    stats = {}

    # FG%
    fgm = pd.to_numeric(game_df.get("fieldGoalsMade", pd.Series(dtype=float)), errors="coerce").sum()
    fga = pd.to_numeric(game_df.get("fieldGoalsAttempted", pd.Series(dtype=float)), errors="coerce").sum()
    if fga > 0:
        stats["fg_pct"] = fgm / fga

    # 3PT%
    tpm = pd.to_numeric(game_df.get("threePointFieldGoalsMade", pd.Series(dtype=float)), errors="coerce").sum()
    tpa = pd.to_numeric(game_df.get("threePointFieldGoalsAttempted", pd.Series(dtype=float)), errors="coerce").sum()
    if tpa > 0:
        stats["three_pct"] = tpm / tpa
        # Three point attempt rate (3PA / FGA) — measures reliance on threes
        if fga > 0:
            stats["three_pt_rate"] = tpa / fga

    # FT%
    ftm = pd.to_numeric(game_df.get("freeThrowsMade", pd.Series(dtype=float)), errors="coerce").sum()
    fta = pd.to_numeric(game_df.get("freeThrowsAttempted", pd.Series(dtype=float)), errors="coerce").sum()
    if fta > 0:
        stats["ft_pct"] = ftm / fta
        # Free throw rate (FTA / FGA)
        if fga > 0:
            stats["off_ftr"] = fta / fga

    return stats


def compute_espn_extras(game_df: pd.DataFrame) -> dict:
    """
    Compute averages for ESPN-exclusive stats.

    These are the stats Torvik doesn't have — points off turnovers,
    fast break points, paint points, largest lead.

    Args:
        game_df: DataFrame from espn_scraper.fetch_team_season_boxscores().

    Returns:
        Dict with per-game averages for ESPN-exclusive stats.
    """
    if game_df.empty:
        return {}

    stats = {}
    extras = {
        "turnoverPoints": "avg_turnover_points",
        "fastBreakPoints": "avg_fast_break_points",
        "pointsInPaint": "avg_paint_points",
        "largestLead": "avg_largest_lead",
        "assists": "avg_assists",
        "steals": "avg_steals",
        "blocks": "avg_blocks",
        "totalTurnovers": "avg_turnovers",
        "offensiveRebounds": "avg_off_rebounds",
        "defensiveRebounds": "avg_def_rebounds",
    }

    for espn_name, our_name in extras.items():
        if espn_name in game_df.columns:
            col = pd.to_numeric(game_df[espn_name], errors="coerce")
            if col.notna().any():
                stats[our_name] = col.mean()

    return stats


def compute_all_espn_stats(game_df: pd.DataFrame) -> dict:
    """
    Master function: compute ALL ESPN-derived stats for a single team.

    Combines trends, volatility, close game performance, shooting splits,
    and ESPN extras into one dict ready for merging with Torvik data.

    Args:
        game_df: DataFrame from espn_scraper.fetch_team_season_boxscores().

    Returns:
        Single dict with all computed stats.
    """
    if game_df.empty:
        return {}

    all_stats = {}
    all_stats.update(compute_trends(game_df))
    all_stats.update(compute_volatility(game_df))
    all_stats.update(compute_close_game_stats(game_df))
    all_stats.update(compute_shooting_splits(game_df))
    all_stats.update(compute_espn_extras(game_df))

    logger.info(f"Computed {len(all_stats)} ESPN-derived stats.")
    return all_stats


# =============================================================================
# Helpers
# =============================================================================

def _weighted_mean(series: pd.Series, decay: float) -> float:
    """
    Compute a weighted mean where more recent values weigh more.

    The last value gets weight 1.0, second-to-last gets decay,
    third gets decay^2, etc.
    """
    values = series.dropna().values.astype(float)
    if len(values) == 0:
        return 0.0

    n = len(values)
    weights = np.array([decay ** (n - 1 - i) for i in range(n)], dtype=float)
    return float(np.sum(values * weights) / np.sum(weights))


def _game_ft_percentages(game_df: pd.DataFrame) -> pd.Series:
    """
    Calculate FT% for each game, filtering out games with < 5 FTA.

    Low-attempt games add noise — a team going 1/2 shouldn't count
    the same as a team going 14/20.
    """
    if "freeThrowsMade" not in game_df.columns or "freeThrowsAttempted" not in game_df.columns:
        return pd.Series(dtype=float)

    ftm = pd.to_numeric(game_df["freeThrowsMade"], errors="coerce")
    fta = pd.to_numeric(game_df["freeThrowsAttempted"], errors="coerce")

    # Only include games with meaningful FT attempts
    mask = fta >= 5
    if mask.sum() == 0:
        return pd.Series(dtype=float)

    return (ftm[mask] / fta[mask])


# =============================================================================
# CLI Test
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    print("🏀 BracketIQ — Trend & Volatility Test\n")

    from data.espn_scraper import fetch_team_season_boxscores, find_espn_id, fetch_teams

    teams = fetch_teams()
    duke_id = find_espn_id("Duke", teams)

    if duke_id:
        print(f"Fetching Duke's full season box scores...")
        game_df = fetch_team_season_boxscores(duke_id)

        if not game_df.empty:
            print(f"  {len(game_df)} games loaded.\n")

            all_stats = compute_all_espn_stats(game_df)

            print("  TRENDS:")
            for k, v in all_stats.items():
                if k.startswith("trend_"):
                    print(f"    {k:<30s} {v:>+.2f}")

            print("\n  VOLATILITY:")
            for k, v in all_stats.items():
                if k.startswith("volatility_"):
                    print(f"    {k:<30s} {v:>.2f}")

            print("\n  CLOSE GAMES:")
            for k, v in all_stats.items():
                if "close" in k:
                    print(f"    {k:<30s} {v}")

            print("\n  SHOOTING:")
            for k, v in all_stats.items():
                if k in ["fg_pct", "three_pct", "ft_pct", "off_ftr", "three_pt_rate"]:
                    print(f"    {k:<30s} {v:.3f}")

            print("\n  ESPN EXTRAS:")
            for k, v in all_stats.items():
                if k.startswith("avg_"):
                    print(f"    {k:<30s} {v:.1f}")

    print("\n✅ Trend & volatility test complete.")