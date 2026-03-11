"""
BracketIQ - Weight Configuration
=================================
All scoring weights, thresholds, and tier definitions live here.
Adjust values freely — everything downstream recalculates automatically.

TIER BREAKDOWN:
  Base Layer (40%)    — Efficiency, shooting, four factors fundamentals
  Context Layer (35%) — SOS, trends, volatility, resume quality
  Tournament Layer (25%) — Upset profile, archetype matching, seed, FT reliability

Each stat within a tier has a sub-weight (should sum to 1.0 within each tier).
"""

# =============================================================================
# TIER WEIGHTS — Controls how much each layer contributes to final score
# =============================================================================
TIER_WEIGHTS = {
    "base": 0.40,
    "context": 0.35,
    "tournament": 0.25,
}

# =============================================================================
# BASE LAYER — Efficiency & Shooting Fundamentals (40% of total)
# =============================================================================
# These are your four-factors-plus metrics. The foundation.
# Sub-weights within this tier should sum to 1.0
BASE_WEIGHTS = {
    # Adjusted efficiency (Torvik, per 100 possessions)
    "adj_o": 0.18,              # Adjusted offensive efficiency
    "adj_d": 0.18,              # Adjusted defensive efficiency (lower = better)
    "net_efficiency": 0.14,     # AdjO - AdjD (overall margin per 100 poss)
    "barthag": 0.10,            # Torvik power rating (0-1 scale)

    # Four Factors — Offense (when available from fixed JSON or ESPN)
    "off_efg": 0.08,            # Offensive effective FG%
    "off_to": 0.05,             # Offensive turnover % (lower = better)
    "off_or": 0.03,             # Offensive rebound %
    "off_ftr": 0.02,            # Offensive free throw rate (FTA/FGA)

    # Four Factors — Defense (when available)
    "def_efg": 0.08,            # Defensive effective FG% allowed (lower = better)
    "def_to": 0.04,             # Defensive turnover % forced (higher = better)
    "def_or": 0.03,             # Defensive rebound % (opp ORB% — lower = better)
    "def_ftr": 0.02,            # Defensive free throw rate allowed (lower = better)

    # Shooting Splits (filled by ESPN data when available)
    "three_pct": 0.03,          # Team 3PT%
    "ft_pct": 0.02,             # Free throw percentage
}

# =============================================================================
# CONTEXT LAYER — Schedule, Trends, Resume Quality (35% of total)
# =============================================================================
# This is where we go beyond the four factors.
# Sub-weights within this tier should sum to 1.0
CONTEXT_WEIGHTS = {
    # Strength of Schedule
    "sos_overall": 0.14,        # Overall strength of schedule
    "sos_noncon": 0.06,         # Non-conference SOS
    "sos_elite": 0.05,          # Elite SOS (top opponents)
    "sos_elite_noncon": 0.03,   # Elite non-conference SOS

    # Resume / Record Quality
    "wab": 0.12,                # Wins Above Bubble (Torvik metric)
    "qual_barthag": 0.08,       # Barthag in quality games
    "qual_o": 0.05,             # Offense rating in quality games
    "qual_d": 0.05,             # Defense rating in quality games
    "qual_games": 0.04,         # Number of quality games played

    # Recent Form & Trends (last 8-10 games vs season average)
    "trend_off_efficiency": 0.06,   # Is offense trending up or down?
    "trend_def_efficiency": 0.06,   # Is defense trending up or down?
    "trend_scoring_margin": 0.06,   # Is margin trending up or down?

    # Consistency / Volatility (std dev of key metrics game-to-game)
    "volatility_scoring": 0.05,     # Scoring consistency (lower std dev = better)
    "volatility_turnovers": 0.05,   # Turnover consistency
    "volatility_ft_pct": 0.05,      # FT% consistency (critical in close games)

    # Close Game Performance
    "close_game_record": 0.05,      # Record in games decided by <= 5 points
}

