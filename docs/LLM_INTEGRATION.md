# LLM Integration — PCOS Harmonizer

Companion to `IMPLEMENTATION_NOTES.md`, `llm_column_profile.schema.json`, and
`llm_mapping_response.schema.json`. Covers the column-mapping LLM call
specifically: what goes in the prompt, what comes back, and how to validate it.
Everything else about the pipeline — conversion, missingness, the mapping file,
coverage reporting — lives in `IMPLEMENTATION_NOTES.md`.

---

## What goes where

| Artifact | Destination |
|---|---|
| Field catalog, generated from the schema | System prompt |
| Instructions below | System prompt, as prose |
| `llm_column_profile.schema.json` output | User message |
| `llm_mapping_response.schema.json` | Structured-output / response-format parameter |

The response schema is 1:1 with the expected response object — no annotations,
no instructions. Most structured-output endpoints reject unknown keywords, so
nothing extra belongs in that file.

## Generating the field catalog

The catalog is derived from `pcos_schema_v0.1.json` at runtime, not stored as a
file — a checked-in copy is a place for the two to drift apart.

Per field, project out: `x_id` → `id`, the field name, type, `x_unit` → `unit`,
`x_group` → `group`, `x_range` → `range`, `x_conversions` keys →
`accepted_units`, `x_hints` → `hints`, `x_note` → `note`, and enum values where
present. **Every field is included** — there are no unmappable fields.

Two rules:

- **Read `x_id`, never compute it.** Enumerating sorted field names produces
  identical output today and silently renumbers the moment a field is added.
  Fail loudly on a field with no `x_id` rather than falling back.
- **Don't send `x_loinc` or `x_unit_ucum`.** They inflate the prompt and
  contribute nothing to mapping.

99 fields, ~18KB. Fits comfortably in one call.

```python
"""Generate the LLM field catalog from pcos_schema_v0.1.json.

Read fresh at runtime — never checked in — so the catalog can't drift from
the schema. Every field is included; there is no unmappable set.
"""
import json


def enum_values(field_spec):
    """Pull enum values out of a nullable anyOf wrapper, if present."""
    if "enum" in field_spec:
        return field_spec["enum"]
    for branch in field_spec.get("anyOf", []):
        if "enum" in branch:
            return branch["enum"]
    return None


def field_type(field_spec):
    ref = field_spec.get("$ref", "")
    if "nullable_number" in ref:
        return "number"
    if "nullable_integer" in ref:
        return "integer"
    if "nullable_boolean" in ref:
        return "boolean"
    if "nullable_string" in ref:
        return "string"
    if enum_values(field_spec):
        return "enum"
    for branch in field_spec.get("anyOf", []):
        if branch.get("format") == "date":
            return "date"
    return "string"


def build_catalog(schema_path="pcos_schema_v0.1.json"):
    schema = json.load(open(schema_path))
    props = schema["properties"]

    fields = []
    for name, spec in props.items():
        if name.startswith("_"):
            continue
        if "x_id" not in spec:
            raise ValueError(f"{name} has no frozen x_id — assign one before use")

        entry = {"id": spec["x_id"], "field": name, "type": field_type(spec)}

        if spec.get("x_unit"):        entry["unit"] = spec["x_unit"]
        if spec.get("x_group"):       entry["group"] = spec["x_group"]
        if spec.get("x_range"):       entry["range"] = spec["x_range"]
        if spec.get("x_conversions"): entry["accepted_units"] = list(spec["x_conversions"].keys())
        if spec.get("x_hints"):       entry["hints"] = spec["x_hints"]
        if spec.get("x_note"):        entry["note"] = spec["x_note"]

        values = enum_values(spec)
        if values:
            entry["values"] = values

        fields.append(entry)

    ids = [f["id"] for f in fields]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate x_id in schema")

    return {
        "schema_version": schema.get("version", "0.1.0"),
        "field_count": len(fields),
        "missing_codes": [
            "not_measured", "below_lod", "not_applicable", "withheld", "unknown"
        ],
        "fields": fields,
    }
```

## Worked example

**System prompt** — role, the instructions below, and the generated catalog:

