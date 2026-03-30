"""
sync.py
----------------
Generate a static HTML page for manually aligning Aeris timestamps
to a Picarro reference using CH4 overlap.

Usage:
    python sync.py \\
        --picarro  cleaned/picarro_clean.csv \\
        --aeris    cleaned/aeris/          \\
        --out      ~/public_html/sync/     \\
        --pic-col  "CH4_dry (ppm)"         \\
        --aer-col  "CH4 (ppm)"

Arguments:
    --picarro   Path to the cleaned Picarro CSV (single file, TIMESTAMP index).
    --aeris     Path to a cleaned Aeris CSV, OR a directory of Aeris CSVs.
    --out       Output directory. index.html will be written there.
    --pic-col   Column name for CH4 in the Picarro file.   [CH4_dry (ppm)]
    --aer-col   Column name for CH4 in the Aeris file(s).  [CH4 (ppm)]

The script writes:
    <out>/index.html   — self-contained sync tool (open in browser)

No server required. Open the URL in your browser, drag sliders,
then click "Download offsets.json". Pass that file to clean.py
via --offsets to apply the shifts.

Harrison LeTourneau, U of Utah, 2026
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_csv(path: Path, ch4_col: str) -> tuple[list[str], list[float]]:
    df = pd.read_csv(path, index_col="TIMESTAMP")
    if ch4_col not in df.columns:
        raise KeyError(
            f"Column '{ch4_col}' not found in {path.name}.\n"
            f"Available: {df.columns.tolist()}"
        )
    df.index = pd.to_datetime(df.index, errors="coerce")
    df = df[~df.index.isna()].sort_index()
    ts  = df.index.strftime("%Y-%m-%dT%H:%M:%S.%f").tolist()
    ch4 = pd.to_numeric(df[ch4_col], errors="coerce").fillna(0.0).tolist()
    return ts, ch4


def collect_aeris_files(aeris_path: Path) -> list[Path]:
    if aeris_path.is_dir():
        files = sorted(
            p for p in aeris_path.iterdir()
            if p.is_file() and p.suffix.lower() == ".csv"
            and not p.name.startswith(".")
        )
        if not files:
            raise FileNotFoundError(f"No CSV files found in {aeris_path}")
        return files
    elif aeris_path.is_file():
        return [aeris_path]
    else:
        raise FileNotFoundError(f"Aeris path not found: {aeris_path}")


# ── HTML builder ──────────────────────────────────────────────────────────────
# HTML and JS are plain strings — no Python .format() so no brace escaping.

CSS = """\
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Syne:wght@400;600;700&display=swap');

:root {
    --bg:        #0b0e14;
    --panel:     #121826;
    --panel-alt: #0f1422;
    --border:    #1f2937;
    --text:      #e5e7eb;
    --muted:     #9ca3af;
    --accent:    #60a5fa;
    --green:     #CFFF04;
    --danger:    #fb7185;
    --nav-bg:    #020617;
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: 'Syne', sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    display: flex;
    flex-direction: column;
}

nav {
    background: var(--nav-bg);
    border-bottom: 1px solid var(--border);
    height: 56px;
    display: flex;
    align-items: center;
    padding: 0 20px;
    gap: 24px;
    position: sticky;
    top: 0;
    z-index: 100;
}

.nav-brand {
    display: flex;
    align-items: center;
    gap: 10px;
    text-decoration: none;
    color: var(--text);
    font-size: 1rem;
    font-weight: 600;
}

.nav-logo { height: 26px; }

.nav-links {
    display: flex;
    gap: 4px;
    margin-left: auto;
    list-style: none;
}

.nav-links a {
    color: var(--muted);
    text-decoration: none;
    font-size: 0.875rem;
    padding: 6px 12px;
    border-radius: 4px;
    transition: color 0.15s, background 0.15s;
}

.nav-links a:hover { color: var(--text); background: var(--panel-alt); }

.container {
    flex: 1;
    display: flex;
    flex-direction: column;
    padding: 16px 20px;
    gap: 12px;
    max-width: 1600px;
    width: 100%;
    margin: 0 auto;
}

.file-bar {
    display: flex;
    align-items: center;
    gap: 12px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 10px 16px;
    flex-wrap: wrap;
}

.file-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.8rem;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
}

.file-name {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.9rem;
    color: var(--accent);
    font-weight: 500;
}

.file-counter {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.8rem;
    color: var(--muted);
}

