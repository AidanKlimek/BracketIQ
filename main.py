"""
BracketIQ - CLI Entry Point
===============================
Usage:
    python main.py rank                         # Quick rankings (Torvik only, fast)
    python main.py rank --full                  # Full rankings with ESPN for top 68
    python main.py rank --tournament            # Rankings for tournament teams only
    python main.py score "Duke"                 # Detailed report for one team (with ESPN)
    python main.py matchup "Duke" "Houston"     # Head-to-head matchup analysis
    python main.py export                       # Export rankings to CSV
    python main.py export --full                # Export full rankings to CSV
    python main.py backtest                     # Validate model against 2021-2025
    python main.py cache status                 # Show cache status
    python main.py cache clear                  # Clear all caches
    python main.py cache clear-current          # Clear current season (keep historical)
    python main.py refresh                      # Clear current season cache and re-rank
"""

import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def cmd_rank(full: bool = False, tournament: bool = False):
    """Generate and display power rankings."""
    from data.integrator import build_full_dataset, get_tournament_teams
    from data.torvik_scraper import fetch_all_torvik_data
    from scoring.team_grader import grade_all_teams

    if tournament:
        print("🏀 Building tournament rankings (Torvik + ESPN)...\n")
        df = build_full_dataset(tournament_only=True)
    elif full:
        print("🏀 Building full rankings (Torvik + ESPN for top 68)...\n")
        torvik_df = fetch_all_torvik_data()
        team_names = get_tournament_teams(torvik_df)
        print(f"   Pulling ESPN data for {len(team_names)} teams...\n")
        df = build_full_dataset(team_names=team_names)
    else:
        print("🏀 Building quick rankings (Torvik only)...\n")
        print("   Tip: Use --full or --tournament for ESPN-enhanced rankings.\n")
        df = fetch_all_torvik_data()

    rankings = grade_all_teams(df)

    print(f"\n{'='*65}")
    print(f"  BracketIQ Power Rankings — Top 25")
    print(f"{'='*65}")
    for idx, row in rankings.head(25).iterrows():
        print(f"  {idx:>3d}. {row['team']:<22s} {row['composite']:>5.1f}  [{row['tier']}]  "
              f"(B:{row['base_score']:>4.1f} C:{row['context_score']:>4.1f} T:{row['tournament_score']:>4.1f})")

    print(f"\n  Tier Distribution:")
    for tier in ["S", "A", "B", "C", "D", "F"]:
        count = len(rankings[rankings["tier"] == tier])
        if count > 0:
            print(f"    {tier}: {count}")

    return rankings


def cmd_score(team_name: str):
    """Detailed scoring report for a single team (always uses ESPN)."""
    from data.integrator import build_full_dataset
    from scoring.team_grader import get_team_report, print_team_report

    print(f"🏀 Scoring {team_name} (Torvik + ESPN)...\n")
    df = build_full_dataset(team_names=[team_name])
    report = get_team_report(team_name, df)
    if report:
        print_team_report(report)
    else:
        print(f"❌ Team '{team_name}' not found.")


def cmd_matchup(team_a_name: str, team_b_name: str):
    """Head-to-head matchup analysis (always uses ESPN)."""
    import numpy as np
    from data.integrator import build_full_dataset
    from scoring.team_grader import grade_all_teams
    from matchup.analyzer import analyze_matchup, print_matchup

    print(f"🏀 Analyzing: {team_a_name} vs {team_b_name}...\n")
    df = build_full_dataset(team_names=[team_a_name, team_b_name])
    rankings = grade_all_teams(df)

    def _get(name):
        mask = df["team"].str.lower().str.contains(name.lower(), na=False)
        if not mask.any():
            return None, None
        stats = df[mask].iloc[0].to_dict()
        r_mask = rankings["team"].str.lower().str.contains(name.lower(), na=False)
        score = float(rankings[r_mask].iloc[0]["composite"]) if r_mask.any() else None
        return stats, score

    a_stats, a_score = _get(team_a_name)
    b_stats, b_score = _get(team_b_name)

    if not a_stats:
        print(f"❌ Team '{team_a_name}' not found.")
        return
    if not b_stats:
        print(f"❌ Team '{team_b_name}' not found.")
        return

    result = analyze_matchup(a_stats, b_stats, a_score, b_score)
    print_matchup(result)

    # Offer CSV export
    from output.csv_export import export_matchup
    export_matchup(result)

    return result


def cmd_export(full: bool = False, tournament: bool = False):
    """Export rankings to CSV."""
    from output.csv_export import export_rankings
    rankings = cmd_rank(full=full, tournament=tournament)
    export_rankings(rankings)


def cmd_cache(action: str):
    """Manage data caches."""
    from data.cache_manager import (
        cache_status, clear_all, clear_espn, clear_torvik,
        clear_current_season, clear_espn_games,
    )

    actions = {
        "status": cache_status,
        "clear": clear_all,
        "clear-espn": clear_espn,
        "clear-espn-games": clear_espn_games,
        "clear-torvik": clear_torvik,
        "clear-current": clear_current_season,
    }

    func = actions.get(action)
    if func:
        func()
    else:
        print(f"Unknown cache action: {action}")
        print(f"Available: {', '.join(actions.keys())}")


def cmd_refresh():
    """Clear current season caches and re-run full rankings."""
    from data.cache_manager import clear_current_season

    print("🔄 Refreshing all current season data...\n")
    clear_current_season()
    print()
    cmd_rank(full=True)


def main():
    args = sys.argv[1:]

    if not args:
        print(__doc__)
        return

    command = args[0].lower()

    if command == "rank":
        full = "--full" in args
        tournament = "--tournament" in args
        cmd_rank(full=full, tournament=tournament)

    elif command == "score":
        if len(args) < 2:
            print("Usage: python main.py score \"Team Name\"")
            return
        cmd_score(args[1])

    elif command == "matchup":
        if len(args) < 3:
            print("Usage: python main.py matchup \"Team A\" \"Team B\"")
            return
        cmd_matchup(args[1], args[2])

    elif command == "export":
        full = "--full" in args
        tournament = "--tournament" in args
        cmd_export(full=full, tournament=tournament)

    elif command == "backtest":
        from backtest.validate import run_backtest
        run_backtest()

    elif command == "cache":
        action = args[1] if len(args) > 1 else "status"
        cmd_cache(action)

    elif command == "refresh":
        cmd_refresh()

    else:
        print(f"Unknown command: {command}")
        print(__doc__)


if __name__ == "__main__":
    main()