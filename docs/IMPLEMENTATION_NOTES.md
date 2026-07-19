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
[6] fallback ──────── deterministic: compute fields per x_fallback (spec §7)
    │                 where no source column mapped
    ▼
[7] validate ──────── run x_validator_rules, emit warnings
    │
    ▼
[8] report ────────── coverage report + standardized output
```

Notes on individual steps:

- **[1]** Sample values (5–10) should exclude `NaN` where possible, but not
  sentinel-looking outliers — those are exactly what unit and sentinel
  detection need. See §3 and §5.
- **[4]** Split the review UI by schema group (identity, criterion 1/2/3,
  metabolic, ...) rather than one flat list — matches the schema's own
  structure and lets a reviewer focus on one criterion at a time.
- **[4]** Surface low-confidence mappings first; a reviewer's time is better
  spent there than re-confirming obvious ones.
- **[4]** High-confidence mappings should stay reviewable, just not forced into
  view by default. Auto-surfacing everything defeats the point of triaging by
  confidence.
- **[5]** Unit coverage will not be complete. Where `unit_raw` has no known
  conversion, prompt the reviewer for a manual factor (`unit_raw` →
  `unit_canonical`) rather than blocking silently or guessing. Record it in
  `transformation_applied` like any other conversion.

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

> `free_androgen_index` and `homa_ir` are **computed fallbacks**, not conversions. See §4.

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

### Field ids are frozen — read them, never compute them

Each field in `pcos_schema_v0.1.json` carries `x_id`. Build the catalog by
reading these, never by enumerating sorted field names. Sort-order ids look
identical today and silently renumber the moment a field is added — `x_id: 44`
becomes a different field, and every stored mapping file now resolves to the
wrong column.

Rules:

- Adding a field: take `x_field_ids.next_available_id`, then increment it.
  Alphabetical position is irrelevant.
- Removing a field: append the id to `x_field_ids.retired_ids`. Never reuse it.
- Renaming a field: keep the id. The id identifies the concept, the name is a
  label.
- Catalog generation must fail loudly on a field with no `x_id` rather than
  falling back to a computed one.

Store `schema_version` in every mapping file. When resolving a mapping file
written against an older version, check for retired ids before assuming a
mapping is valid.

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

**Source-specific overrides beat inference.** These are applied in your backend
before and after the LLM call — the model is never told which dataset it is
looking at. Ship a small file:

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

## 4. Computed fallbacks

Every field is populated from a source column where one exists. Seven fields may
be computed from other canonical fields when the source has none. Both routes
produce the same field.

**Fallback is not conversion.** Conversion rescales a value that *was* present
(§2). A fallback computes a value that was *absent*. A dataset reporting
testosterone in ng/dL needs a conversion; a dataset reporting testosterone and
SHBG but no FAI permits a fallback.

### Precedence

A source-supplied value always wins. Compute only when nothing mapped to the
field. Where a source supplies both `bmi` and its components, keep the source
value, compute the fallback anyway, and record it in `transformation_applied`
for comparison — disagreement beyond rounding tolerance emits a warning. That's
a free data-quality check worth surfacing in the demo.

Set `value_source` on every populated field: `source` or `computed`. It is
required in the provenance record.

### Ordering

```
1. unit conversion (all mapped fields)
2. fallbacks, in dependency order
```

`free_androgen_index` depends on converted testosterone and SHBG; `homa_ir` on
converted glucose and insulin. Convert everything first, then compute.

### Fallbacks are machine-readable

`x_fallback` is a declarative spec, not prose. One generic evaluator handles all
seven — no per-field code, and adding a fallback later requires no code change.

```json
"homa_ir": {
  "x_fallback": {
    "op": "expression",
    "inputs": [
      { "field": "fasting_glucose",  "unit": "mmol/L" },
      { "field": "fasting_insulin",  "unit": "u[IU]/mL" }
    ],
    "expression": "fasting_glucose * fasting_insulin / 22.5",
    "output_unit": "{ratio}",
    "guards": [ { "field": "fasting_status", "condition": "eq", "value": "fasting" } ],
    "source": "Matthews DR et al., Diabetologia 1985;28:412-419"
  }
}
```

**Contract** (`x_fallback_spec` in the schema):

| Key | Meaning |
|---|---|
| `op` | `expression`, `max`, or `min` |
| `inputs` | Canonical field plus the unit the expression assumes. **Not always the field's canonical unit** — `homa_ir` needs insulin in µIU/mL, not the canonical pmol/L. Convert before binding. |
| `expression` | Arithmetic only: `+ - * / **` and parentheses. Field names bind to values. No function calls. |
| `guards` | All must pass or the field is not computed. `gt`, `gte`, `lt`, `lte`, `eq`, `ne`. |
| `warnings` | Emitted with the value; do not block. |
| `output_unit` | UCUM code of the result. Equals the field's `x_unit_ucum` — assert this in tests. |

**Every input must be present.** A missing input yields `not_measured`, never a
partial result. This matters for `max`: a per-ovary maximum computed from one
observed ovary is not the same quantity, since the unobserved side may be larger.

### Reference evaluator

```python
import ast, operator

OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
       ast.Div: operator.truediv, ast.Pow: operator.pow, ast.USub: operator.neg}
CMP = {"gt": operator.gt, "gte": operator.ge, "lt": operator.lt,
       "lte": operator.le, "eq": operator.eq, "ne": operator.ne}