```json
{
  "schema_version": "0.1.0",
  "field_count": 99,
  "missing_codes": ["not_measured", "below_lod", "not_applicable", "withheld", "unknown"],
  "fields": [
    { "id": 5, "field": "age_at_menarche", "type": "number",
      "group": "criterion_1_ovulatory", "unit": "years", "range": [6, 25],
      "hints": ["menarche", "RHQ010", "age_first_period"] },
    { "id": 43, "field": "fasting_glucose", "type": "number",
      "group": "metabolic", "unit": "mmol/L", "range": [1, 40],
      "accepted_units": ["mg/dL"],
      "hints": ["glucose", "LBXGLU", "fasting_glucose", "FPG"],
      "note": "Unit disambiguation: values ~4-7 suggest mmol/L; ~70-130 suggest mg/dL." },
    { "id": 59, "field": "hormonal_contraceptive_use", "type": "enum",
      "group": "confounders",
      "values": ["current", "former", "never", "unknown"],
      "hints": ["birth_control", "oral_contraceptive", "OC_use", "RHQ540"],
      "critical": true },
    { "id": 93, "field": "total_testosterone", "type": "number",
      "group": "criterion_2_hyperandrogenism", "unit": "nmol/L", "range": [0, 20],
      "accepted_units": ["ng/dL", "ng/mL"],
      "hints": ["testosterone", "LBXTST", "total_T", "TT"],
      "note": "Unit disambiguation: values ~0.5-3 suggest nmol/L; ~15-90 suggest ng/dL." }
  ]
}
```

**User message** — the column profile, conforming to
`llm_column_profile.schema.json`. Columns from every input file are merged into
one call; ids are assigned across the whole set:

```json
{
  "columns": [
    { "id": 1, "name": "LBXTST", "label": "Testosterone, total (ng/dL)",
      "samples": [18.2, 31.5, 24.0, 8.9, 62.1, 44.3],
      "min": 2.0, "max": 98.4, "n_unique": 412 },

    { "id": 2, "name": "RHQ010", "label": "Age at first menstrual period",
      "samples": [12, 13, 11, 999, 14, 15, 777],
      "min": 8, "max": 21, "n_unique": 15 },

    { "id": 3, "name": "TESTO", "label": null,
      "samples": [1.2, 2.8, 4.1, 3.3, 2.0],
      "min": 1.2, "max": 4.8, "n_unique": 87 },

    { "id": 4, "name": "Do you currently use hormonal birth control?", "label": null,
      "samples": [1, 2, 1, 3, 9, 2],
      "n_unique": 4,
      "value_counts": { "1": 412, "2": 289, "3": 1104, "9": 31 } },

    { "id": 5, "name": "LBXHCT", "label": "Hematocrit (%)",
      "samples": [41.2, 38.9, 44.1, 36.5],
      "min": 24.0, "max": 56.3, "n_unique": 203 }
  ]
}
```

**Response** — conforming to `llm_mapping_response.schema.json`:

```json
{
  "mappings": [
    { "column_id": 1, "field_id": 93, "confidence": 0.98,
      "unit_raw": "ng/dL", "unit_confidence": 1.0, "flags": [] },

    { "column_id": 2, "field_id": 5, "confidence": 0.97,
      "unit_raw": "years", "unit_confidence": 1.0, "flags": [] },

    { "column_id": 3, "field_id": 93, "confidence": 0.84,
      "unit_raw": null, "unit_confidence": 0.35, "flags": ["UNIT_UNKNOWN"] },

    { "column_id": 4, "field_id": 59, "confidence": 0.93, "flags": [] },

    { "column_id": 5, "field_id": null, "confidence": 0.0,
      "unmapped_reason": "out_of_scope", "flags": [] }
  ]
}
```

**What each column demonstrates:**