# =============================================================================
# TOURNAMENT LAYER — March-Specific Factors (25% of total)
# =============================================================================
# This is the differentiator — what separates us from a four-factors ranking.
# Sub-weights within this tier should sum to 1.0
TOURNAMENT_WEIGHTS = {
    # Historical Archetype Match
    "archetype_similarity": 0.28,   # How similar is this team to past champions/F4?

    # Upset Profile (for lower seeds — measures upset potential)
    "upset_three_pt_var": 0.08,     # High 3PT volume + decent % = variance creator
    "upset_def_efficiency": 0.08,   # Elite defense shrinks talent gaps
    "upset_tempo_control": 0.06,    # Can they slow the game / control pace?
    "upset_turnover_creation": 0.06, # Forcing TOs = free possessions

    # Seed Adjustment (very slight, as discussed)
    "seed_bonus": 0.05,            # Small bump for higher seeds (committee info)

    # Free Throw Reliability Under Pressure
    "ft_pct_close_games": 0.10,    # FT% specifically in close games if available
    "ft_consistency": 0.07,        # Low variance in FT% game-to-game

    # Experience / Tournament Pedigree
    "conf_tournament_result": 0.12, # How did they perform in conf tourney?

    # Pace Mismatch Potential (used more in matchup tool, but factors here too)
    "tempo": 0.10,                  # Raw tempo — not good or bad, but context matters

    # -----------------------------------------------------------------
    # DISABLED — Available for future use. Uncomment and redistribute
    # weights above (must sum to 1.0) to re-enable.
    #
    # "program_tournament_history": 0.07,
    #   ^ Removed: Program pedigree doesn't account for coaching changes.
    #     Consider replacing with coach_tournament_experience if a
    #     reliable coaching data source is added.
    #
    # "coach_tournament_experience": 0.07,
    #   ^ Potential future stat: Coach's personal tournament record.
    #     Would need coaching data from Torvik or manual tracking.
    # -----------------------------------------------------------------
}

# =============================================================================
# STAT POLARITY — Defines whether higher or lower is better
# =============================================================================
# True = higher is better, False = lower is better
# This controls normalization direction
STAT_POLARITY = {
    # Base Layer
    "adj_o": True,
    "adj_d": False,
    "net_efficiency": True,
    "barthag": True,
    "opp_oe": False,
    "opp_de": True,
    "off_efg": True,
    "off_to": False,
    "off_or": True,
    "off_ftr": True,
    "def_efg": False,
    "def_to": True,
    "def_or": False,
    "def_ftr": False,
    "three_pct": True,
    "opp_three_pct": False,
    "ft_pct": True,

    # Context Layer
    "sos_overall": True,
    "sos_noncon": True,
    "sos_elite": False,          # Rank column — lower number = better
    "sos_elite_noncon": False,   # Rank column — lower number = better
    "q1_record": True,
    "q2_record": True,
    "wab": True,
    "qual_o": True,
    "qual_d": False,
    "qual_games": True,
    "qual_barthag": True,
    "trend_off_efficiency": True,
    "trend_def_efficiency": True,
    "trend_scoring_margin": True,
    "volatility_scoring": False,
    "volatility_turnovers": False,
    "volatility_ft_pct": False,
    "close_game_record": True,

    # Tournament Layer
    "archetype_similarity": True,
    "upset_three_pt_var": True,
    "upset_def_efficiency": True,
    "upset_tempo_control": True,
    "upset_turnover_creation": True,
    "seed_bonus": True,
    "ft_pct_close_games": True,
    "ft_consistency": False,
    "conf_tournament_result": True,
    "program_tournament_history": True,
    "tempo": None,
}