def _eval(node, env):
    if isinstance(node, ast.Expression): return _eval(node.body, env)
    if isinstance(node, ast.Constant):   return node.value
    if isinstance(node, ast.Name):       return env[node.id]
    if isinstance(node, ast.BinOp):
        return OPS[type(node.op)](_eval(node.left, env), _eval(node.right, env))
    if isinstance(node, ast.UnaryOp):    return OPS[type(node.op)](_eval(node.operand, env))
    raise ValueError(f"disallowed node: {type(node).__name__}")

def compute_fallback(fb, row):
    """row maps canonical field -> value, already converted to each input's unit."""
    names = [i["field"] for i in fb["inputs"]]
    if any(row.get(n) is None for n in names):
        return None, ["missing_input"]

    for g in fb.get("guards", []):
        v = row.get(g["field"])
        if v is None or not CMP[g["condition"]](v, g["value"]):
            return None, [f"guard_failed:{g['field']}"]

    warnings = [w["message"] for w in fb.get("warnings", [])
                if row.get(w["field"]) is not None
                and CMP[w["condition"]](row[w["field"]], w["value"])]

    env = {n: row[n] for n in names}
    if fb["op"] == "expression":
        value = _eval(ast.parse(fb["expression"], mode="eval"), env)
    elif fb["op"] == "max":
        value = max(env.values())
    elif fb["op"] == "min":
        value = min(env.values())
    else:
        raise ValueError(f"unknown op: {fb['op']}")

    return value, warnings
```

Use `ast` with an operator allowlist, never `eval()`. The expressions come from
a file that could be edited.

**Test to write:** assert every `output_unit` equals the field's `x_unit_ucum`.
Catches drift between the two in one line.

### What not to compute

**No diagnostic algorithm.** Criteria evaluation, phenotype assignment, and case
definition are interpretations of published guidelines — thresholds, suppression
conditions, and 2-of-3 logic all involve judgement that differs between research
groups. The schema deliberately encodes none of it.

If your tool computes an assessment, that is the tool's output. Do not write it
back into `pcos_diagnosis_flag`, `phenotype`, or `criteria_met` — those record
what a source reported, and overwriting them destroys the distinction between
observation and inference.

### Terminology fields

The schema carries `x_unit_ucum` (UCUM code) alongside the human-readable
`x_unit`, and `x_loinc` on laboratory and measurement fields.

- **Use `x_unit_ucum` for machine processing.** `pint` accepts UCUM directly.
  `x_unit` is for display and documentation.
- **`x_loinc` is metadata, not a mapping key.** Emit it in output so downstream
  consumers can join against clinical systems. Do not use it to drive column
  mapping — source datasets rarely carry LOINC codes, and where they do, they
  should be treated as a high-confidence hint rather than an override.
- **Codes marked `x_loinc_verified: false` are provisional.** Confirm against
  the LOINC database before publishing. Currently: `androstenedione`,
  `free_t4`, `waist_circumference_cm`, `ogtt_2hr_glucose`.
- **LOINC distinguishes mass-based from molar-based measurements.** The codes
  listed name the analyte; the canonical unit in `x_unit` governs. A source
  reporting testosterone in ng/dL may legitimately carry a different LOINC code
  than the one in the schema even though the analyte matches — do not treat a
  code mismatch as a mapping failure.

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

## 9. LLM integration

The column-mapping LLM call — prompt construction, catalog generation, the
worked input/output example, and response validation — is covered in
`LLM_INTEGRATION.md`, not here. It's a self-contained subsystem with its own
input and output contracts (`llm_column_profile.schema.json`,
`llm_mapping_response.schema.json`).

---


## 10. Build order

Parallelize; nobody waits for the spec to be final.

| Priority | Component | Owner | Notes |
|---|---|---|---|
| P0 | JSON Schema loader + field registry | data eng | Everything depends on it |
| P0 | Unit converter (pint + molar + specials) | data eng | Test against `x_conversions` |
| P0 | Mapping file read/write | data eng | Format is the contract |
| P0 | LLM proposer | CS/ML | Structured output, retry on parse fail |
| P0 | Transform executor | data eng | Mapping file in, standardized table out |
| P1 | Coverage report | bioeng | The money output |
| P1 | Validator rules | bioeng | 19 rules in `x_validator_rules` |
| P1 | NHANES source override file | bioeng | Makes the demo work |
| P2 | Computed fallbacks | CS/ML | bmi, FAI, HOMA-IR — see §4 |
| P2 | Minimal web UI | PM/CS | Upload → review → download |
| P3 | Value-mapping pass | CS/ML | Enum codes → canonical values; see `LLM_INTEGRATION.md` |

### Which fields to wire first

The schema is comprehensive by design — it covers what a researcher might
plausibly have, not what any one dataset does. That means implementation
priority is a separate question from schema membership, and it lives here rather
than in the schema.

Wire in this order:

1. **identity, criterion_1, criterion_2, criterion_3, exclusions, diagnosis** —
   the Rotterdam evidence fields. Without these the coverage report has nothing
   to say. Note this schema stores what a source reports for each criterion; it
   does not evaluate or diagnose (spec §7.2).
2. **demographics, confounders, metabolic, sample_context** — needed to
   interpret the above, and heavily populated in NHANES.
3. **gonadotropins** — small, cheap.
4. **fertility, mental_health** — real fields, but no demo source populates
   them. Mapping works without special handling; skip only the validation and
   coverage-report wiring if time is short.

Nothing in this list is optional at the schema level. A field with no
implementation still maps correctly — it just doesn't get a validator rule or a
coverage line.

**Cut line:** if the tool is broken and time is short, ship the spec, the JSON
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
