"""
clean_picarro.py
----------------
Clean and standardize raw Picarro G2301/G4302 CSV files.

Usage
-----
    python clean_picarro.py --input data/raw/picarro/SLV_20260210.dat
    python clean_picarro.py --input data/raw/picarro/SLV_20260210.dat \\
        --timestamp epoch \\
        --keep CH4_sync CH4_dry_sync CO2_sync H2O_sync \\
        --output output/picarro_clean/20260210_picarro.csv

Timestamp methods
-----------------
    datetime  : (default) combine DATE + TIME columns → "2026-02-10 21:00:02"
    epoch     : use EPOCH_TIME (Unix seconds UTC)
    julian    : use JULIAN_DAYS column
    frac_days : use FRAC_DAYS_SINCE_JAN1

Column selection
----------------
    Default keep set (--keep not specified):
        CO_sync, CO2_sync, CO2_dry_sync, CH4_sync, CH4_dry_sync, H2O_sync

    Pass any subset on the CLI, e.g.:
        --keep CH4_sync CH4_dry_sync H2O_sync

Harrison LeTourneau, U of Utah, 2026
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd


# ── Column name standardization map ──────────────────────────────────────────
# Maps raw Picarro column names → standardized output names.
# Add entries here if your instrument variant uses different raw names.

STANDARD_NAMES = {
    "CO_sync":      "CO (ppm)",
    "CO2_sync":     "CO2 (ppm)",
    "CO2_dry_sync": "CO2_dry (ppm)",
    "CH4_sync":     "CH4 (ppm)",
    "CH4_dry_sync": "CH4_dry (ppm)",
    "H2O_sync":     "H2O (ppm)",
    # Cavity diagnostics — kept if user requests them explicitly
    "CavityPressure": "CavityPressure (Torr)",
    "CavityTemp":     "CavityTemp (C)",
    "AmbientPressure":"AmbientPressure (Torr)",
}

DEFAULT_KEEP = [
    "CO_sync",
    "CO2_sync",
    "CO2_dry_sync",
    "CH4_sync",
    "CH4_dry_sync",
    "H2O_sync",
]

TIMESTAMP_METHODS = ("datetime", "epoch", "julian", "frac_days")


# ── Core reader ───────────────────────────────────────────────────────────────

def read_picarro(filepath: str | Path) -> pd.DataFrame:
    """
    Read a raw Picarro whitespace-delimited data file into a DataFrame.
    Handles the wide whitespace padding Picarro uses between columns.

    Returns a raw DataFrame with original column names intact.
    Numeric columns that Picarro writes in scientific notation are cast to float.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Picarro file not found: {path}")

    df = pd.read_csv(
        path,
        sep=r"\s+",       # any whitespace run as delimiter
        engine="python",
        na_values=["nan", "NaN", "NA", "", "N/A"],
    )

    # Strip any stray whitespace from column names
    df.columns = [c.strip() for c in df.columns]

    print(f"[read_picarro] {path.name}: {len(df):,} rows, {len(df.columns)} columns")
    return df


# ── Timestamp builders ────────────────────────────────────────────────────────

def build_timestamp_datetime(df: pd.DataFrame) -> pd.Series:
    """
    Combine DATE and TIME columns.
    Expected formats: DATE='2026-02-03', TIME='21:00:02.000'
    """
    if "DATE" not in df.columns or "TIME" not in df.columns:
        raise KeyError("Method 'datetime' requires DATE and TIME columns in the file.")

    combined = df["DATE"].astype(str).str.strip() + " " + df["TIME"].astype(str).str.strip()
    ts = pd.to_datetime(combined, format="%Y-%m-%d %H:%M:%S.%f", errors="coerce")

    # Fallback: try without fractional seconds
    mask = ts.isna()
    if mask.any():
        ts[mask] = pd.to_datetime(combined[mask], format="%Y-%m-%d %H:%M:%S", errors="coerce")

    n_bad = ts.isna().sum()
    if n_bad:
        print(f"  [warn] {n_bad} timestamp rows could not be parsed and will be NaT.")
    return ts


def build_timestamp_epoch(df: pd.DataFrame) -> pd.Series:
    """
    Convert EPOCH_TIME (Unix seconds, UTC) to a tz-naive UTC datetime.
    """
    if "EPOCH_TIME" not in df.columns:
        raise KeyError("Method 'epoch' requires EPOCH_TIME column in the file.")
    return pd.to_datetime(df["EPOCH_TIME"].astype(float), unit="s", utc=True).dt.tz_localize(None)


def build_timestamp_julian(df: pd.DataFrame) -> pd.Series:
    """
    Convert JULIAN_DAYS to datetime.
    Picarro JULIAN_DAYS is fractional Julian Day Number (JDN).
    J2000.0 epoch = 2000-01-01 12:00:00 UTC = JD 2451545.0
    """
    if "JULIAN_DAYS" not in df.columns:
        raise KeyError("Method 'julian' requires JULIAN_DAYS column in the file.")
    j2000_jd = 2451545.0
    j2000_dt = pd.Timestamp("2000-01-01 12:00:00")
    delta_days = df["JULIAN_DAYS"].astype(float) - j2000_jd
    return j2000_dt + pd.to_timedelta(delta_days, unit="D")