.progress-row {
    display: flex;
    gap: 6px;
    align-items: center;
    flex-wrap: wrap;
    margin-left: auto;
}

.dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--border);
    border: 1px solid var(--border);
    transition: background 0.2s;
    cursor: default;
}

.dot.done    { background: var(--accent); border-color: var(--accent); }
.dot.current { background: var(--green);  border-color: var(--green);  box-shadow: 0 0 6px var(--green); }
.dot.skipped { background: transparent;   border-color: var(--muted); }

.plot-panel {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 8px;
    flex: 1;
    min-height: 0;
}

#chart {
    width: 100%;
    height: calc(100vh - 290px);
    min-height: 320px;
}

.controls {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 14px 20px;
    display: flex;
    align-items: center;
    gap: 24px;
    flex-wrap: wrap;
}

.control-group {
    display: flex;
    flex-direction: column;
    gap: 4px;
}

.control-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.07em;
}

.offset-display {
    font-family: 'JetBrains Mono', monospace;
    font-size: 1.6rem;
    font-weight: 600;
    color: var(--green);
    min-width: 110px;
    line-height: 1;
}

.offset-display.negative { color: var(--danger); }

.slider-wrap {
    display: flex;
    flex-direction: column;
    gap: 6px;
    flex: 1;
    min-width: 240px;
}

.slider-row {
    display: flex;
    align-items: center;
    gap: 10px;
}

.slider-row label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem;
    color: var(--muted);
    width: 52px;
    text-align: right;
}

input[type=range] {
    flex: 1;
    accent-color: var(--accent);
    height: 4px;
    cursor: pointer;
}

.nudge-group {
    display: flex;
    gap: 6px;
    align-items: center;
}

button {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.8rem;
    padding: 6px 12px;
    border-radius: 4px;
    border: 1px solid var(--border);
    background: var(--panel-alt);
    color: var(--text);
    cursor: pointer;
    transition: background 0.15s, border-color 0.15s, color 0.15s;
}

button:hover { background: var(--border); }

.btn-confirm {
    background: var(--green);
    border-color: var(--green);
    color: var(--nav-bg);
    font-weight: 600;
}

.btn-confirm:hover { background: #e8ff5a; border-color: #e8ff5a; }

.btn-skip {
    border-color: var(--danger);
    color: var(--danger);
}

.btn-skip:hover { background: rgba(251,113,133,0.12); }

.btn-download {
    background: var(--accent);
    border-color: var(--accent);
    color: var(--nav-bg);
    font-weight: 600;
}

.btn-download:hover { background: #93c5fd; border-color: #93c5fd; }

.actions-row {
    display: flex;
    gap: 10px;
    align-items: center;
    margin-left: auto;
}

#summaryPanel {
    display: none;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 20px 24px;
    gap: 16px;
    flex-direction: column;
}

#summaryPanel h2 {
    font-size: 1rem;
    font-weight: 600;
    color: var(--text);
}

.summary-table {
    width: 100%;
    border-collapse: collapse;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.82rem;
}

.summary-table th {
    text-align: left;
    color: var(--muted);
    font-weight: 500;
    padding: 4px 12px 8px 0;
    border-bottom: 1px solid var(--border);
}

.summary-table td {
    padding: 5px 12px 5px 0;
    border-bottom: 1px solid rgba(31,41,55,0.5);
    color: var(--text);
}

.offset-pos  { color: var(--green)  !important; }
.offset-neg  { color: var(--danger) !important; }
.offset-zero { color: var(--muted)  !important; }
.cell-skip   { color: var(--muted)  !important; font-style: italic; }
.cell-ok     { color: var(--accent) !important; }

#toast {
    position: fixed;
    bottom: 24px;
    right: 24px;
    background: var(--panel);
    border: 1px solid var(--accent);
    color: var(--text);
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.8rem;
    padding: 10px 18px;
    border-radius: 6px;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.3s;
    z-index: 999;
}

#toast.show { opacity: 1; }
</style>"""

BODY_HTML = """\
<nav>
  <a href="/~u1460207/dashboard/" class="nav-brand">
    <img src="/~u1460207/src/BlockU_RGB.png" alt="U" class="nav-logo">
    CH&#8324; Time Sync
  </a>
  <ul class="nav-links">
    <li><a href="/~u1460207/dashboard/">Home</a></li>
    <li><a href="/~u1460207/dashboard/viewer/">Map Viewer</a></li>
    <li><a href="/~u1460207/dashboard/analysis/">Analysis</a></li>
    <li><a href="/~u1460207/dashboard/about/">About</a></li>
  </ul>