# =============================================================================
# ARCHETYPE PROFILE — Statistical profile of recent champions / Final Four teams
# =============================================================================
# Based on 2021-2025 tournament winners and Final Four teams
# These are approximate percentile thresholds (out of all D1 teams)
# Used by archetype.py to calculate similarity scores
CHAMPION_ARCHETYPE = {
    "adj_o_percentile": 90,         # Top 10% offensive efficiency
    "adj_d_percentile": 90,         # Top 10% defensive efficiency
    "net_efficiency_percentile": 95, # Top 5% net efficiency
    "off_efg_percentile": 75,       # Above average eFG%
    "off_to_percentile": 70,        # Reasonably low turnover rate
    "ft_pct_percentile": 65,        # Above average FT shooting
    "sos_percentile": 70,           # Played a real schedule
    "three_pct_percentile": 60,     # Don't need to be elite, but competent
    "def_efg_percentile": 80,       # Strong defensive eFG% allowed
    "tempo_range": (64, 72),        # Most champions play moderate tempo
}

# Weights for how much each archetype dimension matters in similarity calc
ARCHETYPE_DIMENSION_WEIGHTS = {
    "adj_o_percentile": 0.12,
    "adj_d_percentile": 0.15,       # Defense slightly more important
    "net_efficiency_percentile": 0.15,
    "off_efg_percentile": 0.10,
    "off_to_percentile": 0.10,
    "ft_pct_percentile": 0.10,
    "sos_percentile": 0.08,
    "three_pct_percentile": 0.05,
    "def_efg_percentile": 0.10,
    "tempo_range": 0.05,
}

# =============================================================================
# UPSET THRESHOLDS — When does an upset flag get raised?
# =============================================================================
UPSET_CONFIG = {
    "seed_diff_minimum": 3,         # Only flag upsets for 3+ seed difference
    "upset_score_threshold": 65,    # Upset profile score (0-100) to flag
    "high_variance_three_pct": 0.35, # 3PT% above this = variance creator
    "high_three_volume": 25,        # 3PA per game above this = volume shooter
    "elite_def_percentile": 80,     # Top 20% defense = upset-capable
    "low_tempo_threshold": 65,      # Possessions/game below this = grinder
}

# =============================================================================
# TREND CONFIGURATION
# =============================================================================
TREND_CONFIG = {
    "lookback_games": 8,            # Number of recent games to evaluate trends
    "trend_weight_decay": True,     # More recent games weighted more heavily
    "decay_factor": 0.9,            # Each game back is 0.9x the weight of the next
}

# =============================================================================
# OUTPUT CONFIGURATION
# =============================================================================
OUTPUT_CONFIG = {
    "score_range": (0, 100),        # Final composite score range
    "tier_labels": {
        (90, 100): "S",             # Elite — legitimate title contenders
        (80, 89.99): "A",           # Strong — Sweet 16 / Elite 8 caliber
        (70, 79.99): "B",           # Solid — Round of 32 caliber
        (60, 69.99): "C",           # Average — Could win a game, could lose R1
        (50, 59.99): "D",           # Below average — likely early exit
        (0, 49.99): "F",            # Weak — major upset needed to advance
    },
    "csv_filename": "bracketiq_rankings_{year}.csv",
    "matchup_csv_filename": "bracketiq_matchup_{team1}_vs_{team2}.csv",
}

# =============================================================================
# DATA SOURCE URLS
# =============================================================================
DATA_SOURCES = {
    "torvik": {
        "team_results_csv": "https://barttorvik.com/{year}_team_results.csv",
        "team_results_json": "https://barttorvik.com/{year}_team_results.json",
        "team_slice_json": "https://barttorvik.com/teamslicejson.php?year={year}&json=1",
        "four_factors": "https://barttorvik.com/teamslicejson.php?year={year}&json=1",
        "time_machine": "https://barttorvik.com/timemachine/team_results/{date}_team_results.json.gz",
    },
    "espn": {
        "teams": "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/teams",
        "team_detail": "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/teams/{team_id}",
        "scoreboard": "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard",
        "game_summary": "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/summary?event={game_id}",
        "standings": "https://site.web.api.espn.com/apis/v2/sports/basketball/mens-college-basketball/standings",
        "rankings": "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/rankings",
    },
}

# =============================================================================
# YEAR CONFIGURATION
# =============================================================================
CURRENT_YEAR = 2026
HISTORICAL_YEARS = [2021, 2022, 2023, 2024, 2025]  # 5 years of backtest data