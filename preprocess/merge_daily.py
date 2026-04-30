"""
merge_daily.py

Merge all instrument data into one GPS-aligned CSV per calendar day.

All instruments are binned to a common 1-second resolution, 
then joined on the shared timestamp index so every row has readings
from all instruments present at that second.

Output directory: <out_dir>/YYYY-MM-DD.csv

Usage:
    python merge_daily.py <out_dir/> [--freq <seconds>]

    --freq  resample interval in seconds (default: 1)
"""

import sys
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Source definitions
#   dir         : where to glob *_clean.csv  (or timeshift copies)
#   prefix      : instrument tag added to every column
#   col_rename  : optional per-column overrides BEFORE prefixing
#                 (use to sanitise names like "C2/C1")
# ---------------------------------------------------------------------------
_TEMP = Path(__file__).parent.parent / "temp"

SOURCES = [
    {
        "dir":       _TEMP / "WYO_picarro_cleaned",
        "prefix":    "Picarro",
        "col_rename": {},
    },
    {
        "dir":       _TEMP / "WYO_aerisultra460_timeshift",
        "prefix":    "Aeris460",
        "col_rename": {"C2/C1": "C2C1"},
    },
    {
        "dir":       _TEMP / "LANL_aerisultra321_timeshift",
        "prefix":    "Aeris321",
        "col_rename": {},
    },
    {
        "dir":       _TEMP / "LANL_aerispico017_timeshift",
        "prefix":    "Pico",
        "col_rename": {},
    },
    {
        "dir":       _TEMP / "WYO_sprinter_cleaned",
        "prefix":    "Sprinter",
        "col_rename": {},
    },
]


def load_source(src: dict, freq: str) -> pd.DataFrame:
    """Load all CSVs for one instrument, rename/prefix columns, resample to grid."""
    directory  = src["dir"]
    prefix     = src["prefix"]
    col_rename = src["col_rename"]

    files = sorted(directory.glob("*_clean.csv"))
    if not files:
        print(f"  [warn] No files found in {directory}")
        return pd.DataFrame()

    parts = []
    for f in files:
        df = pd.read_csv(f, index_col="TIMESTAMP", parse_dates=True)
        parts.append(df)

    combined = pd.concat(parts)
    combined = combined[~combined.index.duplicated(keep="first")]
    combined.sort_index(inplace=True)

    # sanitise then prefix columns
    combined.rename(columns=col_rename, inplace=True)
    combined.columns = [f"{col}_{prefix}" for col in combined.columns]

    # Resample to common grid — mean within each bin
    resampled = combined.resample(freq).mean()

    print(f"  {prefix:<12}  {len(combined):>8,} raw rows  ->  "
          f"{resampled.dropna(how='all').shape[0]:>7,} {freq} bins")
    return resampled


def merge_daily(out_dir: Path, freq_s: int = 1):
    out_dir.mkdir(parents=True, exist_ok=True)
    freq = f"{freq_s}s"

    print(f"\n{'═' * 60}")
    print(f"  Loading and resampling to {freq} grid...")
    print(f"{'═' * 60}")

    frames = []
    for src in SOURCES:
        df = load_source(src, freq)
        if not df.empty:
            frames.append(df)

    if not frames:
        print("Error: no data loaded.")
        sys.exit(1)

    # Join all on the common time index (axis=1 = column-wise join)
    combined = pd.concat(frames, axis=1, sort=True)
    combined.index.name = "TIMESTAMP"

    # Drop rows where every column is NaN (empty bins)
    combined.dropna(how="all", inplace=True)
    combined.sort_index(inplace=True)

    # Group by Utah local date (MST = UTC-7, MDT = UTC-6)
    # Localize UTC index, convert to Mountain, extract local date for grouping
    combined.index = combined.index.tz_localize("UTC")
    local_dates = combined.index.tz_convert("America/Denver").normalize()
    dates = local_dates.unique()

    print(f"\n  Aligned rows : {len(combined):,}")
    print(f"  Days found   : {len(dates)} (Utah local time)")
    print(f"  Output       : {out_dir}")
    print(f"{'═' * 60}\n")

    n_written = 0
    for date in sorted(dates):
        date_str = date.strftime("%Y%m%d")
        day_df = combined[local_dates == date].copy()

        # Write index back as UTC strings (no tz suffix) for dashboard compatibility
        day_df.index = day_df.index.tz_convert("UTC").strftime("%Y-%m-%d %H:%M:%S")

        # Drop columns entirely NaN for this day
        day_df = day_df.dropna(axis=1, how="all")

        out_path = out_dir / f"{date_str}.csv"
        day_df.to_csv(out_path)
        n_rows = len(day_df)
        n_cols = len(day_df.columns)
        print(f"  {date_str}  {n_rows:>7,} rows  {n_cols:>3} cols  ->  {out_path.name}")
        n_written += 1

    print(f"\n  Done — {n_written} daily files written to {out_dir}\n")


def main():
    args = sys.argv[1:]

    freq_s = 1
    if "--freq" in args:
        i = args.index("--freq")
        if i + 1 >= len(args):
            print("Error: --freq requires a value (seconds)")
            sys.exit(1)
        freq_s = int(args[i + 1])
        args = [a for j, a in enumerate(args) if j not in (i, i + 1)]

    if len(args) != 1:
        print("Usage: python merge_daily.py <out_dir/> [--freq <seconds>]")
        sys.exit(1)

    merge_daily(Path(args[0]), freq_s)


if __name__ == "__main__":
    main()