def build_timestamp_frac_days(df: pd.DataFrame) -> pd.Series:
    """
    Convert FRAC_DAYS_SINCE_JAN1 to datetime using the year inferred from DATE.
    Day 1.0 = Jan 1 00:00:00 of that year.
    """
    if "FRAC_DAYS_SINCE_JAN1" not in df.columns:
        raise KeyError("Method 'frac_days' requires FRAC_DAYS_SINCE_JAN1 column.")
    if "DATE" not in df.columns:
        raise KeyError("Method 'frac_days' also requires DATE to infer the year.")

    year = pd.to_datetime(df["DATE"].iloc[0].strip()).year
    jan1 = pd.Timestamp(f"{year}-01-01")
    # Picarro frac_days: day 1.0 = Jan 1 00:00:00, so offset = (frac - 1) days
    delta = df["FRAC_DAYS_SINCE_JAN1"].astype(float) - 1.0
    return jan1 + pd.to_timedelta(delta, unit="D")


TIMESTAMP_BUILDERS = {
    "datetime":  build_timestamp_datetime,
    "epoch":     build_timestamp_epoch,
    "julian":    build_timestamp_julian,
    "frac_days": build_timestamp_frac_days,
}


# ── Main cleaning function ────────────────────────────────────────────────────

def clean_picarro(
    filepath: str | Path,
    timestamp_method: str = "datetime",
    keep_columns: list[str] | None = None,
    output_path: str | Path | None = None,
) -> pd.DataFrame:
    """
    Load, clean, and standardize a Picarro data file.

    Parameters
    ----------
    filepath : str or Path
        Path to the raw Picarro .dat / .csv file.

    timestamp_method : str
        One of: 'datetime', 'epoch', 'julian', 'frac_days'.
        See module docstring for details.

    keep_columns : list of str, optional
        Raw Picarro column names to retain (before renaming).
        Defaults to DEFAULT_KEEP (the six sync gas columns).

    output_path : str or Path, optional
        If provided, write the cleaned DataFrame to this CSV path.

    Returns
    -------
    pd.DataFrame
        Cleaned DataFrame with TIMESTAMP index and standardized column names.
    """
    if timestamp_method not in TIMESTAMP_METHODS:
        raise ValueError(
            f"Unknown timestamp method '{timestamp_method}'. "
            f"Choose from: {TIMESTAMP_METHODS}"
        )

    if keep_columns is None:
        keep_columns = DEFAULT_KEEP

    # ── 1. Read raw file
    df = read_picarro(filepath)

    # ── 2. Validate requested keep columns exist
    missing = [c for c in keep_columns if c not in df.columns]
    if missing:
        available = [c for c in df.columns if c not in ("DATE", "TIME")]
        print(f"  [warn] Requested columns not found in file: {missing}")
        print(f"  Available columns: {available}")
        keep_columns = [c for c in keep_columns if c in df.columns]
        if not keep_columns:
            raise ValueError("No valid data columns remain after filtering.")

    # ── 3. Build timestamp
    print(f"  Building timestamp using method: '{timestamp_method}'")
    ts = TIMESTAMP_BUILDERS[timestamp_method](df)

    # ── 4. Subset to desired columns only
    df_clean = df[keep_columns].copy()

    # ── 5. Cast all data columns to float (Picarro writes scientific notation)
    for col in df_clean.columns:
        df_clean[col] = pd.to_numeric(df_clean[col], errors="coerce")

    # ── 6. Apply standard column names (only for columns in the map)
    rename = {c: STANDARD_NAMES[c] for c in df_clean.columns if c in STANDARD_NAMES}
    df_clean.rename(columns=rename, inplace=True)

    # ── 7. Set TIMESTAMP index
    df_clean.insert(0, "TIMESTAMP", ts.values)
    df_clean.set_index("TIMESTAMP", inplace=True)
    df_clean.index.name = "TIMESTAMP"

    # ── 8. Drop NaT index rows and duplicates
    df_clean = df_clean[~df_clean.index.isna()]
    df_clean = df_clean[~df_clean.index.duplicated(keep="first")]
    df_clean.sort_index(inplace=True)

    print(
        f"  Cleaned: {len(df_clean):,} records | "
        f"columns: {df_clean.columns.tolist()}"
    )

    # ── 9. Optionally write output
    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        df_clean.to_csv(out)
        print(f"  Saved → {out}")

    return df_clean


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args():
    parser = argparse.ArgumentParser(
        description="Clean and standardize a raw Picarro data file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Path to raw Picarro .dat or .csv file.",
    )
    parser.add_argument(
        "--timestamp", "-t",
        default="datetime",
        choices=TIMESTAMP_METHODS,
        help=(
            "Method for building the TIMESTAMP index. "
            "datetime=DATE+TIME (default), epoch=EPOCH_TIME, "
            "julian=JULIAN_DAYS, frac_days=FRAC_DAYS_SINCE_JAN1."
        ),
    )
    parser.add_argument(
        "--keep", "-k",
        nargs="+",
        default=None,
        metavar="COL",
        help=(
            "Raw Picarro column names to keep. "
            f"Defaults to: {DEFAULT_KEEP}. "
            "Example: --keep CH4_sync CH4_dry_sync H2O_sync"
        ),
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help=(
            "Output CSV path. If omitted, prints summary only "
            "(useful for inspecting what columns are available)."
        ),
    )
    parser.add_argument(
        "--list-columns",
        action="store_true",
        help="Print all column names found in the file and exit.",
    )
    return parser.parse_args()


def main():
    args = _parse_args()

    if args.list_columns:
        df_raw = read_picarro(args.input)
        print("\nAll columns in file:")
        for col in df_raw.columns:
            print(f"  {col}")
        sys.exit(0)

    clean_picarro(
        filepath=args.input,
        timestamp_method=args.timestamp,
        keep_columns=args.keep,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()