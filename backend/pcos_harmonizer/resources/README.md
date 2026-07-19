# PCOS Canonical Schema (v0.1)

`pcos_schema_v0.1.json` is a shared data model for harmonizing cross-sectional
PCOS research datasets (NHANES, clinic exports, cohort studies, etc.) onto one
set of field names, units, and typed missingness — organized around the
**Rotterdam 2003 criteria**. It's a draft (`CC BY 4.0`) and **not clinically
validated**; treat it as a research tool, not a diagnostic instrument.

This document explains the schema itself and how to actually get your dataset
onto it using the `pcos_harmonizer` package in this repo.

## Why harmonize onto it

PCOS datasets are notoriously hard to pool: cycle-length thresholds, androgen
assay platforms, and even what "missing" means all vary by source. This
schema exists to make those differences **explicit and machine-readable**
instead of silently lost during a merge. Concretely, every field carries:

- **A frozen field name and id** (`x_id`) — ids are permanent from v0.1
  onward, so mapping files you write today keep resolving as the schema grows.
- **A canonical unit**, both human-readable (`x_unit`, e.g. `"nmol/L"`) and
  machine-readable (`x_unit_ucum`, e.g. `"nmol/L"` per [UCUM](https://ucum.org)).
- **Typed missingness** — missing values are never blank. They're one of
  `not_measured`, `below_lod`, `not_applicable`, `withheld`, `unknown`, so you
  can distinguish "we didn't ask" from "below detection limit" from "doesn't
  apply because of a hysterectomy."
- **Full provenance** — every populated field gets a matching entry in
  `_provenance` recording whether it was mapped from a source column or
  computed, what the raw value/unit were, a mapping confidence, and whether a
  human reviewed it.

## How the schema is organized

Fields are grouped via `x_group`:

| Group | What it covers |
|---|---|
| `identity` / `demographics` | subject id, age, anthropometrics |
| `confounders` | contraceptive use, pregnancy, menopause, metformin/antiandrogen use — things that invalidate other fields if not accounted for |
| `criterion_1_ovulatory` | cycle length/irregularity, luteal progesterone |
| `criterion_2_hyperandrogenism` | testosterone, SHBG, FAI, DHEAS, hirsutism, acne |
| `criterion_3_pcom` | antral follicle count, ovarian volume, AMH |
| `gonadotropins` | LH, FSH, estradiol |
| `exclusions` | TSH, prolactin, 17-OHP, cortisol — conditions that must be ruled out before a PCOS label is meaningful |
| `metabolic` | glucose, insulin, HOMA-IR, lipids, blood pressure |
| `fertility`, `mental_health`, `diagnosis`, `sample_context` | self-explanatory |

Look up any field's group, unit, and hints with the registry (see below), or
just read the schema — it's the source of truth.

### Computed fields (`x_fallback`)

Some fields (`bmi`, `waist_hip_ratio`, `free_androgen_index`, `homa_ir`,
`antral_follicle_count_max`, `ovarian_volume_max_ml`, `lh_fsh_ratio`) can be
**derived** from other canonical fields when your source doesn't supply them
directly — e.g. `bmi = weight_kg / (height_cm/100)**2`. A source-supplied
value always wins; a field is only computed when every required input is
present in the right unit. This is a convenience, not a diagnostic
algorithm — the schema deliberately defines no criteria-evaluation or
phenotyping logic itself (that's the pipeline's job, informed by published
guidelines).

### Validator rules

`x_validator_rules` encodes cross-field consistency checks a harmonized
dataset should satisfy — e.g. "if `hormonal_contraceptive_use = current`,
androgen and cycle fields must carry a suppression warning" or "if any
androgen value is present and `androgen_assay_method` is missing, emit a
critical warning." These aren't hard rejections; most surface as warnings so
you can judge whether they matter for your analysis.

### Coverage report & verdict

`x_coverage_report` lists, per Rotterdam criterion, which fields count as
direct evidence for it, plus which confounders are "critical" (contraceptive
use, assay method, pregnancy status). The `verdict_rule` states the pipeline's
bar for usability: **at least 2 of 3 criteria evaluable AND
`exclusions_assessed_flag` populated**. "This dataset cannot support a
Rotterdam diagnosis" is a legitimate, useful answer — the pipeline reports it
plainly rather than softening it.

## Using it: harmonizing your own dataset

The `pcos_harmonizer` package turns raw files (NHANES `.xpt`, CSV, TSV, Excel)
into a table conforming to this schema, plus a coverage report.

```bash
pip install -r backend/requirements.txt
```

```python
from pcos_harmonizer.pipeline import run_pipeline

result = run_pipeline(
    input_paths=["data/my_cohort.csv"],
    output_path="outputs/my_cohort_standardized.csv",
    source=None,       # or "nhanes" if you're using NHANES variable naming
)

print(result.coverage_text)   # human-readable coverage report + verdict
result.table                  # pandas DataFrame in canonical column names/units
result.provenance              # per-field provenance dict
result.warnings                 # validator + transform/derive warnings
```

What happens under the hood, in order:

1. **Ingest** (`ingest/`) — reads your file(s) and joins them on a subject key.
2. **Propose** (`propose/`) — matches your source columns to canonical fields.
   Column names are matched against each field's `x_hints` (common aliases,
   including NHANES variable codes); an LLM proposer can also be used, with a
   confidence score attached to every guess. This writes a **mapping file**
   (`mapping.yaml`) — nothing is applied yet.
3. **Review the mapping file.** This is the step that matters most for
   research use: open `outputs/mapping.yaml`, check `canonical_field`,
   `unit_raw`, and `mapping_confidence` for each of your source columns, and
   fix anything wrong. Columns whose unit couldn't be inferred are listed
   under `blocked` and are *not* converted until you supply `unit_raw`
   yourself — unit conversion is always done by deterministic code, never
   guessed by the LLM.
4. **Transform** (`transform/`) — applies your reviewed mapping: unit
   conversion (via the field's `x_conversions`/`x_unit_ucum`), value-map
   standardization for categorical fields, and typed-missingness coding.
5. **Derive** (`derive/`) — fills in computed fields per `x_fallback` where a
   source value is absent.
6. **Validate** (`validate/`) — runs `x_validator_rules` and flags any value
   outside a field's `x_range` (a plausibility warning, not a hard failure —
   it may just mean an unconverted unit).
7. **Report** (`report/`) — builds the coverage report and verdict described
   above.

Once you've hand-reviewed a mapping file, re-run deterministically without
re-proposing or touching the network:

```python
from pcos_harmonizer.pipeline import run_from_mapping

result = run_from_mapping(input_paths=["data/my_cohort.csv"],
                           mapping_path="outputs/mapping.yaml")
```

### Inspecting the schema programmatically

```python
from pcos_harmonizer.schema.loader import get_registry

registry = get_registry()
registry.get("total_testosterone").unit        # "nmol/L"
registry.fields_in_group("criterion_2_hyperandrogenism")
registry.critical_fields()                      # fields whose absence blocks interpretation
registry.coverage_config                        # the x_coverage_report block
registry.validator_rules                        # the x_validator_rules list
```

### Output formats

`result.table` can be written to csv/tsv/json/jsonl/xlsx/parquet/stata/xpt.
For JSON/JSONL the canonical values are written directly; for all other
formats, provenance is written alongside as a
`<name>_provenance.json` sidecar (provenance isn't currently nested inline for
JSON output, despite the schema defining a `_provenance` field — keep the
sidecar file if you need per-value provenance from a JSON export).

## Caveats for research use

- **Draft schema, not clinically validated.** Field boundaries and thresholds
  (e.g. PCOM antral-follicle cutoffs) reflect published literature but haven't
  been independently validated for this tool.
- **LOINC codes marked `x_loinc_verified: false`** are provisional — confirm
  against loinc.org before relying on them for cross-system interoperability.
- **`race_ethnicity` and similar labels are preserved verbatim**, not recoded
  — don't assume comparability across source datasets without checking.
- **Diagnosis fields (`pcos_diagnosis_flag`, `phenotype`, `criteria_met`) are
  observations, not derived results** — they reflect what a source reported,
  and always require `diagnostic_criteria_version` + `diagnosis_source` to be
  interpretable, since diagnostic criteria have changed substantially over
  time (NIH 1990 → Rotterdam 2003 → AE-PCOS 2006 → Intl 2018/2023).
