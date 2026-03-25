"""
clean.py
----------------
Interactive Picarro CSV cleaner.

Usage:
    python clean.py <input_file.dat>

The script will prompt you for:
  1. Number of header lines to skip
  2. Which data columns to keep
  3. How to build the timestamp index

Output: a cleaned CSV with a single TIMESTAMP index and your chosen columns.

Harrison LeTourneau, U of Utah, 2026
"""

import sys
from pathlib import Path

import pandas as pd


# ── Helpers ───────────────────────────────────────────────────────────────────

def prompt(msg: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default is not None else ""
    while True:
        val = input(f"{msg}{suffix}: ").strip()
        if val == "" and default is not None:
            return default
        if val != "":
            return val
        print("  Please enter a value.")


def prompt_int(msg: str, default: int | None = None) -> int:
    while True:
        raw = prompt(msg, str(default) if default is not None else None)
        try:
            return int(raw)
        except ValueError:
            print(f"  '{raw}' is not a valid integer. Try again.")


def prompt_choice(msg: str, choices: list[str], default: str | None = None) -> str:
    choices_lower = [c.lower() for c in choices]
    while True:
        raw = prompt(msg, default).lower()
        if raw in choices_lower:
            return raw
        print(f"  Invalid choice. Options: {choices}")


def section(title: str):
    width = 60
    print("\n" + "─" * width)
    print(f"  {title}")
    print("─" * width)


# ── Step 1: Read with user-specified header skip ──────────────────────────────

def read_with_skip(filepath: Path, skiprows: int) -> pd.DataFrame:
    df = pd.read_csv(
        filepath,
        sep=r"\s+",
        engine="python",
        skiprows=skiprows,
        na_values=["nan", "NaN", "NA", "", "N/A"],
    )
    df.columns = [c.strip() for c in df.columns]
    return df


# ── Step 2: Column selection ──────────────────────────────────────────────────

def select_columns(df: pd.DataFrame) -> list[str]:
    # Exclude obvious timestamp-related columns from the data menu
    ts_keywords = {"date", "time", "epoch", "julian", "frac", "timestamp"}
    data_cols = [
        c for c in df.columns
        if not any(kw in c.lower() for kw in ts_keywords)
    ]

    print("\n  Available data columns:\n")
    for i, col in enumerate(data_cols, 1):
        # Show a quick sample value for context
        sample = df[col].dropna().iloc[0] if df[col].dropna().shape[0] > 0 else "N/A"
        print(f"    [{i:>2}]  {col:<35}  (e.g. {sample})")

    print()
    print("  Enter column numbers separated by spaces (e.g. 1 3 5),")
    print("  or press Enter to keep ALL of them.")

    while True:
        raw = input("  Your selection: ").strip()
        if raw == "":
            return data_cols
        try:
            indices = [int(x) for x in raw.split()]
            if all(1 <= i <= len(data_cols) for i in indices):
                selected = [data_cols[i - 1] for i in indices]
                print(f"\n  Keeping: {selected}")
                return selected
            else:
                print(f"  Numbers must be between 1 and {len(data_cols)}. Try again.")
        except ValueError:
            print("  Please enter integers only.")


# ── Step 3: Timestamp building ────────────────────────────────────────────────

def find_cols(df: pd.DataFrame, keyword: str) -> list[str]:
    """Return column names that contain a keyword (case-insensitive)."""
    return [c for c in df.columns if keyword.lower() in c.lower()]


def build_timestamp(df: pd.DataFrame) -> pd.Series:
    section("STEP 3 of 3 — Timestamp / Index")

    # Show what timestamp-ish columns exist
    ts_keywords = ["date", "time", "epoch", "julian", "frac"]
    ts_cols = [
        c for c in df.columns
        if any(kw in c.lower() for kw in ts_keywords)
    ]
    print("\n  Detected timestamp-related columns:")
    for c in ts_cols:
        sample = df[c].iloc[0] if len(df) > 0 else "N/A"
        print(f"    {c:<35}  (e.g. {sample})")

    print()
    print("  How would you like to build the timestamp index?")
    print("    [1]  epoch   — single column of Unix seconds (e.g. EPOCH_TIME)")
    print("    [2]  combine — combine a DATE column + a TIME column")
    method = prompt_choice("\n  Choice", ["1", "2", "epoch", "combine"])

    if method in ("1", "epoch"):
        return _build_epoch(df, ts_cols)
    else:
        return _build_combine(df, ts_cols)


def _build_epoch(df: pd.DataFrame, ts_cols: list[str]) -> pd.Series:
    epoch_candidates = [c for c in ts_cols if "epoch" in c.lower()]
    if epoch_candidates:
        default_col = epoch_candidates[0]
    else:
        default_col = ts_cols[0] if ts_cols else None

    col = prompt(
        "\n  Enter the epoch column name",
        default_col,
    )
    if col not in df.columns:
        raise KeyError(f"Column '{col}' not found in file.")

    print(f"  Parsing '{col}' as Unix seconds (UTC) → tz-naive datetime.")
    ts = pd.to_datetime(df[col].astype(float), unit="s", utc=True).dt.tz_localize(None)
    return ts


def _build_combine(df: pd.DataFrame, ts_cols: list[str]) -> pd.Series:
    date_candidates = [c for c in ts_cols if "date" in c.lower()]
    time_candidates = [c for c in ts_cols if "time" in c.lower() and "epoch" not in c.lower()]

    date_col = prompt(
        "\n  Date column name",
        date_candidates[0] if date_candidates else None,
    )
    time_col = prompt(
        "  Time column name",
        time_candidates[0] if time_candidates else None,
    )

    for col in (date_col, time_col):
        if col not in df.columns:
            raise KeyError(f"Column '{col}' not found in file.")

    # Show samples so the user can figure out the right format
    print(f"\n  Sample DATE values : {df[date_col].iloc[:3].tolist()}")
    print(f"  Sample TIME values : {df[time_col].iloc[:3].tolist()}")
    print()
    print("  Enter the combined datetime format string.")
    print("  Examples:")
    print("    %Y-%m-%d %H:%M:%S       →  2026-02-10 21:00:02")
    print("    %Y-%m-%d %H:%M:%S.%f    →  2026-02-10 21:00:02.123")
    print("    %m/%d/%Y %I:%M:%S %p    →  02/10/2026 09:00:02 PM")
    print("  (The date and time values will be joined with a single space.)")

    fmt = prompt(
        "  Format string",
        "%Y-%m-%d %H:%M:%S",
    )

    combined = (
        df[date_col].astype(str).str.strip()
        + " "
        + df[time_col].astype(str).str.strip()
    )

    ts = pd.to_datetime(combined, format=fmt, errors="coerce")

    n_bad = ts.isna().sum()
    if n_bad > 0:
        print(f"\n  [warn] {n_bad} rows failed to parse and will be dropped.")

    return ts


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python clean.py <input_file.dat>")
        sys.exit(1)

    filepath = Path(sys.argv[1])
    if not filepath.exists():
        print(f"Error: file not found — {filepath}")
        sys.exit(1)

    print(f"\n{'═' * 60}")
    print(f"  Picarro Cleaner")
    print(f"  File: {filepath.name}")
    print(f"{'═' * 60}")

    # ── Step 1: Header skip ───────────────────────────────────────────────────
    section("STEP 1 of 3 — Header Lines")

    # Peek at first 10 lines so the user can see the structure
    print("\n  First 10 lines of the file:\n")
    max_content = 72  # chars of line content before truncating
    with open(filepath) as f:
        for i, line in enumerate(f):
            if i >= 10:
                break
            content = line.rstrip("\n")
            if len(content) > max_content:
                content = content[:max_content] + " ..."
            print(f"  {i:>3}  {content}")
    print()

    print("\n  How many lines should be skipped before the column-name row?")
    print("  (e.g. if row 0 is already the header, enter 0)")
    skiprows = prompt_int("  Lines to skip", default=0)

    # Try to read with that skip value
    try:
        df = read_with_skip(filepath, skiprows)
    except Exception as e:
        print(f"\n  Error reading file: {e}")
        sys.exit(1)

    print(f"\n  Read {len(df):,} rows, {len(df.columns)} columns.")
    print(f"  Column names detected: {df.columns.tolist()}")

    # ── Step 2: Column selection ──────────────────────────────────────────────
    section("STEP 2 of 3 — Data Columns to Keep")
    keep_cols = select_columns(df)

    # ── Step 3: Timestamp ─────────────────────────────────────────────────────
    ts = build_timestamp(df)

    # ── Assemble clean DataFrame ──────────────────────────────────────────────
    df_clean = df[keep_cols].copy()

    for col in df_clean.columns:
        df_clean[col] = pd.to_numeric(df_clean[col], errors="coerce")

    df_clean.insert(0, "TIMESTAMP", ts.values)
    df_clean.set_index("TIMESTAMP", inplace=True)
    df_clean.index.name = "TIMESTAMP"

    # Drop unparseable timestamps and duplicates
    df_clean = df_clean[~df_clean.index.isna()]
    df_clean = df_clean[~df_clean.index.duplicated(keep="first")]
    df_clean.sort_index(inplace=True)

    print(f"\n  ✓  Clean DataFrame ready: {len(df_clean):,} rows × {len(df_clean.columns)} columns")
    print(f"     Columns: {df_clean.columns.tolist()}")
    print(f"     Time range: {df_clean.index[0]}  →  {df_clean.index[-1]}")

    # ── Output ────────────────────────────────────────────────────────────────
    section("OUTPUT")
    default_out = filepath.stem + "_clean.csv"
    out_path = Path(prompt("  Output file path", default_out))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df_clean.to_csv(out_path)
    print(f"\n  ✓  Saved → {out_path}\n")


if __name__ == "__main__":
    main()