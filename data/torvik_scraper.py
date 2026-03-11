"""
BracketIQ - Bart Torvik Data Scraper
======================================
Pulls adjusted team stats from Bart Torvik's T-Rank system.

Torvik provides direct CSV/JSON endpoints (no scraping needed):
  - {year}_team_results.csv — Full season team stats
  - teamslicejson.php       — Filterable team stats with four factors
  - timemachine/             — Historical snapshots (pre-tournament ratings)

Data includes: AdjO, AdjD, Barthag, tempo, four factors, SOS, WAB, and more.

Be respectful of Bart's servers — use caching and don't spam requests.
"""

import io
import json
import time
import gzip
import logging
from pathlib import Path
from datetime import datetime, timedelta

import requests
import pandas as pd

from config.settings import (
    CACHE_DIR, TORVIK_REQUEST_DELAY, REQUEST_HEADERS, CACHE_TTL_HOURS,
)
from config.weights import DATA_SOURCES, CURRENT_YEAR, HISTORICAL_YEARS

logger = logging.getLogger(__name__)


# =============================================================================
# Cache Helpers
# =============================================================================

def _cache_path(filename: str) -> Path:
    """Return full path to a cache file."""
    return CACHE_DIR / filename


def _cache_is_fresh(filepath: Path) -> bool:
    """Check if a cached file exists and is still within the TTL."""
    if not filepath.exists():
        return False
    modified = datetime.fromtimestamp(filepath.stat().st_mtime)
    age = datetime.now() - modified
    return age < timedelta(hours=CACHE_TTL_HOURS)


