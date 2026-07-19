# HackNation6

Challenge #5: Foundation Models for Women's Hormonal Health

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m ipykernel install --user --name=hacknation6 --display-name="HackNation6 (.venv)"
```

Put any SAS XPORT (`.xpt`) files in `data/`:

```bash
curl -L -o data/P_RHQ.xpt \
  https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/P_RHQ.xpt
```

## Explore data (Jupyter)

General-purpose notebook — change `XPT_NAME` (or `XPT_PATH`) to analyse any file in `data/`.

Select kernel **HackNation6 (.venv)**, then:

```bash
source .venv/bin/activate
jupyter notebook notebooks/explore_xpt.ipynb
```

## Backend: PCOS harmonizer

The `backend/pcos_harmonizer` package maps raw research datasets onto the PCOS
canonical schema via an auditable pipeline (ingest → profile → LLM propose →
review → transform → derive → validate → report). The LLM runs **only** in the
propose step; everything after is deterministic.

```bash
pip install -r backend/requirements.txt
cd backend && python -m pytest        # 48 tests
```

## App (Streamlit UI + backend)

```bash
pip install -r backend/requirements.txt -r UI/requirements.txt
streamlit run UI/upload/app.py
```

Configure via `.env` (git-ignored):

- `OPENAI_API_KEY` — enables the LLM mapping engine.
- `USE_MOCK_DATA=true` — default to the synthetic files in `mock_data/` until the
  real datasets are finalized.

The UI offers three mapping engines with automatic fallback for demos:

1. **AI mapping (LLM)** — falls back to heuristic, then the curated demo mapping.
2. **Heuristic (offline)** — deterministic, no network.
3. **Demo (curated mapping)** — a human-reviewed mapping in
   `mock_data/demo_snapshot/` that always produces a correct result offline.

See `mock_data/README.md` for the bundled synthetic datasets.

## Testing

Instructions for everyone. All commands are run from the repo root unless noted.

### 0. One-time setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt -r UI/requirements.txt
```

The bundled synthetic inputs in `mock_data/` are committed, so tests work with no
network and no API key. If they are ever missing, regenerate them:

```bash
python mock_data/generate_mock_data.py
```

### 1. Unit tests (no network, no API key)

The suite covers the schema loader, the unit converter (checked against the
schema's `x_conversions` oracle), missingness, value maps, derivations, mapping
I/O, the output writer, and an end-to-end NHANES run.

```bash
cd backend && python -m pytest
```

Expected: **48 passed**. (`backend/pyproject.toml` sets `pythonpath`, so no extra
`PYTHONPATH` is needed when running from `backend/`.)

### 2. End-to-end pipeline check (offline, deterministic)

Runs ingest → transform → derive → validate → report on the mock data with no LLM.
The curated "demo" engine should report **"Can support a Rotterdam diagnosis"**;
the heuristic engine will honestly report limited coverage.

```bash
cd backend && PYTHONPATH="$PWD" python -c "
from pcos_harmonizer import app_api
from pcos_harmonizer.config import mock_data_files
paths = [p for p in mock_data_files() if 'clinic' in p.name]
for engine in ['demo', 'heuristic']:
    o = app_api.analyze(paths, engine=engine, source=None)
    print(engine, '->', o.result.coverage['verdict'])
"
```

### 3. LLM test (needs `OPENAI_API_KEY` + network)

Add your key to `.env` (git-ignored), then run the real AI mapping engine:

```bash
echo 'OPENAI_API_KEY=sk-...' >> .env
cd backend && PYTHONPATH="$PWD" python -c "
from pcos_harmonizer import app_api
from pcos_harmonizer.config import mock_data_files
paths = [p for p in mock_data_files() if 'clinic' in p.name]
o = app_api.analyze(paths, engine='llm', source=None)
print('engine used:', o.engine_used, '| verdict:', o.result.coverage['verdict'])
"
```

Expected: `engine used: llm | verdict: Can support a Rotterdam diagnosis`. If the
call fails (no key, quota, network), it automatically falls back to the heuristic
then the curated demo — the run never crashes.

### 4. UI test (manual)

```bash
streamlit run UI/upload/app.py
```

Then in the browser: keep **Use bundled mock data** on, select
`mock_pcos_clinic.xpt`, pick a **mapping engine** in the sidebar, and click
**Analyze Dataset**. Check the *Coverage report*, *Column mapping*, *Standardized
data*, *Warnings*, and *Download* tabs. Try the **Demo (curated mapping)** engine
first — it works offline with no API key.
