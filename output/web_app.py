"""
BracketIQ - Streamlit Web UI
================================
Launch with: streamlit run output/web_app.py

Provides:
  - Power rankings table with tier badges
  - Detailed team reports
  - Head-to-head matchup analyzer
  - CSV export buttons
"""

import streamlit as st
import pandas as pd
import numpy as np
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# Page config
st.set_page_config(
    page_title="BracketIQ",
    page_icon="🏀",
    layout="wide",
)

# =============================================================================
# Data Loading (cached by Streamlit so it only runs once per session)
# =============================================================================

@st.cache_data(ttl=3600, show_spinner="Loading Torvik data...")
def load_torvik():
    from data.torvik_scraper import fetch_all_torvik_data
    return fetch_all_torvik_data()


@st.cache_data(ttl=3600, show_spinner="Loading ESPN data (this may take a while)...")
def load_full_dataset(team_names: tuple):
    from data.integrator import build_full_dataset
    return build_full_dataset(team_names=list(team_names))


@st.cache_data(ttl=3600, show_spinner="Grading teams...")
def grade_teams(df_hash: str, df: pd.DataFrame):
    from scoring.team_grader import grade_all_teams
    return grade_all_teams(df)


@st.cache_data(ttl=3600, show_spinner="Loading ESPN data for matchup...")
def load_matchup_data(team_a: str, team_b: str):
    from data.integrator import build_full_dataset
    return build_full_dataset(team_names=[team_a, team_b])


def get_team_list(df: pd.DataFrame) -> list[str]:
    """Get sorted list of team names from DataFrame."""
    if "team" in df.columns:
        return sorted(df["team"].dropna().unique().tolist())
    return []


# =============================================================================
# Sidebar Navigation
# =============================================================================

st.sidebar.title("🏀 BracketIQ")
page = st.sidebar.radio(
    "Navigate",
    ["Power Rankings", "Team Report", "Matchup Analyzer", "About"],
)

# Data source toggle
st.sidebar.markdown("---")
st.sidebar.subheader("Data Settings")
use_espn = st.sidebar.checkbox("Include ESPN data", value=False,
    help="Pulls game-by-game box scores for trend/volatility analysis. "
         "Slower on first load but more accurate.")

# Load base data
torvik_df = load_torvik()
team_list = get_team_list(torvik_df)


# =============================================================================
# Page: Power Rankings
# =============================================================================

if page == "Power Rankings":
    st.title("📊 Power Rankings")

    if use_espn:
        st.info("ESPN mode: Loading game-by-game data for top 68 teams. First run may take ~35 minutes.")
        from data.integrator import get_tournament_teams
        from config.tournament import get_tournament_team_names

        tourney_teams = get_tournament_team_names()
        if not tourney_teams:
            tourney_teams = get_tournament_teams(torvik_df)

        df = load_full_dataset(tuple(tourney_teams))
    else:
        df = torvik_df

    # Grade
    df_hash = str(len(df)) + str(df.columns.tolist()[:5])
    rankings = grade_teams(df_hash, df)

    # Tier filter
    tiers = st.multiselect(
        "Filter by tier",
        ["S", "A", "B", "C", "D", "F"],
        default=["S", "A", "B"],
    )
    filtered = rankings[rankings["tier"].isin(tiers)]

    # Display count
    st.markdown(f"**Showing {len(filtered)} teams** ({', '.join(tiers)})")

    # Color-code tiers
    def tier_color(tier):
        colors = {"S": "🟣", "A": "🔵", "B": "🟢", "C": "🟡", "D": "🟠", "F": "🔴"}
        return colors.get(tier, "⚪")

    # Build display table
    display_df = filtered.copy()
    display_df.insert(0, "", display_df["tier"].map(tier_color))
    display_df = display_df.rename(columns={
        "team": "Team",
        "composite": "Score",
        "tier": "Tier",
        "base_score": "Base",
        "context_score": "Context",
        "tournament_score": "Tournament",
    })

    st.dataframe(
        display_df[["", "Team", "Score", "Tier", "Base", "Context", "Tournament"]],
        use_container_width=True,
        height=600,
    )

    # CSV download
    csv = rankings.to_csv(index=True)
    st.download_button(
        "📥 Download Full Rankings CSV",
        csv,
        "bracketiq_rankings.csv",
        "text/csv",
    )


