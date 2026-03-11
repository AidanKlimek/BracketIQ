"""
BracketIQ - ESPN Data Scraper
================================
Pulls team stats and game-level box scores from ESPN's public API.

ESPN provides data that Torvik does not:
  - Bench points, points off turnovers, fast break points, points in paint
  - Game-by-game box scores for trend/volatility analysis
  - Team schedule and results with game IDs

Endpoints used (no auth required):
  - /teams              — All D1 team IDs, names, abbreviations
  - /scoreboard         — Daily game IDs and scores
  - /summary?event=ID   — Full box score for a specific game
  - /standings           — Conference standings and records

Be respectful — ESPN can rate-limit or block excessive requests.
"""

import json
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any

import requests
import pandas as pd

from config.settings import (
    CACHE_DIR, ESPN_REQUEST_DELAY, REQUEST_HEADERS, CACHE_TTL_HOURS,
)
from config.weights import DATA_SOURCES, CURRENT_YEAR

logger = logging.getLogger(__name__)

BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball"
SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/summary"


# =============================================================================
# Cache Helpers (same pattern as Torvik scraper)
# =============================================================================

def _cache_path(filename: str) -> Path:
    return CACHE_DIR / filename


def _cache_is_fresh(filepath: Path) -> bool:
    if not filepath.exists():
        return False
    modified = datetime.fromtimestamp(filepath.stat().st_mtime)
    return (datetime.now() - modified) < timedelta(hours=CACHE_TTL_HOURS)


def _save_cache(filepath: Path, data: str) -> None:
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(data, encoding="utf-8")


def _load_cache(filepath: Path) -> str:
    return filepath.read_text(encoding="utf-8")


# =============================================================================
# HTTP Helpers
# =============================================================================

