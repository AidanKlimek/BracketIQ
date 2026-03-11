"""
BracketIQ - Cache Manager
============================
Manages cached data files. Use before tournament starts to ensure
fresh data, or selectively clear stale caches.

Usage:
    python -m data.cache_manager status     # Show cache status
    python -m data.cache_manager clear      # Clear ALL caches
    python -m data.cache_manager clear-espn # Clear only ESPN game caches
    python -m data.cache_manager clear-torvik # Clear only Torvik caches
"""

import sys
import logging
from pathlib import Path
from datetime import datetime

from config.settings import CACHE_DIR

logger = logging.getLogger(__name__)


def cache_status():
    """Show what's currently cached and how old it is."""
    if not CACHE_DIR.exists():
        print("📁 Cache directory doesn't exist yet.")
        return

    files = sorted(CACHE_DIR.glob("*"))
    if not files:
        print("📁 Cache is empty.")
        return

    # Categorize
    torvik_files = [f for f in files if f.name.startswith("torvik_")]
    espn_team_files = [f for f in files if f.name.startswith("espn_teams") or f.name.startswith("espn_schedule")]
    espn_game_files = [f for f in files if f.name.startswith("espn_game_")]
    other_files = [f for f in files if f not in torvik_files + espn_team_files + espn_game_files]

    total_size = sum(f.stat().st_size for f in files)

    print(f"\n📁 Cache Status ({CACHE_DIR})")
    print(f"   Total: {len(files)} files, {total_size / 1024:.0f} KB\n")

    def _print_group(name: str, file_list: list[Path]):
        if not file_list:
            return
        oldest = min(f.stat().st_mtime for f in file_list)
        newest = max(f.stat().st_mtime for f in file_list)
        oldest_dt = datetime.fromtimestamp(oldest)
        newest_dt = datetime.fromtimestamp(newest)
        size = sum(f.stat().st_size for f in file_list)
        print(f"   {name}:")
        print(f"     Files: {len(file_list)} ({size / 1024:.0f} KB)")
        print(f"     Oldest: {oldest_dt.strftime('%Y-%m-%d %H:%M')}")
        print(f"     Newest: {newest_dt.strftime('%Y-%m-%d %H:%M')}")

    _print_group("Torvik data", torvik_files)
    _print_group("ESPN teams/schedules", espn_team_files)
    _print_group("ESPN game box scores", espn_game_files)
    _print_group("Other", other_files)
    print()


def clear_all():
    """Clear entire cache."""
    count = _clear_pattern("*")
    print(f"🗑️  Cleared {count} cached files.")


def clear_espn():
    """Clear only ESPN caches (teams, schedules, game box scores)."""
    count = _clear_pattern("espn_*")
    print(f"🗑️  Cleared {count} ESPN cached files.")


def clear_espn_games():
    """Clear only ESPN game box score caches (keeps team/schedule caches)."""
    count = _clear_pattern("espn_game_*")
    print(f"🗑️  Cleared {count} ESPN game cached files.")


def clear_torvik():
    """Clear only Torvik caches."""
    count = _clear_pattern("torvik_*")
    print(f"🗑️  Cleared {count} Torvik cached files.")


def clear_current_season():
    """Clear only current season caches (keeps historical for archetype)."""
    count = 0
    count += _clear_pattern("torvik_team_results_2026*")
    count += _clear_pattern("torvik_four_factors_2026*")
    count += _clear_pattern("espn_teams*")
    count += _clear_pattern("espn_schedule_*")
    count += _clear_pattern("espn_game_*")
    print(f"🗑️  Cleared {count} current season cached files.")
    print(f"   Historical data (2021-2025) preserved for archetype matching.")


def _clear_pattern(pattern: str) -> int:
    """Delete files matching a glob pattern in the cache dir."""
    if not CACHE_DIR.exists():
        return 0
    files = list(CACHE_DIR.glob(pattern))
    for f in files:
        f.unlink()
    return len(files)


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    args = sys.argv[1:]
    command = args[0] if args else "status"

    if command == "status":
        cache_status()
    elif command == "clear":
        clear_all()
    elif command == "clear-espn":
        clear_espn()
    elif command == "clear-espn-games":
        clear_espn_games()
    elif command == "clear-torvik":
        clear_torvik()
    elif command == "clear-current":
        clear_current_season()
    else:
        print(f"Unknown command: {command}")
        print("Commands: status, clear, clear-espn, clear-espn-games, clear-torvik, clear-current")