| Column | Point |
|---|---|
| 1 | Label carries the unit — highest confidence, no inference needed |
| 2 | `777`/`999` are visible in `samples` but excluded from `min`/`max`; classifying them is pass 2's job, not this call's |
| 3 | No label, range 1.2–4.8 sits between plausible nmol/L and ng/mL → `unit_raw: null`, `UNIT_UNKNOWN`, conversion blocked. Mapping confidence stays high: it is clearly testosterone, just unclear in what unit |
| 4 | Question text as the column name; `n_unique: 4` and `value_counts` identify a coded enum. The mapping is proposed here, the code-to-value translation happens in pass 2 |
| 5 | Correctly unmapped — a real measurement with no canonical field |

Note that column 3 has high `confidence` and low `unit_confidence`. A single
score would hide exactly the case that needs a reviewer.

## Instructions for the system prompt

- Return one entry per source column. Never omit a column; unmappable columns
  get `field_id: null` with an `unmapped_reason`.
- Prefer `field_id: null` over a low-confidence guess. Gaps are visible in the
  coverage report; wrong mappings are not.
- Every field in the catalog is mappable. A source column holding a value the
  schema can also compute — a `BMI` or `HOMA-IR` column — maps normally; the
  source value takes precedence over any fallback computation.
- Infer units from value ranges using the `range` and `note` fields in the
  catalog. Report the unit; never convert values.
- If a unit cannot be determined, set `unit_raw: null` and flag `UNIT_UNKNOWN`.
  Never guess a unit.
- This pass maps columns to fields only. Do not map data values to enum values
  and do not classify sentinel codes — both are handled in a separate pass.


## Value mapping is a second pass

Column mapping and value mapping are different problems and should not share a
call. Columns go in one batch over the whole dataset; values need the distinct
values and frequencies of a *single* enum column, which you only know after
pass 1 has identified it as an enum.

```
Pass 1: columns -> fields          (all columns, one call)
        | filter to enum-typed fields
Pass 2: source values -> enum values  (per column, small calls)
```

Pass 2 also covers sentinel classification (`7`, `9`, `777`, `999` -> missing
codes). For booleans it is often deterministic — try a lookup table (`1`/`2`,
`Y`/`N`, `yes`/`no`) before spending an LLM call.

Not specified in v0.1; `value_counts` in the column profile is the input signal
that tells pass 1 which columns will need it.

## Validation after the response

Run these in code; the model never sees them.

**Reject:**
- any `column_id` not present in the input profile
- any input column missing from the response
- duplicate `column_id` entries
- any `field_id` not present in the catalog

**Warn:**
- two columns mapping to the same `field_id` — expected with merged multi-file
  input (glucose appears in two NHANES files); surface the conflict for review
  rather than silently picking one

**Always:**
- set `human_reviewed: false` on every entry regardless of confidence
- fill unmapped canonical fields with `not_measured` downstream; the response is
  not required to enumerate them

## Profiling source columns

What the profiler emits is defined by `llm_column_profile.schema.json`. How to
fill it well:

- **All files are profiled and merged into one call.** Assign column ids across
  the whole set, not per file, and keep a backend `map[filename][columnname] ->
  id` to resolve the response.
- **Sample across the distribution, not the head.** Head-only samples miss
  sentinels and understate range.
- **Compute min/max after excluding suspected sentinels,** but keep the
  sentinels in `samples`. The model needs the clean range for unit inference and
  the raw oddities for sentinel detection.
- **Include `value_counts` whenever `n_unique <= 20`.** It's the difference
  between the model guessing at an enum and reading it off.
- **Extract `label` wherever the format carries one.** XPT files have variable
  labels; CSVs usually don't. A label like `"Testosterone, total (ng/dL)"`
  resolves both field and unit in one step.
- **Exclude the join key and identifier columns** before sending.

## Prompt content

Give the proposer, per canonical field: name, canonical unit, type, `x_range`,
`x_hints`, and any disambiguation note. Compact JSON, not prose.

Per source column: name, up to 10 sample values, min/max, n_unique, the codebook
label where the format carries one, and value_counts for low-cardinality
columns.

**Require structured output.** Reject and retry on parse failure rather than
repairing by hand.

**Batch by group, not all 99 fields at once,** if precision disappoints. Send
the metabolic fields with the metabolic-looking columns. Try the full catalog
first — at roughly 17KB it fits comfortably.