</nav>

<div class="container">

  <div class="file-bar">
    <span class="file-label">Aeris file</span>
    <span class="file-name" id="fileName">&#8212;</span>
    <span class="file-counter" id="fileCounter"></span>
    <div class="progress-row" id="progressDots"></div>
  </div>

  <div class="plot-panel">
    <div id="chart"></div>
  </div>

  <div class="controls" id="controlsPanel">
    <div class="control-group">
      <span class="control-label">Offset (s)</span>
      <div class="offset-display" id="offsetDisplay">+0.0 s</div>
    </div>
    <div class="slider-wrap">
      <div class="slider-row">
        <label>Coarse</label>
        <input type="range" id="sliderCoarse" min="-120" max="120" step="1" value="0">
      </div>
      <div class="slider-row">
        <label>Fine</label>
        <input type="range" id="sliderFine" min="-5" max="5" step="0.1" value="0">
      </div>
    </div>
    <div class="control-group">
      <span class="control-label">Nudge</span>
      <div class="nudge-group">
        <button onclick="nudge(-10)">&#8722;10s</button>
        <button onclick="nudge(-1)">&#8722;1s</button>
        <button onclick="nudge(-0.1)">&#8722;0.1s</button>
        <button onclick="nudge(0.1)">+0.1s</button>
        <button onclick="nudge(1)">+1s</button>
        <button onclick="nudge(10)">+10s</button>
      </div>
    </div>
    <div class="actions-row">
      <button class="btn-skip" onclick="skipFile()">Skip</button>
      <button onclick="resetOffset()">Reset</button>
      <button class="btn-confirm" onclick="confirmOffset()">Confirm &#10003;</button>
    </div>
  </div>

  <div id="summaryPanel">
    <h2>All files reviewed</h2>
    <table class="summary-table">
      <thead><tr><th>File</th><th>Offset (s)</th><th>Status</th></tr></thead>
      <tbody id="summaryBody"></tbody>
    </table>
    <div>
      <button class="btn-download" onclick="downloadOffsets()">&#11015; Download offsets.json</button>
    </div>
  </div>

</div>
<div id="toast"></div>"""

JS_TEMPLATE = """\
<script>
const PICARRO    = PICARRO_DATA_PLACEHOLDER;
const AERIS_FILES = AERIS_DATA_PLACEHOLDER;

let currentIdx    = 0;
let offsets       = {};
let currentOffset = 0;

buildDots();
loadFile(0);

function buildDots() {
    var row = document.getElementById('progressDots');
    row.innerHTML = '';
    AERIS_FILES.forEach(function(f, i) {
        var d = document.createElement('div');
        d.className = 'dot' + (i === 0 ? ' current' : '');
        d.id = 'dot_' + i;
        d.title = f.name;
        row.appendChild(d);
    });
}

function updateDots() {
    AERIS_FILES.forEach(function(f, i) {
        var d = document.getElementById('dot_' + i);
        if (i === currentIdx) {
            d.className = 'dot current';
        } else if (offsets[f.name] === 'skip') {
            d.className = 'dot skipped';
        } else if (offsets[f.name] !== undefined) {
            d.className = 'dot done';
        } else {
            d.className = 'dot';
        }
    });
}

function loadFile(idx) {
    if (idx >= AERIS_FILES.length) { showSummary(); return; }
    currentIdx    = idx;
    currentOffset = 0;
    syncSliders();
    updateDots();
    var f = AERIS_FILES[idx];
    document.getElementById('fileName').textContent    = f.name;
    document.getElementById('fileCounter').textContent = (idx + 1) + ' / ' + AERIS_FILES.length;
    renderChart();
}

function applyOffset(timestamps, offsetSec) {
    return timestamps.map(function(t) {
        var d = new Date(t);
        d.setTime(d.getTime() + offsetSec * 1000);
        return d.toISOString();
    });
}

