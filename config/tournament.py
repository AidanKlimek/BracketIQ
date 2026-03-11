"""
BracketIQ - Tournament Roster & Conference Results
=====================================================
Manually maintained file updated as Selection Sunday and
conference tournaments finalize.

UPDATE INSTRUCTIONS:
  1. After each conference tournament final, update CONF_TOURNEY_RESULTS
  2. On Selection Sunday, update TOURNAMENT_TEAMS with all 68 teams
  3. Clear relevant caches and re-run: python main.py refresh

Set TOURNAMENT_FINALIZED = True once the bracket is set.
"""

# Set to True once Selection Sunday bracket is released
TOURNAMENT_FINALIZED = False

# =============================================================================
# 2026 TOURNAMENT TEAMS — Update on Selection Sunday
# =============================================================================
# Format: {"team_name": {"seed": N, "region": "Region"}}
# Leave empty until bracket is announced. The tool will fall back to
# top 68 by WAB if this is empty.

TOURNAMENT_TEAMS: dict[str, dict] = {
    # EXAMPLE (uncomment and fill in on Selection Sunday):
    # "Duke": {"seed": 1, "region": "East"},
    # "Houston": {"seed": 1, "region": "South"},
    # "Michigan": {"seed": 1, "region": "West"},
    # "Florida": {"seed": 1, "region": "Midwest"},
    # ... all 68 teams
}

# =============================================================================
# CONFERENCE TOURNAMENT RESULTS — Update as they finish
# =============================================================================
# Format: {"team_name": result_score}
# Scoring:
#   Won conference tournament = 100
#   Lost in championship game = 75
#   Lost in semifinal = 50
#   Lost in quarterfinal = 25
#   Lost earlier / didn't play = 0
#
# This feeds into the "conf_tournament_result" weight in the tournament layer.

CONF_TOURNEY_RESULTS: dict[str, int] = {
    # EXAMPLE (update as tournaments finish):
    # "Duke": 100,          # Won ACC tournament
    # "North Carolina": 75, # Lost in ACC final
    # "Virginia": 50,       # Lost in ACC semifinal
}

# =============================================================================
# PLAY-IN GAMES — Update after First Four
# =============================================================================
# Teams in play-in games (First Four). Update with winners after games.
PLAYIN_MATCHUPS: list[dict] = [
    # EXAMPLE:
    # {"team_a": "Team1", "team_b": "Team2", "seed": 16, "winner": None},
    # {"team_a": "Team3", "team_b": "Team4", "seed": 11, "winner": None},
]


def get_tournament_team_names() -> list[str]:
    """Get list of tournament team names. Falls back to empty if not set."""
    if TOURNAMENT_TEAMS:
        return list(TOURNAMENT_TEAMS.keys())
    return []


def get_team_seed(team_name: str) -> int | None:
    """Get a team's tournament seed."""
    info = TOURNAMENT_TEAMS.get(team_name)
    return info["seed"] if info else None


def get_team_region(team_name: str) -> str | None:
    """Get a team's tournament region."""
    info = TOURNAMENT_TEAMS.get(team_name)
    return info.get("region") if info else None


def get_conf_tourney_score(team_name: str) -> int:
    """Get a team's conference tournament result score."""
    return CONF_TOURNEY_RESULTS.get(team_name, 0)