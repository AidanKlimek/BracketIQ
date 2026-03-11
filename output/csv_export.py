"""
BracketIQ - CSV Export
========================
Exports rankings and matchup analyses to CSV files.
"""

import logging
from pathlib import Path
from datetime import datetime

import pandas as pd

from config.settings import EXPORT_DIR
from config.weights import CURRENT_YEAR

logger = logging.getLogger(__name__)


def export_rankings(rankings_df: pd.DataFrame, filename: str | None = None) -> Path:
    """Export power rankings to CSV."""
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        filename = f"bracketiq_rankings_{CURRENT_YEAR}_{timestamp}.csv"

    filepath = EXPORT_DIR / filename
    rankings_df.to_csv(filepath)
    logger.info(f"Exported rankings to {filepath}")
    print(f"📄 Rankings exported: {filepath}")
    return filepath


def export_matchup(result: dict, filename: str | None = None) -> Path:
    """Export a matchup analysis to CSV."""
    a = result["team_a"]
    b = result["team_b"]

    if filename is None:
        filename = f"matchup_{a}_vs_{b}.csv".replace(" ", "_")

    rows = []
    rows.append({"metric": "Team A", "value": a})
    rows.append({"metric": "Team B", "value": b})
    rows.append({"metric": "Composite A", "value": result.get("composite_a")})
    rows.append({"metric": "Composite B", "value": result.get("composite_b")})
    rows.append({"metric": "Raw Edge", "value": result.get("raw_edge")})

    for dim_name, dim in result.get("dimensions", {}).items():
        rows.append({
            "metric": f"{dim_name} - edge",
            "value": dim.get("edge"),
        })
        rows.append({
            "metric": f"{dim_name} - adjustment",
            "value": dim.get("adjustment"),
        })
        rows.append({
            "metric": f"{dim_name} - detail",
            "value": dim.get("detail"),
        })

    rows.append({"metric": "Net Adjustment", "value": result.get("net_adjustment")})
    rows.append({"metric": "Adjusted Edge", "value": result.get("adjusted_edge")})
    rows.append({"metric": "Pick", "value": result.get("pick")})
    rows.append({"metric": "Confidence", "value": result.get("confidence")})

    df = pd.DataFrame(rows)
    filepath = EXPORT_DIR / filename
    df.to_csv(filepath, index=False)
    logger.info(f"Exported matchup to {filepath}")
    print(f"📄 Matchup exported: {filepath}")
    return filepath