# mobilelabs

A Python toolkit for processing and analyzing mobile laboratory atmospheric measurement data.

## Overview

`mobilelab` provides I/O utilities and analysis algorithms for working with data collected from mobile atmospheric sensing platforms. It is designed for use in HPC environments processing large multi-instrument datasets.

## Structure

```
mobilelab/
├── __init__.py
├── algorithms/
│   └── plume.py        # Plume detection and analysis
└── io/
    ├── merge.py        # Multi-instrument data merging
    └── parse.py        # Instrument data parsing
```

## Installation

```bash
git clone https://github.com/<your-username>/mobilelab.git
cd mobilelab
pip install -e .
```

> Requires Python 3.9+

## Usage

```python
import mobilelab

# Parse raw instrument data
from mobilelab.io import parse, merge

# Run plume detection algorithms
from mobilelab.algorithms import plume
```

## Modules

### `mobilelab.io`
- **`parse`** — Reads and standardizes raw instrument data files
- **`merge`** — Aligns and merges data streams from multiple instruments

### `mobilelab.algorithms`
- **`plume`** — Plume identification and characterization routines

