# mobilelab

A Python toolkit for processing and analyzing mobile laboratory atmospheric measurement data.

## Overview

`mobilelab` provides preprocessing utilities for cleaning, time-syncing, and merging data from multi-instrument mobile sensing campaigns. The general workflow is:

1. **Clean** raw instrument files with `clean.py`
2. **Determine time offsets** visually with `sync_offsets.ipynb`
3. **Apply offsets** by re-running `clean.py` with the JSON outputs from the notebook
4. **Merge** all instruments to a common time grid with `merge_daily.py`

## Setup

```bash
conda env create -f environment.yml
conda activate mobilelab
```

## Usage

### 1. `preprocess/clean.py` — Clean raw instrument files

Normalizes raw files to a common CSV format with a `TIMESTAMP` index. Handles comma-delimited and whitespace-delimited files automatically.

**Single file:**
```bash
python preprocess/clean.py <file>
```

**Batch directory — interactive (prompts for time shift per file):**
```bash
python preprocess/clean.py <raw_dir/>
```

Type `a` at any time shift prompt to apply `0s` to all remaining files.

**Batch directory — JSON mode (no prompts, offsets from notebook):**
```bash
python preprocess/clean.py <dir/> -o offsets.json [-r rejected.json]
```

- `-o` — JSON dict mapping filename → seconds (output of `sync_offsets.ipynb`)
- `-r` — JSON list of filenames to skip entirely (output of `sync_offsets.ipynb`)

Files not present in the offsets JSON receive a `0s` shift automatically.

Output: one `*_clean.csv` per input file (suffix configurable at runtime), with a `TIMESTAMP` index formatted as `YYYY-MM-DD HH:MM:SS.ffffff`.

---

### 2. `preprocess/sync_offsets.ipynb` — Determine time offsets visually

Cross-correlates a test instrument's CH4 signal against a reference instrument to find per-file time offsets. Takes cleaned CSVs as input.

Open in JupyterLab:
```bash
jupyter lab preprocess/sync_offsets.ipynb
```

**Config cell** (the only cell you need to edit):

| Variable | Description |
|---|---|
| `REF_DIR` | Folder of `*_clean.csv` files for the reference instrument |
| `REF_COL` | Column name to cross-correlate on (e.g. `CH4_dry_sync`) |
| `TEST_DIR` | Folder of `*_clean.csv` files for the instrument being synced |
| `TEST_COL` | Column name to cross-correlate on (e.g. `CH4`) |
| `TEST_NAME` | Label shown in plots |
| `OUTPUT_DIR` | Where to save the JSON outputs |
| `OUTPUT_STEM` | Base name for outputs — e.g. `aeris460` → `aeris460_timeshift.json` |
| `REF_RAW_EXT` | Raw file extension of the reference instrument (e.g. `.dat`) |
| `TEST_RAW_EXT` | Raw file extension of the test instrument (e.g. `.txt`) |
| `RESAMPLE_S` | Resample interval in seconds (default: `1`) |
| `MAX_LAG_S` | Maximum lag to search in seconds (default: `120`) |

Run all cells top to bottom. Step through files with the interactive plot — use the lag slider to align peaks, then **Commit & Next** to save or **Mark Bad & Next** to reject. The final cell writes:

- `<OUTPUT_STEM>_timeshift.json` — filename → offset in seconds
- `<OUTPUT_STEM>_rejected.json` — list of bad/unusable files

These JSONs are passed directly to `clean.py -o / -r`.

---

### 3. `preprocess/merge_daily.py` — Merge instruments to daily files

Loads cleaned CSVs from multiple instrument directories, resamples to a common time grid, and joins them into one CSV per calendar day.

```bash
python preprocess/merge_daily.py <out_dir/> [--freq <seconds>]
```

Edit the `SOURCES` list at the top of the script to point to your instrument directories and set column prefixes before running.

Output: one `YYYYMMDD.csv` per day in `<out_dir>/`, with all instrument columns prefixed by instrument name (e.g. `CH4_Picarro`, `CH4_Aeris460`).
