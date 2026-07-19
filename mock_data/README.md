# mock_data

Synthetic `.xpt` inputs for testing and demoing the PCOS harmonizer. **Not real
patient data.** These stand in for uploaded research datasets until the real
files are finalized. The app uses them when `USE_MOCK_DATA=true` in `.env`.

## Files

- `mock_pcos_clinic.xpt` — a fertility-clinic-style cohort (40 subjects) spanning
  all three Rotterdam criteria plus confounders and exclusions. Column names
  differ from the schema and NHANES codes, and weight/height are in imperial
  units, so it exercises LLM mapping, value standardization, and unit conversion.
  With a correct mapping it yields **"Can support a Rotterdam diagnosis."**
- `mock_nhanes_repro.xpt` — a reproductive-health-only file (30 subjects) using
  real NHANES variable codes and missing sentinels. Coverage is intentionally
  limited → **"Cannot support a Rotterdam diagnosis"** (a valid, useful result).

## Regenerate

```bash
python mock_data/generate_mock_data.py
```

## demo_snapshot/

`mock_pcos_clinic.mapping.yaml` is a human-reviewed mapping used as the
**offline demo fallback**: it runs deterministically with no network (via
`run_from_mapping`), so the UI's "Demo (curated mapping)" engine — and the
automatic fallback when the LLM/heuristic fail — always produces a correct,
presentable result.
