# Implementation Notes — PCOS Harmonizer

Companion to `PCOS_SCHEMA_SPEC.md` and `pcos_schema_v0.1.json`.

The spec defines *what* the canonical schema is — field semantics, units,
validity conditions — and is written for researchers. This file defines *how* to
build a tool that produces conforming data, and is written for developers.
`pcos_schema_v0.1.json` is authoritative for field names, types, ranges, and
validation rules.

Where the spec and this file disagree, the spec wins for semantics and this file
wins for mechanics.

---

## 1. Pipeline overview

```
input files
    │
    ▼
[1] ingest ────────── read CSV / XPT / XLSX, extract headers + sample values
    │
    ▼
[2] profile ───────── per column: dtype, n_unique, min/max, sample values,
    │                 null rate, candidate unit signals
    ▼
[3] propose ───────── LLM: source column → canonical field + inferred unit_raw
    │                 emits mapping file (YAML). NO numeric work here.
    ▼
[4] review ────────── human edits mapping file, sets human_reviewed: true
    │
    ▼
[5] transform ─────── deterministic: unit conversion, missingness coding,
    │                 enum normalization. Reads mapping file only.
    ▼
[6] derive ────────── deterministic: arithmetic + clinical logic (spec §7)
    │
    ▼
[7] validate ──────── run x_validator_rules, emit warnings
    │
    ▼
[8] report ────────── coverage report + standardized output
```

Notes:
- [1] `sample values` (5-10) exclude NaN values when possible
- [4] the UI should split review by section
- [4] UI should take confidence into account so it puts "low" confidence mappings into view
- [4] High confidence mappings should still be reviewable but only if user wishes to do it
- [5] Need to ensure our unit conversions are comprensive, if we don't have a mapping, the user should provide a factor from unit_raw to unit_canonical

**The hard boundary is between [3] and [5].** The LLM proposes; deterministic
code executes. No LLM call after step 3. This is the project's core claim — if
it leaks, the "auditable, not a black box" pitch collapses.

---

## 2. Unit conversion — do NOT hand-write a conversion table

The naive approach is a dict of every (source_unit, canonical_unit) pair. Don't.
It grows quadratically and it will be wrong. Three layers instead:

### Layer 1 — physical units: use `pint`

```python
import pint
ureg = pint.UnitRegistry()

def convert_physical(value, from_unit, to_unit):
    return (value * ureg(from_unit)).to(to_unit).magnitude

convert_physical(154, 'pound', 'kilogram')   # 69.853...
convert_physical(65, 'inch', 'centimeter')   # 165.1
```

Covers `height_cm`, `weight_kg`, `waist_circumference_cm`,
`hip_circumference_cm` — anything dimensionally convertible. You write zero
factors.

### Layer 2 — molar conversions: one molecular weight per analyte

`pint` cannot do ng/dL → nmol/L without knowing the substance. Store molar mass,
not conversion factors — then every mass/volume unit pair works automatically.

```python
MOLAR_MASS_G_PER_MOL = {
    'total_testosterone':      288.42,
    'free_testosterone':       288.42,
    'estradiol':               272.38,
    'progesterone_luteal':     314.46,
    'androstenedione':         286.41,
    'dheas':                   368.49,
    'cortisol':                362.46,
    '17_hydroxyprogesterone':  330.46,
    'fasting_glucose':         180.16,
    'ogtt_2hr_glucose':        180.16,
    'total_cholesterol':       386.65,
    'hdl_cholesterol':         386.65,
    'ldl_cholesterol':         386.65,
}

def convert_molar(value, from_unit, to_unit, field):
    mm = MOLAR_MASS_G_PER_MOL[field] * ureg('g/mol')
    q = value * ureg(from_unit)
    if q.check('[mass]/[volume]') and ureg(to_unit).check('[substance]/[volume]'):
        return (q / mm).to(to_unit).magnitude
    if q.check('[substance]/[volume]') and ureg(to_unit).check('[mass]/[volume]'):
        return (q * mm).to(to_unit).magnitude
    return q.to(to_unit).magnitude
```

13 numbers replace ~50 pairwise factors, and they extend to unit pairs you
didn't anticipate.

### Layer 3 — irregular cases: an explicit short list

These have no clean molar route. Hard-code them and comment why.

