# Field Value Mappings — PCOS Harmonizer

Companion to `LLM_INTEGRATION.md`, `llm_value_profile.schema.json`, and
`llm_value_mapping_response.schema.json`. Covers pass 2: mapping the *values*
inside a column, once pass 1 has already mapped the *column* to a canonical
field. Column mapping lives in `LLM_INTEGRATION.md`; this file does not repeat
it.

---

## Why this is a separate pass

Pass 1 answers "which canonical field does this column correspond to?" — one
call, all columns, using the field catalog. It has no reason to see individual
data values.

Pass 2 answers "what does `1` mean in this column?" — and that question only
makes sense once pass 1 has told you the column is
`hormonal_contraceptive_use`, so you know the target vocabulary is `current`,
`former`, `never`, `unknown` and not some other field's enum entirely.

```
Pass 1: columns -> fields              (all columns, one call)
        │ filter to fields with an enum type in the catalog
        ▼
Pass 2: source values -> option id     (one call per column)
```

## One call per column

Unlike pass 1, pass 2 is **scoped to a single column per call.** Each call
already carries the exact target vocabulary for that one field — there's no
reason to send 99 fields' worth of catalog again, and no ambiguity about which
field a value belongs to.

This has a real consequence for the contract: **no column identifier is
needed anywhere in the request or response.** The caller made the call because
it already knows which column it's asking about; it attaches that context
after the response comes back, not before.

## When pass 2 runs

A column needs pass 2 when pass 1 mapped it to a field whose catalog entry has
`"type": "enum"`. Practically: after pass 1, look up each mapped `field_id` in
the catalog and check its type.

**Try a lookup table before spending a call.** Many enum columns are
deterministic — `1`/`2` → true/false, `Y`/`N`, `yes`/`no`, or a column whose
distinct values are already exactly the catalog's enum strings. Reserve the LLM
call for columns where the source uses its own coding.

## Sentinels are a value-mapping problem, not a column-mapping problem

`hormonal_contraceptive_use` might have codes `1`, `2`, `3` for the real
categories and `7`, `9` for refused/don't-know. Both live in the same column,
and only pass 2 — with the value distribution in hand — can tell them apart.

The distinguishing signal is usually frequency: sentinel codes are rare
relative to the real categories. That's why `count` is the important field in
the value profile — a `9` at 2% among 1s and 2s at 40% each is legible as a
sentinel from the shape alone, before the model reasons about meaning at all.

---

## Contracts

| Artifact | Role |
|---|---|
| `llm_value_profile.schema.json` | Input — one column's options and observed values |
| `llm_value_mapping_response.schema.json` | Output — value → option id |

Same design decisions as pass 1: ids over strings for anything in a closed
vocabulary, `null` preferred over a low-confidence guess, flat response array,
conditional requirements enforced by the schema.

### Numbered options, not a string result

The model never generates the string `"current"` or `"unknown"`. It's given a
flat, explicitly numbered list — the field's own enum values, followed by the
five missing codes — and returns an id from that list. This mirrors why pass 1
returns `field_id` rather than a field name: an id can only be valid or
invalid, never a plausible-looking near miss.

The options list is built fresh for every call, concatenating the target
field's enum values with the fixed missing-code vocabulary:

```python
MISSING_CODES = ["not_measured", "below_lod", "not_applicable", "withheld", "unknown"]

def build_options(field_enum_values):
    """field_enum_values: the target field's own allowed values, e.g.
    ["current", "former", "never", "unknown"] for hormonal_contraceptive_use."""
    options = [
        {"id": i + 1, "label": v}
        for i, v in enumerate(field_enum_values)
    ]
    base = len(field_enum_values)
    options += [
        {"id": base + i + 1, "label": f"{v} (missing/sentinel code, not a real answer)"}
        for i, v in enumerate(MISSING_CODES)
    ]
    return options
```