function renderChart() {
    var f = AERIS_FILES[currentIdx];
    var shiftedTs = applyOffset(f.timestamps, currentOffset);

    var tracePic = {
        x: PICARRO.timestamps,
        y: PICARRO.ch4,
        type: 'scattergl',
        mode: 'lines',
        line: { width: 1.5, color: '#60a5fa' },
        name: 'Picarro CH4'
    };

    var traceAer = {
        x: shiftedTs,
        y: f.ch4,
        type: 'scattergl',
        mode: 'lines',
        line: { width: 1.5, color: '#CFFF04' },
        name: 'Aeris CH4 (shifted)'
    };

    var layout = {
        autosize: true,
        paper_bgcolor: '#121826',
        plot_bgcolor: '#020617',
        font: { color: '#e5e7eb' },
        xaxis: {
            title: { text: 'Time (UTC)', font: { color: '#9ca3af' } },
            tickfont: { color: '#9ca3af' },
            gridcolor: '#1f2937',
            zerolinecolor: '#1f2937'
        },
        yaxis: {
            title: { text: 'CH4 (ppm)', font: { color: '#9ca3af' } },
            tickfont: { color: '#9ca3af' },
            gridcolor: '#1f2937',
            zerolinecolor: '#1f2937'
        },
        legend: {
            x: 0.01, y: 0.99,
            bgcolor: 'rgba(2,6,23,0.85)',
            bordercolor: '#1f2937',
            borderwidth: 1,
            font: { color: '#e5e7eb', size: 12 }
        },
        margin: { l: 65, r: 30, t: 30, b: 50 }
    };

    Plotly.react('chart', [tracePic, traceAer], layout, { responsive: true });
}

function updateChart() {
    var f = AERIS_FILES[currentIdx];
    var shiftedTs = applyOffset(f.timestamps, currentOffset);
    Plotly.restyle('chart', { x: [shiftedTs] }, [1]);
}

var sliderCoarse  = document.getElementById('sliderCoarse');
var sliderFine    = document.getElementById('sliderFine');
var offsetDisplay = document.getElementById('offsetDisplay');

sliderCoarse.addEventListener('input', function() {
    currentOffset = parseFloat(sliderCoarse.value) + parseFloat(sliderFine.value);
    refreshDisplay();
    updateChart();
});

sliderFine.addEventListener('input', function() {
    currentOffset = parseFloat(sliderCoarse.value) + parseFloat(sliderFine.value);
    refreshDisplay();
    updateChart();
});

function syncSliders() {
    var coarse = Math.round(currentOffset);
    var fine   = parseFloat((currentOffset - coarse).toFixed(1));
    sliderCoarse.value = Math.max(-120, Math.min(120, coarse));
    sliderFine.value   = Math.max(-5,   Math.min(5,   fine));
    refreshDisplay();
}

function refreshDisplay() {
    var sign = currentOffset >= 0 ? '+' : '';
    offsetDisplay.textContent = sign + currentOffset.toFixed(1) + ' s';
    offsetDisplay.className   = 'offset-display' + (currentOffset < 0 ? ' negative' : '');
}

function nudge(delta) {
    currentOffset = parseFloat((currentOffset + delta).toFixed(2));
    syncSliders();
    updateChart();
}

function resetOffset() {
    currentOffset = 0;
    syncSliders();
    updateChart();
}

function confirmOffset() {
    var name = AERIS_FILES[currentIdx].name;
    offsets[name] = parseFloat(currentOffset.toFixed(2));
    var sign = currentOffset >= 0 ? '+' : '';
    toast('Confirmed ' + name + ': ' + sign + currentOffset.toFixed(1) + 's');
    loadFile(currentIdx + 1);
}

function skipFile() {
    var name = AERIS_FILES[currentIdx].name;
    offsets[name] = 'skip';
    toast('Skipped ' + name);
    loadFile(currentIdx + 1);
}

function showSummary() {
    document.querySelector('.plot-panel').style.display  = 'none';
    document.getElementById('controlsPanel').style.display = 'none';
    var panel = document.getElementById('summaryPanel');
    panel.style.display = 'flex';

    var tbody = document.getElementById('summaryBody');
    tbody.innerHTML = '';

    AERIS_FILES.forEach(function(f) {
        var val   = offsets[f.name];
        var tr    = document.createElement('tr');
        var nameTd = document.createElement('td');
        var offTd  = document.createElement('td');
        var statTd = document.createElement('td');
        nameTd.textContent = f.name;

        if (val === 'skip') {
            offTd.textContent  = '\u2014';
            offTd.className    = 'cell-skip';
            statTd.textContent = 'skipped';
            statTd.className   = 'cell-skip';
        } else if (val === undefined) {
            offTd.textContent  = '\u2014';
            offTd.className    = 'cell-skip';
            statTd.textContent = 'not reviewed';
            statTd.className   = 'cell-skip';
        } else {
            var sign = val >= 0 ? '+' : '';
            offTd.textContent  = sign + val.toFixed(2);
            offTd.className    = val > 0 ? 'offset-pos' : val < 0 ? 'offset-neg' : 'offset-zero';
            statTd.textContent = 'confirmed';
            statTd.className   = 'cell-ok';
        }

        tr.appendChild(nameTd);
        tr.appendChild(offTd);
        tr.appendChild(statTd);
        tbody.appendChild(tr);
    });

    updateDots();
}