| Field | Conversion | Why it's special |
|---|---|---|
| `fasting_insulin` | µIU/mL → pmol/L × 6.945 | IU-based; potency-defined, not mass-defined |
| `prolactin` | ng/mL → mIU/L × 21.2 | IU-based; factor is assay-standard-dependent |
| `hba1c_percent` | NGSP% = (IFCC × 0.0915) + 2.15 | Affine, not multiplicative |
| `triglycerides` | mg/dL → mmol/L × 0.0113 | Molar mass varies with fatty-acid composition; 0.0113 is a conventional average |
| `shbg`, `lh`, `fsh`, `tsh` | none typically required | Already conventionally nmol/L, IU/L, IU/L, mIU/L — still record `unit_raw` |

> `free_androgen_index` and `homa_ir` are **derived**, not converted. See §4.

### Testing the converter

`x_conversions` in the JSON Schema lists explicit factors. Keep them as a test
oracle:

```python
def test_converter_matches_spec():
    for field, conv in schema_conversions().items():
        for src_unit, factor in conv.items():
            if not isinstance(factor, (int, float)):
                continue  # skip affine formulas like HbA1c
            got = convert(1.0, src_unit, canonical_unit(field), field)
            assert abs(got - factor) / factor < 0.01, (field, src_unit, got, factor)
```

If this fails, either the spec factor or your molar mass is wrong. Find out now,
not during the demo.

---

## 3. Unit *detection* is the hard part, not conversion

The arithmetic is solved. The real problem is a column of bare numbers with no
unit metadata — the common case in real datasets.

**Signals available, in order of reliability:**

1. **Explicit unit metadata** — column name suffix (`testosterone_ng_dl`), a
   units row, a codebook. Trust it.
2. **Value range** — `x_range` in the JSON plus the disambiguation notes.
   Testosterone at 0.5–3 is nmol/L; at 15–90 it's ng/dL. Glucose at 4–7 is
   mmol/L; at 70–130 it's mg/dL. This is where most detection happens.
3. **Dataset convention** — NHANES publishes units per variable; a source-
   specific override map beats inference.
4. **LLM inference from column name + samples** — the fallback.

**When detection is ambiguous, block rather than guess.**

```python
if unit_raw is None or confidence < THRESHOLD:
    field.status = 'BLOCKED_UNIT_UNKNOWN'
    # no conversion, no derivation, surfaced in review UI
```

A weight of `154` read as kg instead of lb produces a BMI of 66.8 instead of
30.4, and nothing downstream catches it. Blocking is the correct behaviour and
it demos well — show the tool refusing.

**Source-specific overrides beat inference.** Ship a small file:

```yaml
# sources/nhanes.yaml
LBXTST:  { field: total_testosterone, unit: ng/dL }
LBXSHBG: { field: shbg,               unit: nmol/L }
LBXGLU:  { field: fasting_glucose,    unit: mg/dL }
LBXIN:   { field: fasting_insulin,    unit: uIU/mL }
```

When a known source is detected, these take precedence over LLM proposals and
the mapping is marked `source: override` with confidence 1.0.

---

## 4. Derivation ≠ conversion

Two distinct mechanisms; keep them in separate modules.

- **Conversion** rescales a value that *was* present. Same measurement.
- **Derivation** computes a field that was *absent*, from fields that were
  present.

Spec §7 defines *what* each derived field means and when it is valid. This
section covers *how* to compute them.

### Provenance emission

Every mapped value emits the record in spec §5. Implementation points:

- `human_reviewed` defaults `false` and is **never** set by code. Only an
  explicit reviewer action flips it.
- `value_raw` and `unit_raw` are retained even when no conversion occurred.
  Downstream users need to verify, not trust.
- `transformation_applied` is human-readable, not a code — `"ng/dL -> nmol/L
  (molar, MW 288.42)"`, not `"CONV_017"`. A reviewer must be able to check it
  without reading source.

Worked example — source column `WT` containing `154`:

| Field | Value |
|---|---|
| `source_column_name` | `WT` |
| `value_raw` | `154` |
| `unit_raw` | `lb` (LLM-inferred from range and column name) |
| `value_canonical` | `69.85` |
| `unit_canonical` | `kg` |
| `transformation_applied` | `lb -> kg (pint)` |
| `mapping_confidence` | `0.88` |
| `human_reviewed` | `false` |

### Who does what

The LLM proposes the column mapping and *infers the source unit* — it writes
`unit_raw: "lb"`, it does not compute the converted value. Deterministic code
reads `unit_raw`, applies the conversion, and produces `value_canonical`. No
model arithmetic anywhere in the numeric path.

**Precedence rule:** derivation never overwrites a source-supplied value. If the
source has both `bmi` and its components, keep the source value, compute the
derived one, and record it in `transformation_applied`. Disagreement beyond
rounding tolerance emits a warning — this is a free data-quality check and it's
worth surfacing in the demo.