def _save_cache(filepath: Path, data: str) -> None:
    """Write raw response data to cache."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(data, encoding="utf-8")
    logger.debug(f"Cached: {filepath.name}")


def _load_cache(filepath: Path) -> str:
    """Read raw data from cache."""
    logger.debug(f"Loading from cache: {filepath.name}")
    return filepath.read_text(encoding="utf-8")


# =============================================================================
# HTTP Helpers
# =============================================================================

def _fetch(url: str, delay: float = None) -> str:
    """
    Make a GET request with polite delay and error handling.
    Returns raw response text.
    """
    if delay is None:
        delay = TORVIK_REQUEST_DELAY

    time.sleep(delay)
    logger.info(f"Fetching: {url}")

    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def _fetch_gzip(url: str, delay: float = None) -> str:
    """Fetch and decompress a gzipped JSON file (for time machine data)."""
    if delay is None:
        delay = TORVIK_REQUEST_DELAY

    time.sleep(delay)
    logger.info(f"Fetching (gzip): {url}")

    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    decompressed = gzip.decompress(resp.content)
    return decompressed.decode("utf-8")


# =============================================================================
# Core Data Fetchers
# =============================================================================

def fetch_team_results(year: int = None, force_refresh: bool = False) -> pd.DataFrame:
    """
    Fetch full season team results from Torvik CSV endpoint.

    Returns a DataFrame with one row per team, including:
        - Team name, conference
        - Record, wins, games
        - AdjO, AdjD, AdjT (tempo), Barthag
        - SOS metrics
        - Seed (if tournament team)

    Args:
        year: Season year (e.g., 2026 for the 2025-26 season). Defaults to CURRENT_YEAR.
        force_refresh: If True, bypass cache.

    Returns:
        pd.DataFrame with team-level season stats.
    """
    if year is None:
        year = CURRENT_YEAR

    cache_file = _cache_path(f"torvik_team_results_{year}.csv")

    # Check cache first
    if not force_refresh and _cache_is_fresh(cache_file):
        raw = _load_cache(cache_file)
        return _parse_team_results_csv(raw)

    # Fetch fresh data
    url = DATA_SOURCES["torvik"]["team_results_csv"].format(year=year)
    try:
        raw = _fetch(url)
        _save_cache(cache_file, raw)
        return _parse_team_results_csv(raw)
    except requests.RequestException as e:
        logger.error(f"Failed to fetch Torvik team results for {year}: {e}")
        # Fall back to stale cache if it exists
        if cache_file.exists():
            logger.warning("Using stale cache as fallback.")
            raw = _load_cache(cache_file)
            return _parse_team_results_csv(raw)
        raise


def _parse_team_results_csv(raw_csv: str) -> pd.DataFrame:
    """Parse the raw CSV text into a cleaned DataFrame."""
    df = pd.read_csv(io.StringIO(raw_csv))

    # Standardize column names — Torvik's CSV headers can vary slightly
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")

    # Ensure numeric types for key columns
    numeric_cols = [
        "barthag", "adj_o", "adj_d", "adj_t",
        "wab", "seed",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    logger.info(f"Parsed {len(df)} teams from Torvik CSV.")
    return df


def fetch_four_factors(year: int = None, force_refresh: bool = False) -> pd.DataFrame:
    """
    Fetch four factors data from Torvik's team slice JSON endpoint.

    Returns a DataFrame with offensive and defensive four factors:
        - off_efg, off_to, off_or, off_ftr (offensive)
        - def_efg, def_to, def_or, def_ftr (defensive)
        - Plus AdjO, AdjD, AdjT, Barthag, record, conference

    Args:
        year: Season year. Defaults to CURRENT_YEAR.
        force_refresh: If True, bypass cache.

    Returns:
        pd.DataFrame with four factors per team.
    """
    if year is None:
        year = CURRENT_YEAR

    cache_file = _cache_path(f"torvik_four_factors_{year}.json")

    if not force_refresh and _cache_is_fresh(cache_file):
        raw = _load_cache(cache_file)
        return _parse_four_factors_json(raw)

    url = DATA_SOURCES["torvik"]["four_factors"].format(year=year)
    try:
        raw = _fetch(url)
        _save_cache(cache_file, raw)
        return _parse_four_factors_json(raw)
    except requests.RequestException as e:
        logger.error(f"Failed to fetch Torvik four factors for {year}: {e}")
        if cache_file.exists():
            logger.warning("Using stale cache as fallback.")
            raw = _load_cache(cache_file)
            return _parse_four_factors_json(raw)
        raise


def _parse_four_factors_json(raw_json: str) -> pd.DataFrame:
    """Parse the team slice JSON into a cleaned DataFrame."""
    data = json.loads(raw_json)

    # Torvik's JSON can be a list of lists or list of dicts depending on endpoint
    if isinstance(data, list) and len(data) > 0:
        if isinstance(data[0], dict):
            df = pd.DataFrame(data)
        else:
            # List of lists — first row is typically headers
            df = pd.DataFrame(data[1:], columns=data[0])
    else:
        df = pd.DataFrame(data)

    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")

    # Coerce numeric columns
    skip = {"team", "conf", "rec", "conference", "name"}
    for col in df.columns:
        if col not in skip:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    logger.info(f"Parsed {len(df)} teams from Torvik four factors JSON.")
    return df


def fetch_pre_tournament_snapshot(year: int, force_refresh: bool = False) -> pd.DataFrame:
    """
    Fetch the pre-tournament ratings snapshot from Torvik's time machine.

    This gives us the exact ratings as of Selection Sunday for a given year.
    Critical for backtesting — we need to score teams as they were BEFORE
    the tournament, not after.

    The time machine stores data as gzipped JSON at:
        /timemachine/team_results/YYYYMMDD_team_results.json.gz

    Args:
        year: Tournament year (2021-2025 for historical).
        force_refresh: If True, bypass cache.

    Returns:
        pd.DataFrame with pre-tournament team ratings.
    """
    # Selection Sunday approximate dates (day after) for recent years
    selection_dates = {
        2021: "20210315",
        2022: "20220314",
        2023: "20230313",
        2024: "20240318",
        2025: "20250317",
        2026: "20260316",  # Approximate — update when known
    }

    date_str = selection_dates.get(year)
    if date_str is None:
        raise ValueError(f"No Selection Sunday date configured for {year}")

    cache_file = _cache_path(f"torvik_snapshot_{year}_{date_str}.json")

    if not force_refresh and _cache_is_fresh(cache_file):
        raw = _load_cache(cache_file)
        return _parse_four_factors_json(raw)

    url = DATA_SOURCES["torvik"]["time_machine"].format(date=date_str)
    try:
        raw = _fetch_gzip(url)
        _save_cache(cache_file, raw)
        return _parse_four_factors_json(raw)
    except requests.RequestException as e:
        logger.error(f"Failed to fetch Torvik snapshot for {year}: {e}")
        if cache_file.exists():
            logger.warning("Using stale cache as fallback.")
            raw = _load_cache(cache_file)
            return _parse_four_factors_json(raw)
        raise


# =============================================================================
# Convenience: Merge All Torvik Data Into One DataFrame
# =============================================================================

def fetch_all_torvik_data(year: int = None, force_refresh: bool = False) -> pd.DataFrame:
    """
    Fetch and merge team results + four factors into one comprehensive DataFrame.

    This is the main function most other modules should call.

    Returns a DataFrame with columns covering:
        - Team identifiers (name, conference)
        - Adjusted efficiencies (AdjO, AdjD, net, barthag)
        - Four factors (off + def)
        - Tempo
        - SOS metrics
        - WAB
        - Seed (if applicable)

    Args:
        year: Season year. Defaults to CURRENT_YEAR.
        force_refresh: If True, bypass cache for all fetches.

    Returns:
        pd.DataFrame — one row per team, comprehensive stats.
    """
    if year is None:
        year = CURRENT_YEAR

    logger.info(f"Fetching all Torvik data for {year}...")

    # Pull both datasets
    results_df = fetch_team_results(year, force_refresh)
    factors_df = fetch_four_factors(year, force_refresh)

    # Find the team name column (Torvik uses different names sometimes)
    results_team_col = _find_team_column(results_df)
    factors_team_col = _find_team_column(factors_df)

    if results_team_col is None or factors_team_col is None:
        logger.warning("Could not identify team column for merge. Returning results only.")
        return results_df

    # Standardize team column name for merge
    results_df = results_df.rename(columns={results_team_col: "team"})
    factors_df = factors_df.rename(columns={factors_team_col: "team"})

    # Merge on team name — use outer join to keep all teams
    merged = pd.merge(
        results_df,
        factors_df,
        on="team",
        how="outer",
        suffixes=("", "_ff"),
    )

    # Drop duplicate columns from the merge (keep the first occurrence)
    dupe_cols = [c for c in merged.columns if c.endswith("_ff")]
    for col in dupe_cols:
        base_col = col.replace("_ff", "")
        if base_col in merged.columns:
            # Fill any NaNs in the base column from the duplicate
            merged[base_col] = merged[base_col].fillna(merged[col])
        else:
            merged = merged.rename(columns={col: base_col})
    merged = merged.drop(columns=[c for c in merged.columns if c.endswith("_ff")], errors="ignore")

    # Add computed columns
    if "adj_o" in merged.columns and "adj_d" in merged.columns:
        merged["net_efficiency"] = merged["adj_o"] - merged["adj_d"]

    logger.info(f"Merged Torvik data: {len(merged)} teams, {len(merged.columns)} columns.")
    return merged


def _find_team_column(df: pd.DataFrame) -> str | None:
    """Try to identify the team name column in a DataFrame."""
    candidates = ["team", "team_name", "name", "school"]
    for c in candidates:
        if c in df.columns:
            return c
    # Check for any column that looks like team names (strings, many unique)
    for c in df.columns:
        if df[c].dtype == object and df[c].nunique() > 100:
            return c
    return None


# =============================================================================
# Fetch Historical Data for Backtesting
# =============================================================================

def fetch_historical_torvik(years: list[int] = None, force_refresh: bool = False) -> dict[int, pd.DataFrame]:
    """
    Fetch Torvik data for multiple historical years.

    For backtest years, we use the time machine snapshot to get pre-tournament
    ratings. This ensures we're scoring teams as they were BEFORE results.

    Args:
        years: List of years to fetch. Defaults to HISTORICAL_YEARS from config.
        force_refresh: If True, bypass cache.

    Returns:
        Dict mapping year -> DataFrame of team stats.
    """
    if years is None:
        years = HISTORICAL_YEARS

    historical = {}
    for year in years:
        logger.info(f"Fetching historical Torvik data for {year}...")
        try:
            # Try time machine snapshot first (more accurate for backtesting)
            df = fetch_pre_tournament_snapshot(year, force_refresh)
            logger.info(f"  Got pre-tournament snapshot for {year}: {len(df)} teams")
        except Exception as e:
            logger.warning(f"  Time machine failed for {year}, falling back to season data: {e}")
            try:
                df = fetch_all_torvik_data(year, force_refresh)
            except Exception as e2:
                logger.error(f"  Could not fetch any data for {year}: {e2}")
                continue

        df["year"] = year
        historical[year] = df

    return historical


# =============================================================================
# Diagnostic / Exploration Helpers
# =============================================================================

def print_available_columns(year: int = None):
    """Print all available columns from Torvik data — useful for exploration."""
    df = fetch_all_torvik_data(year)
    print(f"\n📊 Torvik Data Columns ({len(df.columns)} total):\n")
    for i, col in enumerate(sorted(df.columns), 1):
        sample = df[col].dropna().iloc[0] if not df[col].dropna().empty else "N/A"
        dtype = df[col].dtype
        print(f"  {i:3d}. {col:<30s} ({dtype}) — e.g., {sample}")


def get_team(team_name: str, year: int = None) -> pd.Series | None:
    """Quick lookup for a single team's stats."""
    df = fetch_all_torvik_data(year)
    team_col = _find_team_column(df)
    if team_col is None:
        return None

    # Case-insensitive partial match
    mask = df[team_col].str.lower().str.contains(team_name.lower(), na=False)
    matches = df[mask]

    if matches.empty:
        logger.warning(f"No team found matching '{team_name}'")
        return None
    if len(matches) > 1:
        logger.info(f"Multiple matches for '{team_name}': {matches[team_col].tolist()}")

    return matches.iloc[0]


# =============================================================================
# CLI Test
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    print("🏀 BracketIQ — Torvik Scraper Test\n")

    # Test: fetch current year data
    df = fetch_all_torvik_data()
    print(f"✅ Fetched {len(df)} teams for {CURRENT_YEAR}")
    print(f"   Columns: {list(df.columns[:10])}... ({len(df.columns)} total)")
    print(f"\n   Top 5 by net efficiency:")
    if "net_efficiency" in df.columns:
        top = df.nlargest(5, "net_efficiency")[["team", "adj_o", "adj_d", "net_efficiency"]]
        print(top.to_string(index=False))

    # Test: single team lookup
    print("\n   Looking up 'Duke':")
    duke = get_team("Duke")
    if duke is not None:
        print(f"   {duke.get('team', 'N/A')} — AdjO: {duke.get('adj_o', 'N/A')}, AdjD: {duke.get('adj_d', 'N/A')}")

    print("\n✅ Torvik scraper test complete.")