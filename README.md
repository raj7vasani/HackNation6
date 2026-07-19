# PCOS Schema Mapper

**An open, Rotterdam-criteria-grounded canonical schema for PCOS research data, plus an AI-assisted, human-reviewed tool that maps any raw dataset into it.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](backend/pyproject.toml)
[![Tests: pytest](https://img.shields.io/badge/tests-pytest-informational)](#testing)

Research on PCOS (Polycystic Ovary Syndrome) is fragmented across incompatible data sources — population surveys (NHANES), hospital exports, and independent studies each capture the same clinical variables under different column names, units, and formats. This project defines an open data schema grounded in the [Rotterdam diagnostic criteria](docs/PCOS_SCHEMA_SPEC.md) and provides a pipeline that harmonizes any input dataset into it: an LLM *proposes* column mappings, a human *reviews* them, and deterministic code executes every transformation. No model ever touches a number.

📖 **[Problem statement](docs/PROBLEM_STATEMENT.md)** · **[Schema spec](docs/PCOS_SCHEMA_SPEC.md)** · **[Architecture diagram](docs/diagrams/architecture.md)** · **[Implementation notes](docs/IMPLEMENTATION_NOTES.md)**

---

## Contents

- [How it works](#how-it-works)
- [Quickstart](#quickstart)
- [Project layout](#project-layout)
- [Configuration](#configuration)
- [Testing](#testing)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

## How it works

```
input files → ingest → profile → propose (LLM) → review (human) → transform → derive → validate → report
```

The LLM runs **only** in the *propose* step, suggesting which source column maps to which canonical field and in what unit. Every step after that — unit conversion, derived fields (BMI, free androgen index, HOMA-IR, …), Rotterdam criterion flags, validation, and the coverage report — is deterministic, reproducible Python. A run can also **pause mid-pipeline** to ask for a unit when it can't infer one confidently, rather than guessing.

See the [architecture diagram](docs/diagrams/architecture.md) for the full data flow.

## Quickstart

Requires Python 3.11+.

```bash
git clone <this-repo>
cd HackNation6
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the app:

```bash
streamlit run UI/upload/app.py
```

Toggle **"Use bundled mock data"** in the UI to try it immediately with no setup — synthetic datasets in `mock_data/` let you explore the full pipeline offline, with no API key required.

## Project layout

```
backend/pcos_harmonizer/   Core pipeline: ingest, profile, propose (LLM), transform, derive, validate, report
UI/upload/                 Streamlit app
docs/                      Schema spec, problem statement, architecture, implementation notes
mock_data/                 Synthetic datasets + a curated offline demo mapping
data/                      Drop your own NHANES/.xpt files here
notebooks/                 Exploratory Jupyter notebook for raw .xpt files
```

## Configuration

Set these in a `.env` file at the repo root (git-ignored):

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | Enables the AI mapping engine. Without it, the app falls back to a deterministic offline heuristic. |
| `USE_MOCK_DATA` | Set `true` to default to the bundled synthetic datasets in `mock_data/`. |

The UI offers three mapping engines with automatic fallback, so a demo never fails to produce a result:

1. **AI mapping (LLM)** → falls back to heuristic → falls back to the curated demo mapping.
2. **Heuristic (offline)** — deterministic, no network.
3. **Demo (curated mapping)** — a human-reviewed mapping that always produces a correct result offline.

## Testing

```bash
cd backend
python -m pytest
```

The suite covers the schema loader, the unit converter (checked against the schema's own `x_conversions` oracle), missingness handling, value maps, derivations, mapping I/O, the output writer, the interactive review flow, the chat assistant, and an end-to-end NHANES run — all offline, with no API key required.

## Documentation

- [Problem statement](docs/PROBLEM_STATEMENT.md) — why this project exists
- [PCOS canonical schema spec](docs/PCOS_SCHEMA_SPEC.md) — field definitions, units, validity conditions
- [Implementation notes](docs/IMPLEMENTATION_NOTES.md) — pipeline mechanics, unit conversion strategy, build order
- [LLM integration](docs/LLM_INTEGRATION.md) — how the proposer prompts and parses the model
- [Field value mappings](docs/FIELD_VALUE_MAPPINGS.md) — categorical/enum standardization reference
- [Architecture diagram](docs/diagrams/architecture.md)
- [mock_data/README.md](mock_data/README.md) — bundled synthetic datasets

## Contributing

Issues and pull requests are welcome. Please run the test suite before submitting a change, and keep the core boundary intact: the LLM proposes column mappings only — it must never perform unit conversion, derivation, or diagnosis logic.

## License

[MIT](LICENSE)