**Watch for label collisions.** Several fields have their own enum value
literally named `unknown` (meaning "the person answered, and the answer was
'I don't know'") which is a different thing from the missing code `unknown`
(meaning "we have no interpretable answer at all"). Left unqualified, both
options would show the label `unknown` and the model would have no way to
choose between them. The `(missing/sentinel code, not a real answer)` suffix
on every missing-code option exists specifically to prevent this — apply it
unconditionally, not just when a collision is detected, since a fix that only
fires on known collisions will miss the next one.

The stored result is unaffected by the label text: once `target_id` resolves
back to `not_measured` or the field's own `unknown`, the label suffix is
discarded — it only ever existed to disambiguate the prompt.

### Input

```json
{
  "field_id": 59,
  "options": [
    { "id": 1, "label": "current" },
    { "id": 2, "label": "former" },
    { "id": 3, "label": "never" },
    { "id": 4, "label": "unknown" },
    { "id": 5, "label": "not_measured (missing/sentinel code, not a real answer)" },
    { "id": 6, "label": "below_lod (missing/sentinel code, not a real answer)" },
    { "id": 7, "label": "not_applicable (missing/sentinel code, not a real answer)" },
    { "id": 8, "label": "withheld (missing/sentinel code, not a real answer)" },
    { "id": 9, "label": "unknown (missing/sentinel code, not a real answer)" }
  ],
  "values": [
    { "raw": "1", "count": 412 },
    { "raw": "2", "count": 289 },
    { "raw": "3", "count": 1104 },
    { "raw": "9", "count": 31 }
  ]
}
```

`field_id` (here `59`, `hormonal_contraceptive_use` in the current schema) is
carried for logging and audit — the model maps against `options`, not
`field_id` directly. `raw` identifies each observed value; distinct values
within one already-identified column don't collide, so no separate id is
needed for them.

### Output

```json
{
  "mappings": [
    { "raw": "1", "target_id": 1, "confidence": 0.95, "flags": [] },
    { "raw": "2", "target_id": 2, "confidence": 0.94, "flags": [] },
    { "raw": "3", "target_id": 3, "confidence": 0.94, "flags": [] },
    { "raw": "9", "target_id": 8, "confidence": 0.85,
      "flags": ["LOW_FREQUENCY_UNCLASSIFIED"] }
  ]
}
```

`raw: "9"` (31 occurrences against 412/289/1104 for the real categories)
resolves to `target_id: 8`, which is `withheld` — correctly classified as a
missing code rather than a fourth category. This is the sentinel-detection
case the whole pass exists for.

### Conditional rule, enforced by the schema

`target_id: null` requires `unmapped_reason`. One `allOf`/`if`/`then` block in
`llm_value_mapping_response.schema.json`.

---

## Assembling the call

**Pass 2 does not reuse the pass-1 system prompt.** Pass 1's prompt carries the
full 99-field catalog (~18KB) so the model can choose a field. Pass 2 chooses
from the ~9 options in its own request — the catalog is irrelevant, and sending
it would cost tokens on every enum column for no benefit. This prompt is
self-contained.

```python
import json

VALUE_MAPPING_SYSTEM_PROMPT = """You are a data-mapping assistant for a PCOS research
harmonization tool.

A column from a research dataset has already been matched to a field in the
canonical schema. Your job is now narrower: for each distinct value observed
in that column, choose which of the provided numbered options it corresponds
to.

You will receive:
- options: a numbered list of valid targets for this column. Each has an id
  and a label.
- values: the distinct values found in the column, each with how often it
  occurs, most frequent first.

Rules:
- Return exactly one entry per value given to you. Never omit a value and
  never invent one.
- Match each value to the id of the option whose label best describes it.
  Return the id only - never the label text.
- Options labeled "(missing/sentinel code, not a real answer)" represent
  refused, don't-know, not-applicable, or otherwise uninterpretable
  responses, rather than real categories. Datasets commonly encode these as
  out-of-range numbers such as 7, 9, 77, 99, 777, or 999.
- Use frequency as evidence. A value that is rare relative to the column's
  other values is more likely a sentinel than a genuine category, especially
  in a column with only two to four real categories. A value that is common
  is unlikely to be a sentinel.
- Judge only from the values and counts shown. Do not assume a coding
  convention from a dataset you were not shown.
- If a value cannot be confidently matched to any option, set target_id to
  null and give an unmapped_reason. A gap is reviewable; a wrong mapping is
  not, and silently corrupts every downstream analysis of this column.

Respond only with JSON conforming to the provided response schema. Do not
include commentary, explanations, or markdown formatting outside the JSON."""


def build_value_mapping_call(field_id, field_enum_values, observed_values):
    """Returns (system_prompt, user_message) for one enum column."""
    options = build_options(field_enum_values)
    user_message = json.dumps({
        "field_id": field_id,
        "options": options,
        "values": observed_values,
    })
    return VALUE_MAPPING_SYSTEM_PROMPT, user_message
```

The three pieces of the API call:

```python
system_prompt, user_message = build_value_mapping_call(
    field_id, field_enum_values, observed_values
)
response_format = json.load(open("llm_value_mapping_response.schema.json"))
```

At ~2KB of instructions plus a handful of options and values, each pass-2 call
is roughly a tenth the size of the single pass-1 call — which matters, since
there's one of these per enum column rather than one per dataset.

## Resolving the response

`target_id` is only meaningful relative to the exact `options` list sent for
that call — resolve it immediately, don't store the bare integer.

```python
def resolve_mappings(mappings, options):
    """Returns {raw: canonical_value} where canonical_value is either the
    field's own enum string or one of the five missing codes."""
    by_id = {o["id"]: o["label"] for o in options}
    resolved = {}
    for m in mappings:
        if m["target_id"] is None:
            resolved[m["raw"]] = None
            continue
        label = by_id[m["target_id"]]
        # strip the disambiguation suffix added for missing-code options
        canonical = label.split(" (missing/sentinel code")[0]
        resolved[m["raw"]] = canonical
    return resolved
```

The result of `resolve_mappings` is what goes into the mapping file's
`value_map` for that column (see `IMPLEMENTATION_NOTES.md` §6) — a plain
`{raw: canonical_value}` dict, with no ids left in it. Ids exist for the LLM
call only; nothing downstream should need to know option 8 meant `withheld`.

---

## Validation after the response

**Reject:**
- any `raw` from the input missing from the response
- duplicate `raw` entries
- a `target_id` not present in the `options` list that was sent

**Warn:**
- two distinct `raw` values mapping to the same `target_id` — not necessarily
  wrong (e.g. `"Y"` and `"1"` both meaning `current`), but worth a reviewer's
  eyes
- a missing-code `target_id` chosen for a value with a *high* count —
  sentinels are supposed to be rare; a common value classified as missing may
  indicate the wrong direction

**Always:**
- resolve `target_id` back to a string immediately and discard the id — see
  `resolve_mappings` above
- carry the resolved `{raw: canonical_value}` map into the mapping file as
  `value_map` for that column
- keep `human_reviewed: false` on every value mapping by default, same as
  column mappings

---

## What this pass does not do

- **No new fields.** Pass 2 only refines values within a column pass 1 already
  mapped. It cannot map a column to a field or unmap one.
- **No unit conversion.** Enum values have no units.
- **No cross-column consistency check.** If two different columns both claim
  to represent contraceptive use with different codings, pass 2 resolves each
  independently. Reconciling them is a reviewer's job.