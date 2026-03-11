"""
BracketIQ - CLI Entry Point
===============================
Usage:
    python main.py rank                         # Top 25 power rankings (Torvik only, fast)
    python main.py rank --full                  # Full rankings with ESPN data for top 68
    python main.py score "Duke"                 # Detailed report for one team
    python main.py matchup "Duke" "Houston"     # Head-to-head matchup analysis
    python main.py export                       # Export rankings to CSV
    python main.py export --full                # Export full rankings (with ESPN) to CSV
    python main.py backtest                     # Validate model against 2021-2025 tournaments
"""

import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def cmd_rank(full: bool = False):
    """Generate and display power rankings."""
    from data.torvik_scraper import fetch_all_torvik_data
    from data.integrator import build_full_dataset, get_tournament_teams
    from scoring.team_grader import grade_all_teams

    if full:
        print("🏀 Building full rankings (Torvik + ESPN)...\n")
        torvik_df = fetch_all_torvik_data()
        team_names = get_tournament_teams(torvik_df)
        print(f"   Pulling ESPN data for {len(team_names)} teams (this may take a while)...\n")
        df = build_full_dataset(team_names=team_names)
    else:
        print("🏀 Building rankings (Torvik only — use --full for ESPN data)...\n")
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
    """Detailed scoring report for a single team."""
    from data.integrator import build_full_dataset
    from scoring.team_grader import get_team_report, print_team_report

    print(f"🏀 Scoring {team_name} (with ESPN data)...\n")
    df = build_full_dataset(team_names=[team_name])
    report = get_team_report(team_name, df)
    if report:
        print_team_report(report)
    else:
        print(f"❌ Team '{team_name}' not found.")


def cmd_matchup(team_a_name: str, team_b_name: str):
    """Head-to-head matchup analysis."""
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
    return result


def cmd_export(full: bool = False):
    """Export rankings to CSV."""
    from output.csv_export import export_rankings
    rankings = cmd_rank(full=full)
    export_rankings(rankings)


def main():
    args = sys.argv[1:]

    if not args:
        print(__doc__)
        return

    command = args[0].lower()

    if command == "rank":
        full = "--full" in args
        cmd_rank(full=full)

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
        cmd_export(full=full)

    elif command == "backtest":
        from backtest.validate import run_backtest
        run_backtest()

    else:
        print(f"Unknown command: {command}")
        print(__doc__)


if __name__ == "__main__":
    main()