# =============================================================================
# Page: Team Report
# =============================================================================

elif page == "Team Report":
    st.title("📋 Team Report")

    selected_team = st.selectbox("Select a team", team_list)

    if selected_team and st.button("Generate Report", type="primary"):
        with st.spinner(f"Analyzing {selected_team}..."):
            # Always use ESPN for individual team reports
            report_df = load_full_dataset(tuple([selected_team]))
            from scoring.team_grader import get_team_report
            report = get_team_report(selected_team, report_df)

        if report:
            # Header
            col1, col2, col3 = st.columns(3)
            col1.metric("Composite Score", f"{report['composite']:.1f}")
            col2.metric("Tier", report["tier"])
            col3.metric("Conference", report.get("conf", "N/A"))

            # Tier scores
            st.markdown("### Tier Breakdown")
            col1, col2, col3 = st.columns(3)
            col1.metric("Base Layer (40%)", f"{report['base_score']:.1f} / 100")
            col2.metric("Context Layer (35%)", f"{report['context_score']:.1f} / 100")
            col3.metric("Tournament Layer (25%)", f"{report['tournament_score']:.1f} / 100")

            # Detailed breakdown
            for tier_name, tier_breakdown in report["breakdown"].items():
                available = {k: v for k, v in tier_breakdown.items() if v["value"] is not None}
                if not available:
                    continue

                st.markdown(f"### {tier_name.title()} Layer Details")
                sorted_stats = sorted(available.items(), key=lambda x: x[1]["contribution"], reverse=True)

                rows = []
                for stat, info in sorted_stats:
                    rows.append({
                        "Stat": stat,
                        "Percentile": f"{info['value']:.1f}",
                        "Weight": f"{info['weight']:.2f}",
                        "Contribution": f"{info['contribution']:.2f}",
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.error(f"Team '{selected_team}' not found.")


# =============================================================================
# Page: Matchup Analyzer
# =============================================================================

elif page == "Matchup Analyzer":
    st.title("⚔️ Matchup Analyzer")

    col1, col2 = st.columns(2)
    team_a = col1.selectbox("Team A", team_list, index=0)
    team_b = col2.selectbox("Team B", team_list, index=min(1, len(team_list) - 1))

    if team_a == team_b:
        st.warning("Please select two different teams.")
    elif st.button("Analyze Matchup", type="primary"):
        with st.spinner(f"Analyzing {team_a} vs {team_b}..."):
            matchup_df = load_matchup_data(team_a, team_b)
            rankings = grade_teams(
                f"matchup_{team_a}_{team_b}",
                matchup_df,
            )

            # Get team data
            def _get(name):
                mask = matchup_df["team"].str.lower().str.contains(name.lower(), na=False)
                if not mask.any():
                    return None, None
                stats = matchup_df[mask].iloc[0].to_dict()
                r_mask = rankings["team"].str.lower().str.contains(name.lower(), na=False)
                score = float(rankings[r_mask].iloc[0]["composite"]) if r_mask.any() else None
                return stats, score

            a_stats, a_score = _get(team_a)
            b_stats, b_score = _get(team_b)

        if a_stats and b_stats:
            from matchup.analyzer import analyze_matchup
            result = analyze_matchup(a_stats, b_stats, a_score, b_score)

            # Pick header
            pick = result["pick"]
            confidence = result["confidence"]

            if pick == "Toss-up":
                st.warning(f"### 🤝 Toss-up — Too close to call ({confidence})")
            else:
                st.success(f"### 📌 Pick: {pick} (Confidence: {confidence})")

            # Composite scores
            col1, col2, col3 = st.columns(3)
            col1.metric(f"{team_a} Score", f"{a_score:.1f}" if a_score else "N/A")
            col2.metric(f"{team_b} Score", f"{b_score:.1f}" if b_score else "N/A")
            col3.metric("Adjusted Edge", f"{result['adjusted_edge']:+.1f}")

            # Dimension breakdown
            st.markdown("### Matchup Dimensions")
            dim_rows = []
            for dim_name, dim in result["dimensions"].items():
                adj = dim.get("adjustment", 0)
                dim_rows.append({
                    "Dimension": dim_name.replace("_", " ").title(),
                    "Edge": dim.get("edge", "?"),
                    "Adjustment": f"{adj:+.1f}" if adj != 0 else "--",
                    "Detail": dim.get("detail", ""),
                })
            st.dataframe(pd.DataFrame(dim_rows), use_container_width=True, hide_index=True)

            # Summary
            st.markdown("### Summary")
            st.markdown(f"""
            | Metric | Value |
            |--------|-------|
            | Raw Edge | {result['raw_edge']:+.1f} (favors {team_a if result['raw_edge'] > 0 else team_b}) |
            | Net Matchup Adjustment | {result['net_adjustment']:+.1f} |
            | **Adjusted Edge** | **{result['adjusted_edge']:+.1f}** |
            | **Pick** | **{pick}** ({confidence}) |
            """)

            # CSV download
            from output.csv_export import export_matchup
            import io
            matchup_rows = [
                {"metric": "Pick", "value": pick},
                {"metric": "Confidence", "value": confidence},
                {"metric": "Adjusted Edge", "value": result["adjusted_edge"]},
            ]
            for dim_name, dim in result["dimensions"].items():
                matchup_rows.append({"metric": f"{dim_name} edge", "value": dim.get("edge")})
                matchup_rows.append({"metric": f"{dim_name} detail", "value": dim.get("detail")})

            csv = pd.DataFrame(matchup_rows).to_csv(index=False)
            st.download_button(
                "📥 Download Matchup CSV",
                csv,
                f"matchup_{team_a}_vs_{team_b}.csv",
                "text/csv",
            )
        else:
            st.error("Could not find one or both teams in the data.")


# =============================================================================
# Page: About
# =============================================================================

elif page == "About":
    st.title("🏀 BracketIQ")
    st.markdown("""
    **A data-driven March Madness bracket tool that goes beyond the four factors.**

    ### How It Works

    Every team receives a composite score (0-100) built from three weighted tiers:

    | Tier | Weight | What It Captures |
    |------|--------|------------------|
    | **Base Layer** | 40% | Adjusted efficiency, four factors, shooting splits |
    | **Context Layer** | 35% | Strength of schedule, trends, volatility, resume quality |
    | **Tournament Layer** | 25% | Historical archetype matching, upset profile, FT reliability |

    ### Data Sources
    - **Bart Torvik (T-Rank)** — Adjusted efficiency, four factors, SOS, tempo
    - **ESPN** — Game-by-game box scores for trend/volatility analysis

    ### Tier Labels
    - 🟣 **S** (90-100): Elite — legitimate title contenders
    - 🔵 **A** (80-90): Strong — Sweet 16 / Elite 8 caliber
    - 🟢 **B** (70-80): Solid — Round of 32 caliber
    - 🟡 **C** (60-70): Average — Could win a game, could lose R1
    - 🟠 **D** (50-60): Below average — likely early exit
    - 🔴 **F** (0-50): Weak — major upset needed to advance

    ### Backtest Results (2021-2025)
    - Champions averaged **#5.2** in model rankings
    - **85%** of Final Four teams were in model's top 25
    - All 5 champions rated **S-tier**

    ---
    *Built for bracket-building, not betting. No model predicts March perfectly — the madness is the point.*
    """)