function downloadOffsets() {
    var result = {};
    AERIS_FILES.forEach(function(f) {
        var val = offsets[f.name];
        if (val === 'skip' || val === undefined) return;
        result[f.name] = val;
    });
    var blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' });
    var url  = URL.createObjectURL(blob);
    var a    = document.createElement('a');
    a.href     = url;
    a.download = 'offsets.json';
    a.click();
    URL.revokeObjectURL(url);
}

function toast(msg) {
    var el = document.getElementById('toast');
    el.textContent = msg;
    el.classList.add('show');
    setTimeout(function() { el.classList.remove('show'); }, 2200);
}
</script>
</body>
</html>"""


def build_html(picarro_json: str, aeris_json: str) -> str:
    head = (
        "<!DOCTYPE html>\n"
        "<html lang='en'>\n"
        "<head>\n"
        "<meta charset='UTF-8'/>\n"
        "<meta name='viewport' content='width=device-width, initial-scale=1.0'/>\n"
        "<title>CH4 Time Sync - Mobile Atmos</title>\n"
        "<script src='https://cdn.plot.ly/plotly-2.30.0.min.js'></script>\n"
        + CSS + "\n"
        "</head>\n"
        "<body>\n"
    )

    js = JS_TEMPLATE.replace("PICARRO_DATA_PLACEHOLDER", picarro_json)
    js = js.replace("AERIS_DATA_PLACEHOLDER", aeris_json)

    return head + BODY_HTML + "\n" + js


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate a static CH4 time-sync HTML tool.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--picarro", "-p", required=True,
                        help="Cleaned Picarro CSV (TIMESTAMP index).")
    parser.add_argument("--aeris", "-a", required=True,
                        help="Cleaned Aeris CSV or directory of CSVs.")
    parser.add_argument("--out", "-o", required=True,
                        help="Output directory for index.html.")
    parser.add_argument("--pic-col", default="CH4_dry",
                        help="CH4 column name in Picarro file. [%(default)s]")
    parser.add_argument("--aer-col", default="CH4",
                        help="CH4 column name in Aeris file(s). [%(default)s]")
    args = parser.parse_args()

    picarro_path = Path(args.picarro)
    aeris_path   = Path(args.aeris)
    out_dir      = Path(args.out).expanduser()

    if not picarro_path.exists():
        print(f"Error: Picarro file not found — {picarro_path}")
        sys.exit(1)

    # Load Picarro
    print(f"Loading Picarro: {picarro_path.name}  (col: '{args.pic_col}')")
    try:
        pic_ts, pic_ch4 = load_csv(picarro_path, args.pic_col)
    except KeyError as e:
        print(f"Error: {e}")
        sys.exit(1)
    print(f"  {len(pic_ts):,} records  |  {pic_ts[0][:19]}  ->  {pic_ts[-1][:19]}")

    # Load Aeris files
    aeris_files = collect_aeris_files(aeris_path)
    print(f"\nAeris files ({len(aeris_files)}):")

    aeris_list = []
    for f in aeris_files:
        try:
            ts, ch4 = load_csv(f, args.aer_col)
            aeris_list.append({"name": f.name, "timestamps": ts, "ch4": ch4})
            print(f"  ok  {f.name}  ({len(ts):,} records)")
        except Exception as e:
            print(f"  !!  {f.name}  skipped -- {e}")

    if not aeris_list:
        print("Error: no Aeris files loaded successfully.")
        sys.exit(1)

    picarro_json = json.dumps({"timestamps": pic_ts, "ch4": pic_ch4})
    aeris_json   = json.dumps(aeris_list)

    html = build_html(picarro_json, aeris_json)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "index.html"
    out_path.write_text(html, encoding="utf-8")

    print(f"\nWritten -> {out_path}")
    try:
        rel = out_path.relative_to(Path.home() / "public_html")
        print(f"Open:    https://home.chpc.utah.edu/~u1460207/{rel}")
    except ValueError:
        print(f"Open the file in your browser: {out_path}")
    print()


if __name__ == "__main__":
    main()