**Ordering matters.** Derive in dependency order:

```
1. unit conversion (all fields)
2. arithmetic derivations   → bmi, waist_hip_ratio, free_androgen_index,
                              homa_ir, lh_fsh_ratio, antral_follicle_count_max,
                              ovarian_volume_max_ml
3. criterion flags          → ovulatory_dysfunction_derived,
                              hyperandrogenism_derived, pcom_flag
4. diagnosis                → criteria_met → phenotype → pcos_diagnosis_flag
```

Step 4 depends on step 3, which depends on step 2. Compute
`free_androgen_index` before evaluating hyperandrogenism, not after.

**Guard clauses matter more than formulas.** Spec §7.2 lists validity
conditions for each criterion derivation — suppression under current hormonal
contraception, antiandrogen use, pregnancy, hysterectomy, and the adolescent
PCOM window. Implement suppression *first*, then the positive logic. Getting the
order wrong produces a confident wrong flag, which is the worst failure mode in
this project.

Where a derivation is invalid, write `not_applicable` — not `false`, and not a
null. The distinction is load-bearing for downstream analysis.

**Do not hardcode biochemical thresholds.** Spec §7.2 is explicit: use the
source dataset's own reference range where available and record it. Assay-method
differences make universal cut-points unsafe.

### Longitudinal input detection

Spec §8 puts time-series data out of scope. Detect it by repeated `subject_id`
plus a timestamp column, and reject with an explanatory message naming the
offending file. Do not aggregate to fit — the choice of aggregation is a
research decision, and silently making it commits every downstream user to it.

---

## 5. Missingness

Never write a blank or bare `NaN`. Every absent value gets a code from spec §6:
`not_measured`, `below_lod`, `not_applicable`, `withheld`, `unknown`.

**Source-specific sentinel decoding is required.** NHANES uses `7`/`9`,
`77`/`99`, `777`/`999` for refused/don't-know depending on field width. Decoding
these is per-source configuration, not inference:

```yaml
# sources/nhanes.yaml
sentinels:
  RHQ010:  { 777: withheld, 999: unknown }
  RHQ031:  { 7: withheld, 9: unknown }
  RHQ332:  { 7777: withheld, 9999: unknown }
```

Getting this wrong is silently catastrophic — an age at menarche of 999 averaged
into a cohort is not a subtle error, but a `7` read as "7 years old" is.

**`not_applicable` is structural, not missing.** If `hysterectomy_flag` is true,
cycle fields are `not_applicable`, not `not_measured`. The validator enforces
this; implement it in the transform step so the validator confirms rather than
discovers.

---

## 6. Mapping file format

The reviewable artifact. YAML, committed alongside outputs.

```yaml
schema_version: "0.1.0"
source_dataset: "NHANES_2017_2018"
generated_at: "2026-07-19T10:14:00Z"
generator: "llm-proposer v0.1"

join:
  key: SEQN
  files: [DEMO_J.XPT, TST_J.XPT, GLU_J.XPT, RHQ_J.XPT, BMX_J.XPT]

mappings:
  - source_file: TST_J.XPT
    source_column: LBXTST
    canonical_field: total_testosterone
    unit_raw: ng/dL
    unit_canonical: nmol/L
    transformation_applied: "ng/dL -> nmol/L (molar, MW 288.42)"
    mapping_confidence: 1.0
    mapping_rationale: "NHANES source override"
    source: override
    human_reviewed: false

  - source_file: unknown_cohort.csv
    source_column: WT
    canonical_field: weight_kg
    unit_raw: lb
    unit_canonical: kg
    transformation_applied: "lb -> kg (pint)"
    mapping_confidence: 0.88
    mapping_rationale: "Column 'WT'; values 110-260 consistent with pounds"
    source: llm
    human_reviewed: false

unmapped_columns:
  - { source_column: LBXWBCSI, reason: "no canonical field — white blood cell count out of scope" }

blocked:
  - source_column: TESTO
    reason: BLOCKED_UNIT_UNKNOWN
    detail: "Values 1.2-4.8 ambiguous between nmol/L and ng/mL; no unit metadata"
```

Requirements:

- Re-running with the same mapping file must produce byte-identical output.
- `human_reviewed` defaults `false` everywhere and is never set by code.
- `unmapped_columns` and `blocked` are first-class — a mapping file that hides
  what it couldn't handle is worse than useless.

---

## 7. Multi-file ingestion