def _fetch_json(url: str, params: dict | None = None, delay: float | None = None) -> dict:
    """
    Make a GET request to ESPN API and return parsed JSON.
    Includes polite delay and error handling.
    """
    if delay is None:
        delay = ESPN_REQUEST_DELAY

    time.sleep(delay)
    logger.info(f"Fetching ESPN: {url}")

    resp = requests.get(url, params=params, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


# =============================================================================
# Team Directory
# =============================================================================

def fetch_teams(force_refresh: bool = False) -> pd.DataFrame:
    """
    Fetch all D1 men's basketball teams from ESPN.

    Returns DataFrame with: team_id, name, abbreviation, display_name,
    conference (if available), logo_url.

    This is needed to map team names to ESPN IDs for schedule/game lookups.
    """
    cache_file = _cache_path("espn_teams.json")

    if not force_refresh and _cache_is_fresh(cache_file):
        data = json.loads(_load_cache(cache_file))
    else:
        url = f"{BASE_URL}/teams"
        data = _fetch_json(url, params={"limit": "1000", "groups": "50"})
        _save_cache(cache_file, json.dumps(data))

    # Parse the nested JSON structure
    teams = []
    try:
        for team_entry in data["sports"][0]["leagues"][0]["teams"]:
            t = team_entry["team"]
            teams.append({
                "espn_id": int(t["id"]),
                "name": t.get("nickname", t.get("shortDisplayName", "")),
                "display_name": t.get("displayName", ""),
                "abbreviation": t.get("abbreviation", ""),
                "location": t.get("location", ""),
                "slug": t.get("slug", ""),
                "color": t.get("color", ""),
                "logo_url": t["logos"][0]["href"] if t.get("logos") else "",
            })
    except (KeyError, IndexError) as e:
        logger.error(f"Error parsing ESPN teams: {e}")

    df = pd.DataFrame(teams)
    logger.info(f"Parsed {len(df)} teams from ESPN.")
    return df


# =============================================================================
# Team Schedule & Game IDs
# =============================================================================

def fetch_team_schedule(team_id: int, year: int | None = None, force_refresh: bool = False) -> list[dict]:
    """
    Fetch a team's full schedule with game IDs and results.

    Returns a list of dicts, each containing:
        - game_id, date, home_away, opponent, result, score, opponent_score
    """
    if year is None:
        year = CURRENT_YEAR

    cache_file = _cache_path(f"espn_schedule_{team_id}_{year}.json")

    if not force_refresh and _cache_is_fresh(cache_file):
        return json.loads(_load_cache(cache_file))

    url = f"{BASE_URL}/teams/{team_id}/schedule"
    params = {"season": str(year)}

    try:
        data = _fetch_json(url, params=params)
    except requests.RequestException as e:
        logger.error(f"Failed to fetch schedule for team {team_id}: {e}")
        if cache_file.exists():
            return json.loads(_load_cache(cache_file))
        return []

    games = []
    for event in data.get("events", []):
        game = _parse_schedule_event(event, team_id)
        if game:
            games.append(game)

    _save_cache(cache_file, json.dumps(games))
    logger.info(f"Parsed {len(games)} games for team {team_id}.")
    return games


def _parse_schedule_event(event: dict, team_id: int) -> dict | None:
    """Parse a single schedule event into a clean dict."""
    try:
        competition = event["competitions"][0]
        competitors = competition["competitors"]

        # Find our team and the opponent
        our_team = None
        opponent = None
        for c in competitors:
            if int(c["id"]) == team_id:
                our_team = c
            else:
                opponent = c

        if not our_team or not opponent:
            return None

        return {
            "game_id": event["id"],
            "date": event.get("date", ""),
            "home_away": our_team.get("homeAway", ""),
            "team_score": int(our_team.get("score", {}).get("value", 0)) if isinstance(our_team.get("score"), dict) else int(our_team.get("score", 0)),
            "opponent_id": int(opponent["id"]),
            "opponent_name": opponent.get("team", {}).get("displayName", "Unknown"),
            "opponent_score": int(opponent.get("score", {}).get("value", 0)) if isinstance(opponent.get("score"), dict) else int(opponent.get("score", 0)),
            "completed": competition.get("status", {}).get("type", {}).get("completed", False),
        }
    except (KeyError, ValueError, TypeError) as e:
        logger.debug(f"Skipping unparseable event: {e}")
        return None


# =============================================================================
# Game Box Score (the key ESPN-unique data)
# =============================================================================

def fetch_game_boxscore(game_id: str, force_refresh: bool = False) -> dict | None:
    """
    Fetch full box score for a single game from the summary endpoint.

    Returns a dict with team-level stats including:
        - Standard: FGM/FGA, 3PM/3PA, FTM/FTA, rebounds, assists, steals, blocks, TOs
        - ESPN extras: benchPoints, turnoverPoints, fastBreakPoints, pointsInPaint
        - Score data: biggest lead, biggest run, time leading
    """
    cache_file = _cache_path(f"espn_game_{game_id}.json")

    if not force_refresh and _cache_is_fresh(cache_file):
        return json.loads(_load_cache(cache_file))

    try:
        data = _fetch_json(SUMMARY_URL, params={"event": str(game_id)})
    except requests.RequestException as e:
        logger.error(f"Failed to fetch game {game_id}: {e}")
        if cache_file.exists():
            return json.loads(_load_cache(cache_file))
        return None

    boxscore = _parse_boxscore(data)
    if boxscore:
        _save_cache(cache_file, json.dumps(boxscore))

    return boxscore


def _parse_boxscore(data: dict) -> dict | None:
    """Parse the game summary JSON into a clean boxscore dict."""
    try:
        boxscore = data.get("boxscore", {})
        teams_data = boxscore.get("teams", [])

        if not teams_data:
            return None

        result = {"teams": []}

        for team_entry in teams_data:
            team_info = team_entry.get("team", {})
            stats = team_entry.get("statistics", [])

            # Convert stats array into a flat dict
            stat_dict = {}
            for stat in stats:
                name = stat.get("name", "")
                value = stat.get("displayValue", "0")
                # Handle "made-attempted" format (e.g., name="fieldGoalsMade-fieldGoalsAttempted", value="29-69")
                if "-" in name and "-" in str(value):
                    name_parts = name.split("-")
                    value_parts = str(value).split("-")
                    if len(name_parts) == 2 and len(value_parts) == 2:
                        try:
                            stat_dict[name_parts[0]] = int(value_parts[0])
                            stat_dict[name_parts[1]] = int(value_parts[1])
                        except ValueError:
                            stat_dict[name] = value
                        continue
                # Try to parse as number
                try:
                    if "." in str(value):
                        stat_dict[name] = float(value)
                    else:
                        stat_dict[name] = int(value)
                except (ValueError, TypeError):
                    stat_dict[name] = value

            result["teams"].append({
                "team_id": int(team_info.get("id", 0)),
                "team_name": team_info.get("displayName", ""),
                "abbreviation": team_info.get("abbreviation", ""),
                "stats": stat_dict,
            })

        return result
    except (KeyError, TypeError) as e:
        logger.error(f"Error parsing boxscore: {e}")
        return None


# =============================================================================
# Aggregate Season Stats From Game-by-Game Box Scores
# =============================================================================

def fetch_team_season_boxscores(
    team_id: int,
    year: int | None = None,
    force_refresh: bool = False,
    max_games: int | None = None,
) -> pd.DataFrame:
    """
    Fetch box scores for all completed games in a team's season.

    This is the heavy-lift function — it pulls each game's summary individually.
    Results are cached per-game, so subsequent runs are fast.

    Args:
        team_id: ESPN team ID.
        year: Season year.
        force_refresh: Bypass cache.
        max_games: Limit number of games (useful for testing).

    Returns:
        DataFrame with one row per game, columns for all box score stats.
    """
    schedule = fetch_team_schedule(team_id, year, force_refresh)
    completed = [g for g in schedule if g.get("completed", False)]

    if max_games:
        completed = completed[:max_games]

    logger.info(f"Fetching box scores for {len(completed)} games (team {team_id})...")

    rows = []
    for game in completed:
        boxscore = fetch_game_boxscore(game["game_id"], force_refresh)
        if not boxscore:
            continue

        # Find our team's stats in the boxscore
        for team in boxscore.get("teams", []):
            if team["team_id"] == team_id:
                row = {
                    "game_id": game["game_id"],
                    "date": game["date"],
                    "home_away": game["home_away"],
                    "team_score": game["team_score"],
                    "opponent_score": game["opponent_score"],
                    "opponent_name": game["opponent_name"],
                    "result": "W" if game["team_score"] > game["opponent_score"] else "L",
                    "margin": game["team_score"] - game["opponent_score"],
                }
                # Flatten all box score stats into the row
                row.update(team.get("stats", {}))
                rows.append(row)
                break

    df = pd.DataFrame(rows)
    if not df.empty:
        logger.info(f"Built {len(df)} game box scores for team {team_id}.")
    else:
        logger.warning(f"No box score data for team {team_id}.")
    return df


def aggregate_season_stats(game_df: pd.DataFrame) -> dict:
    """
    Aggregate game-by-game box scores into season averages.

    Takes the DataFrame from fetch_team_season_boxscores and computes:
        - Per-game averages for all numeric stats
        - Win/loss record
        - Close game record (margin <= 5)
        - Standard deviations for volatility metrics
    """
    if game_df.empty:
        return {}

    stats = {}

    # Record
    stats["wins"] = int((game_df["result"] == "W").sum())
    stats["losses"] = int((game_df["result"] == "L").sum())
    stats["games"] = len(game_df)
    stats["win_pct"] = stats["wins"] / stats["games"] if stats["games"] > 0 else 0

    # Close games (margin <= 5)
    close = game_df[game_df["margin"].abs() <= 5]
    stats["close_games"] = len(close)
    stats["close_wins"] = int((close["result"] == "W").sum()) if not close.empty else 0
    stats["close_game_record"] = stats["close_wins"] / stats["close_games"] if stats["close_games"] > 0 else 0.5

    # Per-game averages for ESPN-specific stats
    espn_stats = [
        "turnoverPoints", "fastBreakPoints", "pointsInPaint",
        "totalTurnovers", "assists", "steals", "blocks", "fouls",
        "fieldGoalsMade", "fieldGoalsAttempted",
        "threePointFieldGoalsMade", "threePointFieldGoalsAttempted",
        "freeThrowsMade", "freeThrowsAttempted",
        "totalRebounds", "offensiveRebounds", "defensiveRebounds",
        "largestLead",
    ]

    for stat in espn_stats:
        if stat in game_df.columns:
            col = pd.to_numeric(game_df[stat], errors="coerce")
            stats[f"avg_{stat}"] = col.mean()
            stats[f"std_{stat}"] = col.std()

    # Scoring averages and volatility
    stats["avg_score"] = game_df["team_score"].mean()
    stats["avg_opp_score"] = game_df["opponent_score"].mean()
    stats["avg_margin"] = game_df["margin"].mean()
    stats["std_margin"] = game_df["margin"].std()
    stats["std_score"] = game_df["team_score"].std()

    # Shooting percentages
    for made, att, pct_name in [
        ("fieldGoalsMade", "fieldGoalsAttempted", "fg_pct"),
        ("threePointFieldGoalsMade", "threePointFieldGoalsAttempted", "three_pct"),
        ("freeThrowsMade", "freeThrowsAttempted", "ft_pct"),
    ]:
        if made in game_df.columns and att in game_df.columns:
            m = pd.to_numeric(game_df[made], errors="coerce").sum()
            a = pd.to_numeric(game_df[att], errors="coerce").sum()
            stats[pct_name] = m / a if a > 0 else 0

    # FT% volatility (critical for tournament layer)
    if "freeThrowsMade" in game_df.columns and "freeThrowsAttempted" in game_df.columns:
        game_ft_pcts = []
        for _, row in game_df.iterrows():
            ftm = pd.to_numeric(row.get("freeThrowsMade", 0), errors="coerce") or 0
            fta = pd.to_numeric(row.get("freeThrowsAttempted", 0), errors="coerce") or 0
            if fta >= 5:  # Only count games with meaningful FT attempts
                game_ft_pcts.append(ftm / fta)
        if game_ft_pcts:
            stats["ft_pct_std"] = pd.Series(game_ft_pcts).std()

    return stats


# =============================================================================
# Team Name Matching (ESPN <-> Torvik)
# =============================================================================

def build_name_mapping(espn_teams: pd.DataFrame) -> dict[str, int]:
    """
    Build a lookup dict mapping various team name formats to ESPN IDs.

    ESPN uses "displayName" like "Duke Blue Devils" while Torvik uses "Duke".
    This builds a map so we can cross-reference.
    """
    mapping = {}
    for _, row in espn_teams.iterrows():
        espn_id = row["espn_id"]
        # Map all name variants to the same ID
        mapping[row["display_name"].lower()] = espn_id
        mapping[row["location"].lower()] = espn_id
        mapping[row["name"].lower()] = espn_id
        mapping[row["abbreviation"].lower()] = espn_id
        mapping[row["slug"].lower()] = espn_id
    return mapping


def find_espn_id(team_name: str, espn_teams: pd.DataFrame | None = None) -> int | None:
    """Find an ESPN team ID from a team name (partial match supported)."""
    if espn_teams is None:
        espn_teams = fetch_teams()

    name_lower = team_name.lower().strip()

    # Try exact matches first
    mapping = build_name_mapping(espn_teams)
    if name_lower in mapping:
        return mapping[name_lower]

    # Try partial / contains match
    for _, row in espn_teams.iterrows():
        if (name_lower in row["display_name"].lower() or
            name_lower in row["location"].lower() or
            row["location"].lower() in name_lower):
            return row["espn_id"]

    logger.warning(f"No ESPN team found for '{team_name}'")
    return None


# =============================================================================
# CLI Test
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    print("🏀 BracketIQ — ESPN Scraper Test\n")

    # Test 1: Fetch all teams
    print("Step 1: Fetching team directory...")
    teams = fetch_teams()
    print(f"  ✅ {len(teams)} teams loaded")
    print(f"  Sample: {teams[['espn_id', 'display_name', 'abbreviation']].head(3).to_string(index=False)}\n")

    # Test 2: Find a team ID
    print("Step 2: Looking up Duke...")
    duke_id = find_espn_id("Duke", teams)
    print(f"  ✅ Duke ESPN ID: {duke_id}\n")

    if duke_id:
        # Test 3: Fetch schedule
        print("Step 3: Fetching Duke's schedule...")
        schedule = fetch_team_schedule(duke_id)
        completed = [g for g in schedule if g.get("completed")]
        print(f"  ✅ {len(completed)} completed games found")
        if completed:
            last = completed[-1]
            print(f"  Last game: vs {last['opponent_name']} — {last['team_score']}-{last['opponent_score']}\n")

        # Test 4: Fetch a single game box score (most recent)
        if completed:
            print("Step 4: Fetching box score for most recent game...")
            game = fetch_game_boxscore(completed[-1]["game_id"])
            if game:
                for team in game["teams"]:
                    stats = team["stats"]
                    extras = {k: v for k, v in stats.items()
                              if k in ["benchPoints", "turnoverPoints", "fastBreakPoints", "pointsInPaint"]}
                    print(f"  {team['team_name']}: {extras}")
            print()

        # Test 5: Aggregate season stats (limit to 5 games for speed)
        print("Step 5: Aggregating stats (last 5 games for speed)...")
        game_df = fetch_team_season_boxscores(duke_id, max_games=5)
        if not game_df.empty:
            agg = aggregate_season_stats(game_df)
            def _fmt(val):
                return f"{val:.1f}" if isinstance(val, (int, float)) else "N/A"

            print(f"  ✅ Record: {agg.get('wins', 0)}-{agg.get('losses', 0)}")
            print(f"  Avg pts off TO: {_fmt(agg.get('avg_turnoverPoints'))}")
            print(f"  Avg fast break: {_fmt(agg.get('avg_fastBreakPoints'))}")
            print(f"  Avg paint pts:  {_fmt(agg.get('avg_pointsInPaint'))}")
            print(f"  Avg largest lead: {_fmt(agg.get('avg_largestLead'))}")
            print(f"  Avg lead pct:   {_fmt(agg.get('avg_leadPercentage'))}")
            print(f"  FT%: {_fmt(agg.get('ft_pct'))}")
            print(f"  FT% volatility: {_fmt(agg.get('ft_pct_std'))}")

    print("\n✅ ESPN scraper test complete.")