NHANES is naturally 5–8 XPT files joined on `SEQN`. Support this from the start;
it's also a good demo beat ("insert a set of files").

- Detect a shared key column across files; `SEQN` for NHANES, configurable
  otherwise.
- Left join onto the demographics/anchor file.
- **Reject silently-overlapping columns.** If two files both supply
  `fasting_glucose`, do not pick one — surface the conflict for review.
- Record `source_file` per field. Provenance is per-value, not per-dataset.

Reading XPT: `pandas.read_sas(path, format='xport')`.

---

## 8. Coverage report

The most valuable output. Per spec §9, it answers: **can this dataset support a
Rotterdam diagnosis?**

Structure:

```
Dataset: NHANES_2017_2018        Subjects: 2,148 (female, 18-45)

CRITERION COVERAGE
  1. Ovulatory dysfunction   PARTIAL   amenorrhea only (RHQ031)
                                       no cycle length / regularity
  2. Hyperandrogenism        PARTIAL   total_testosterone 94%, shbg 94%
                                       → free_androgen_index derivable
                                       no DHEAS, no clinical assessment
  3. PCOM                    ABSENT    no ultrasound, no AMH

EXCLUSION WORKUP             ABSENT    no TSH, prolactin, or 17-OHP

CRITICAL CONFOUNDERS
  hormonal_contraceptive_use  MISSING  ← androgen values uninterpretable
  androgen_assay_method       MISSING  ← cross-dataset pooling unsafe
  pregnancy_status            PRESENT  96%

VERDICT: Cannot support a Rotterdam diagnosis.
         Suitable for: metabolic phenotyping, androgen distribution studies.
         Not suitable for: case definition, cross-cohort androgen pooling.
```

The verdict rule is in `x_coverage_report.verdict_rule`. **A dataset failing
coverage is a valid and useful result** — do not treat it as an error path or
soften the language. This output is the product.

---

## 9. LLM prompt construction

Give the proposer, per canonical field: name, canonical unit, type, `x_range`,
`x_hints`, and any disambiguation note. Compact JSON, not prose.

Per source column: name, dtype, null rate, n_unique, 5–10 sample values, min/max.

**Require structured output.** Ask for JSON matching the mapping-file entry
schema. Reject and retry on parse failure rather than repairing by hand.

**Instruct it to prefer null over a guess.** Wrong mappings are worse than gaps
— a gap is visible in the coverage report, a wrong mapping is invisible until it
corrupts an analysis. The prompt should say this explicitly.

**Ask for unit reasoning, not just a unit.** `mapping_rationale` should say
*why* — "values 110-260, column 'WT', consistent with pounds" — so a reviewer
can check the inference rather than the conclusion.

**Batch by group, not all 104 fields at once.** Send the metabolic fields with
the metabolic-looking columns. Better precision, cheaper, and easier to debug.

---

## 10. Build order (12-hour budget)

Parallelize; nobody waits for the spec to be final.

| Priority | Component | Owner | Notes |
|---|---|---|---|
| P0 | JSON Schema loader + field registry | data eng | Everything depends on it |
| P0 | Unit converter (pint + molar + specials) | data eng | Test against `x_conversions` |
| P0 | Mapping file read/write | data eng | Format is the contract |
| P0 | LLM proposer | CS/ML | Structured output, retry on parse fail |
| P0 | Transform executor | data eng | Mapping file in, standardized table out |
| P1 | Coverage report | bioeng | The money output |
| P1 | Validator rules | bioeng | 20 rules in `x_validator_rules` |
| P1 | NHANES source override file | bioeng | Makes the demo work |
| P2 | Arithmetic derivations | CS/ML | bmi, FAI, HOMA-IR |
| P2 | Minimal web UI | PM/CS | Upload → review → download |
| P3 | Clinical-logic derivations | bioeng | Only if P0–P2 are done |

**Cut line:** if you're 3 hours out with a broken tool, ship the spec, the JSON
Schema, and a hand-done worked example. A documented open schema with a
validator is a real contribution; a half-working ingestion app is not.

---

## 11. Known gaps to state, not hide

- Longitudinal data is out of scope (spec §8). Detect and reject; don't flatten.
- No cross-assay calibration. Assay method is *recorded*, not *corrected for*.
- Biochemical thresholds intentionally not fixed.
- Ethnicity-specific hirsutism thresholds not encoded.
- Not reviewed by a clinical domain expert.

Put these in the README. The challenge brief penalizes hidden assumptions and
unsupported claims; it does not penalize honest scoping.
