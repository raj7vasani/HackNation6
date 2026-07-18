# PCOS Canonical Schema — v0.1

An open schema for harmonizing PCOS research datasets.

**Status:** Draft, hackathon release. Not clinically validated. Field definitions
follow the Rotterdam 2003 criteria and the 2023 International Evidence-Based
Guideline for PCOS, but no domain expert has formally reviewed this version.

**Companion documents.** `pcos_schema_v0.1.json` is the machine-readable
schema and the authoritative source for field names, types, ranges, and
validation rules. `IMPLEMENTATION_NOTES.md` covers building a tool that
produces conforming data — pipeline design, unit conversion, LLM prompting,
source-specific handling. This document defines the schema itself and is
intended for researchers using or extending it.

---

## 1. Scope

**In scope (v0.1):** cross-sectional, one-row-per-subject clinical and laboratory
data. Demographics, anthropometrics, reproductive history, androgens, ovarian
morphology, gonadotropins, exclusion workup, metabolic panel, diagnosis labels.

**Out of scope (v0.1):** longitudinal / time-series data (wearables, CGM, daily
symptom logs, cycle event streams). See §8.

---

## 2. Design principles

1. **Organized around Rotterdam.** Diagnosis requires 2 of 3: ovulatory
   dysfunction, hyperandrogenism, polycystic ovarian morphology — after
   excluding other causes. The schema mirrors that structure so coverage can be
   reported per criterion.
2. **Raw evidence and derived flags are both stored.** Some datasets give cycle
   counts; others give a clinician's `oligomenorrhea: yes`. Keep both and record
   which was available via `*_evidence_level`.
3. **Canonical units, but raw values preserved.** Every measurement carries
   `value_raw` + `unit_raw` alongside `value_canonical` + `unit_canonical`.
   No transformation is lossy or unaudited.
4. **Assay method is not optional metadata.** Immunoassay and LC-MS/MS
   testosterone are not comparable at female concentrations. Pooling without
   this field produces confidently wrong results.
5. **Thresholds change; store what was applied.** PCOM follicle-count cut-points
   moved from ≥12 to ≥20 per ovary as ultrasound resolution improved. A bare
   boolean from 2008 does not mean the same thing as one from 2023.
6. **Missingness is typed, never blank.** See §6.
7. **Every mapped value is traceable to its source column.** See §5.

---

## 3. Field definitions

Units listed are canonical. Conversion factors are from common source units.

### 3.1 Identity & demographics

| Field | Unit | Type | Derived | Notes |
|---|---|---|---|---|
| `subject_id` | — | string |  | **Required.** Unique within `source_dataset`. |
| `source_dataset` | — | string |  | **Required.** Dataset identifier. |
| `age_years` | years | float |  | |
| `race_ethnicity` | — | string |  | Preserve source label verbatim; do not recode. |
| `height_cm` | cm | float |  | from in × 2.54 |
| `weight_kg` | kg | float |  | from lb × 0.4536 |
| `bmi` | kg/m² | float | ✓ | Derived: `weight_kg` / (`height_cm`/100)² |
| `waist_circumference_cm` | cm | float |  | |
| `hip_circumference_cm` | cm | float |  | |
| `waist_hip_ratio` | ratio | float | ✓ | Derived: `waist_circumference_cm` / `hip_circumference_cm` |

### 3.2 Confounders

Fields that invalidate or distort other measurements. Absence of these should be
flagged loudly in the coverage report.

| Field | Unit | Type | Derived | Notes |
|---|---|---|---|---|
| `hormonal_contraceptive_use` | — | enum: `current`, `former`, `never`, `unknown` |  | **Highest-priority confounder.** Suppresses androgens, imposes artificial cycles. |
| `contraceptive_type` | — | enum: `combined_oral`, `progestin_only_oral`, `hormonal_iud`, `copper_iud`, `implant`, `injectable`, `patch`, `ring`, `other_hormonal`, `non_hormonal`, `none`, `unknown` |  | Suppression magnitude differs by type. Combined oral contraceptives raise SHBG and suppress androgens most strongly; copper IUD and non-hormonal methods do not. Preserve the source label in `value_raw`. |
| `contraceptive_washout_days` | days | int |  | Days since discontinuation. |
| `pregnancy_status` | — | enum: `pregnant`, `not_pregnant`, `postpartum`, `unknown` |  | Invalidates most hormonal and cycle fields. |
| `breastfeeding_flag` | — | bool |  | Suppresses ovulation. |
| `menopausal_status` | — | enum: `pre`, `peri`, `post`, `unknown` |  | |
| `age_at_last_menstrual_period` | years | float |  | |
| `hysterectomy_flag` | — | bool |  | Cycle fields become undefined. |
| `oophorectomy_flag` | — | bool |  | Bilateral removal. Androgen/morphology fields undefined. |
| `age_at_oophorectomy` | years | float |  | |
| `metformin_use` | — | bool |  | Alters metabolic panel. |
| `antiandrogen_use` | — | bool |  | e.g. spironolactone. Suppresses clinical + biochemical androgen signals. |
| `ovulation_induction_use` | — | bool |  | e.g. letrozole, clomiphene. |

### 3.3 Criterion 1 — ovulatory dysfunction

| Field | Unit | Type | Derived | Notes |
|---|---|---|---|---|
| `age_at_menarche` | years | float |  | |
| `cycle_length_days_typical` | days | float |  | |
| `cycle_length_variability_days` | days | float |  | SD or range; record which in `transformation_applied`. |
| `cycles_per_year` | count | float |  | |
| `oligomenorrhea_flag` | — | bool |  | Conventionally >35 d cycles or <8 cycles/yr. |
| `amenorrhea_flag` | — | bool |  | No menses ≥3 months (or ≥12 months in some instruments). |
| `irregular_cycles_self_report` | — | bool |  | |
| `progesterone_luteal` | nmol/L | float |  | Biochemical ovulation confirmation. from ng/mL × 3.18 |
| `ovulatory_dysfunction_derived` | — | bool | ✓ | Derived: clinical logic — see §7 |
| `ovulatory_evidence_level` | — | enum: `measured`, `clinician`, `self_report`, `unknown` |  | |

> **Adolescent caveat.** Irregular cycles are physiologically normal in the years
> following menarche. Subjects within ~2–3 years of menarche should not have
> ovulatory dysfunction inferred from cycle irregularity alone.

### 3.4 Criterion 2 — hyperandrogenism

**Biochemical**

| Field | Unit | Type | Derived | Notes |
|---|---|---|---|---|
| `total_testosterone` | nmol/L | float |  | from ng/dL × 0.0347 |
| `free_testosterone` | pmol/L | float |  | from pg/mL × 3.47 |
| `shbg` | nmol/L | float |  | |
| `free_androgen_index` | ratio | float | ✓ | Derived: 100 × `total_testosterone` / `shbg` (both nmol/L) |
| `dheas` | µmol/L | float |  | from µg/dL × 0.02714 |
| `androstenedione` | nmol/L | float |  | from ng/dL × 0.0349 |
| `androgen_assay_method` | — | enum: `immunoassay`, `lcmsms`, `unknown` |  | **Critical.** Not comparable across methods at female concentrations. |
| `sample_time_of_day` | — | enum: `morning`, `afternoon`, `unknown` |  | Androgens show diurnal variation. |

**Clinical**

| Field | Unit | Type | Derived | Notes |
|---|---|---|---|---|
| `hirsutism_score_mfg` | 0–36 | int |  | Modified Ferriman-Gallwey. |
| `hirsutism_flag` | — | bool |  | Threshold varies by ethnicity; record in `transformation_applied`. |
| `acne_flag` | — | bool |  | |
| `androgenic_alopecia_flag` | — | bool |  | |
| `clinical_androgen_assessment` | — | enum: `clinician`, `self_report`, `unknown` |  | |

**Derived**

| Field | Unit | Type | Derived | Notes |
|---|---|---|---|---|
| `hyperandrogenism_derived` | — | bool | ✓ | Derived: clinical logic — see §7 |
| `hyperandrogenism_basis` | — | enum: `biochemical`, `clinical`, `both`, `none` |  | |

### 3.5 Criterion 3 — polycystic ovarian morphology

| Field | Unit | Type | Derived | Notes |
|---|---|---|---|---|
| `antral_follicle_count_left` | count | int |  | |
| `antral_follicle_count_right` | count | int |  | |
| `antral_follicle_count_max` | count | int | ✓ | Per-ovary maximum — this is the criterion value. Derived: max(`antral_follicle_count_left`, `antral_follicle_count_right`) |
| `ovarian_volume_left_ml` | mL | float |  | |
| `ovarian_volume_right_ml` | mL | float |  | |
| `ovarian_volume_max_ml` | mL | float | ✓ | Criterion conventionally >10 mL. Derived: max(`ovarian_volume_left_ml`, `ovarian_volume_right_ml`) |
| `ultrasound_route` | — | enum: `transvaginal`, `transabdominal`, `unknown` |  | Resolution differs materially. |
| `amh` | pmol/L | float |  | from ng/mL × 7.14. May substitute for ultrasound in adults (2023 guideline). |
| `pcom_flag` | — | bool | ✓ | Derived: clinical logic — see §7 |
| `pcom_threshold_applied` | — | string |  | e.g. `AFC>=12`, `AFC>=20`, `volume>10ml`. **Required whenever `pcom_flag` is present.** |
| `pcom_basis` | — | enum: `ultrasound`, `amh`, `unknown` |  | |

> **Adolescent caveat.** PCOM is not a valid criterion within ~8 years of
> menarche — multifollicular ovaries are developmentally normal. Validator
> should flag any subject under ~20 where `pcom_flag` contributes to diagnosis.

### 3.6 Gonadotropins

Supporting, not diagnostic under Rotterdam.

| Field | Unit | Type | Derived | Notes |
|---|---|---|---|---|
| `lh` | IU/L | float |  | |
| `fsh` | IU/L | float |  | |
| `lh_fsh_ratio` | ratio | float | ✓ | Historically used, no longer criterion. Derived: `lh` / `fsh` |
| `estradiol` | pmol/L | float |  | from pg/mL × 3.671 |

### 3.7 Exclusions

PCOS is a diagnosis of exclusion. Without `exclusions_assessed_flag`, a positive
label cannot be distinguished from an unworked-up PCOS-like presentation.

| Field | Unit | Type | Derived | Notes |
|---|---|---|---|---|
| `tsh` | mIU/L | float |  | Thyroid dysfunction. |
| `free_t4` | pmol/L | float |  | |
| `prolactin` | mIU/L | float |  | from ng/mL × 21.2. Hyperprolactinemia. |
| `17_hydroxyprogesterone` | nmol/L | float |  | Non-classic congenital adrenal hyperplasia. |
| `cortisol` | nmol/L | float |  | Cushing's syndrome screening. |
| `exclusions_assessed_flag` | — | bool |  | Whether any exclusion workup was performed. |
| `exclusion_condition_present` | — | string |  | Named condition if identified. |

### 3.8 Metabolic

Not diagnostic, but the dominant PCOS research question.

| Field | Unit | Type | Derived | Notes |
|---|---|---|---|---|
| `fasting_glucose` | mmol/L | float |  | from mg/dL × 0.0555 |
| `fasting_insulin` | pmol/L | float |  | from µIU/mL × 6.945 |
| `homa_ir` | ratio | float | ✓ | Derived: `fasting_glucose`(mmol/L) × `fasting_insulin`(µIU/mL) / 22.5 |
| `ogtt_2hr_glucose` | mmol/L | float |  | from mg/dL × 0.0555 |
| `hba1c_percent` | % (NGSP) | float |  | Note IFCC mmol/mol variant: NGSP% = (IFCC × 0.0915) + 2.15 |
| `total_cholesterol` | mmol/L | float |  | from mg/dL × 0.0259 |
| `hdl_cholesterol` | mmol/L | float |  | from mg/dL × 0.0259 |
| `ldl_cholesterol` | mmol/L | float |  | from mg/dL × 0.0259 |
| `triglycerides` | mmol/L | float |  | from mg/dL × 0.0113 |
| `systolic_bp` | mmHg | int |  | |
| `diastolic_bp` | mmHg | int |  | |
| `acanthosis_nigricans_flag` | — | bool |  | |

### 3.9 Fertility & family history

| Field | Unit | Type | Derived | Notes |
|---|---|---|---|---|
| `gravidity` | count | int |  | Total pregnancies. |
| `parity` | count | int |  | Total deliveries. |
| `infertility_history_flag` | — | bool |  | |
| `infertility_duration_months` | months | int |  | |
| `fertility_treatment_use` | — | bool |  | |
| `family_history_pcos` | — | bool |  | |
| `family_history_t2d` | — | bool |  | |

### 3.10 Mental health & quality of life

Depression and anxiety comorbidity in PCOS is substantially elevated and
increasingly central to the research literature.

| Field | Unit | Type | Derived | Notes |
|---|---|---|---|---|
| `depression_screen_score` | score | float |  | Raw instrument score. Scales differ in range and direction — not comparable across instruments without the instrument field. |
| `depression_instrument` | — | enum: `PHQ-9`, `PHQ-2`, `CES-D`, `BDI-II`, `HADS-D`, `EPDS`, `other`, `unknown` |  | **Required if score present.** Use `other` for unlisted instruments and preserve the verbatim name in `value_raw`. |
| `anxiety_screen_score` | score | float |  | Raw instrument score. |
| `anxiety_instrument` | — | enum: `GAD-7`, `GAD-2`, `STAI`, `HADS-A`, `BAI`, `other`, `unknown` |  | **Required if score present.** Use `other` for unlisted instruments and preserve the verbatim name in `value_raw`. |
| `quality_of_life_score` | score | float |  | Raw instrument score. |
| `quality_of_life_instrument` | — | enum: `PCOSQ`, `PCOSQ-50`, `MPCOSQ`, `SF-36`, `SF-12`, `WHOQOL-BREF`, `EQ-5D`, `other`, `unknown` |  | Required if score present. `PCOSQ` and variants are PCOS-specific; the others are generic. |

> **Scores are not harmonized across instruments.** A PHQ-9 of 12 and a CES-D
> of 12 mean different things, and this schema makes no attempt to convert
> between them. The instrument field exists so downstream analysis can stratify
> or exclude rather than pool naively.

### 3.11 Diagnosis label

| Field | Unit | Type | Derived | Notes |
|---|---|---|---|---|
| `pcos_diagnosis_flag` | — | bool | ✓ | Derived: clinical logic — see §7 |
| `diagnostic_criteria_version` | — | enum: `NIH_1990`, `Rotterdam_2003`, `AE_PCOS_2006`, `Intl_2018`, `Intl_2023`, `unknown` |  | |
| `criteria_met` | — | set of `ovulatory`, `hyperandrogenism`, `pcom` |  | |
| `phenotype` | — | enum: `A`, `B`, `C`, `D`, `unknown` | ✓ | Derived: from `criteria_met` — see §7 |
| `diagnosis_source` | — | enum: `clinician`, `self_report`, `derived`, `unknown` |  | |
| `diagnosis_date` | ISO 8601 | date |  | |

### 3.12 Sample context

Attachable to any laboratory measurement.

| Field | Type | Derived | Notes |
|---|---|---|---|
| `cycle_day_at_draw` | int |  | Days since menses onset. Frequently undefined in this population — that is expected, not an error. |
| `collection_date` | date |  | ISO 8601. |
| `fasting_status` | enum: `fasting`, `non_fasting`, `unknown` |  | Gates interpretability of glucose/insulin/lipids. |

---

## 4. Canonical unit reference

| Field | Section | Canonical | Common source | Factor |
|---|---|---|---|---|
| `total_testosterone` | §3.4 | nmol/L | ng/dL | × 0.0347 |
| `free_testosterone` | §3.4 | pmol/L | pg/mL | × 3.47 |
| `dheas` | §3.4 | µmol/L | µg/dL | × 0.02714 |
| `androstenedione` | §3.4 | nmol/L | ng/dL | × 0.0349 |
| `estradiol` | §3.6 | pmol/L | pg/mL | × 3.671 |
| `progesterone_luteal` | §3.3 | nmol/L | ng/mL | × 3.18 |
| `amh` | §3.5 | pmol/L | ng/mL | × 7.14 |
| `prolactin` | §3.7 | mIU/L | ng/mL | × 21.2 |
| `17_hydroxyprogesterone` | §3.7 | nmol/L | ng/dL | × 0.0303 |
| `cortisol` | §3.7 | nmol/L | µg/dL | × 27.59 |
| `fasting_glucose` | §3.8 | mmol/L | mg/dL | × 0.0555 |
| `ogtt_2hr_glucose` | §3.8 | mmol/L | mg/dL | × 0.0555 |
| `fasting_insulin` | §3.8 | pmol/L | µIU/mL | × 6.945 |
| `total_cholesterol` | §3.8 | mmol/L | mg/dL | × 0.0259 |
| `hdl_cholesterol` | §3.8 | mmol/L | mg/dL | × 0.0259 |
| `ldl_cholesterol` | §3.8 | mmol/L | mg/dL | × 0.0259 |
| `triglycerides` | §3.8 | mmol/L | mg/dL | × 0.0113 |
| `height_cm` | §3.1 | cm | in | × 2.54 |
| `weight_kg` | §3.1 | kg | lb | × 0.4536 |
| `waist_circumference_cm` | §3.1 | cm | in | × 2.54 |
| `hip_circumference_cm` | §3.1 | cm | in | × 2.54 |
| `hba1c_percent` | §3.8 | % (NGSP) | mmol/mol (IFCC) | (IFCC × 0.0915) + 2.15 |

`shbg`, `lh`, `fsh`, and `tsh` are conventionally reported in nmol/L, IU/L,
IU/L, and mIU/L respectively across most sources; no conversion typically
required, but `unit_raw` must still be recorded.

---

## 5. Provenance metadata

Every value in a conforming dataset carries a provenance record. This is part of
the schema, not an implementation detail: a value without provenance is not
conformant.

| Field | Type | Notes |
|---|---|---|
| `value_raw` | any | As found in source, before any transformation. |
| `unit_raw` | string | The unit the source used. Recorded even when no conversion was needed. |
| `value_canonical` | any | After conversion to the canonical unit. |
| `unit_canonical` | string | Per the field definition in §3. |
| `source_file` | string | |
| `source_column_name` | string | e.g. `LBXTST` |
| `transformation_applied` | string | Human-readable description, e.g. `ng/dL -> nmol/L`. |
| `mapping_confidence` | float 0–1 | Confidence that this source column corresponds to this canonical field. |
| `mapping_rationale` | string | Why the mapping was proposed. |
| `human_reviewed` | bool | **Defaults false.** Set true only by explicit reviewer approval, never automatically. |
| `below_lod_flag` | bool | Value below the assay's limit of detection. |

**Raw values are never discarded.** `value_raw` and `unit_raw` are retained
alongside the canonical form so that any conversion can be independently checked
or reversed. A conforming dataset is auditable back to its source columns.

**Unreviewed data is usable but marked.** `human_reviewed: false` does not
invalidate a value; it records that no human has confirmed the mapping. Analyses
may filter on it.

---

## 6. Missingness vocabulary

Missing values are never blank. One of:

| Code | Meaning |
|---|---|
| `not_measured` | Not collected in this dataset. |
| `below_lod` | Measured, below limit of detection. |
| `not_applicable` | Structurally undefined (e.g. cycle length post-hysterectomy). |
| `withheld` | Suppressed for privacy or disclosure control. |
| `unknown` | Present in source but uninterpretable (e.g. NHANES codes 7/9/777/999). |

---

## 7. Derivation rules

Some canonical fields may be computed from others when the source does not
supply them directly. This section defines *what* each derived field means and
under what conditions it is valid — not how to compute it. See
`IMPLEMENTATION_NOTES.md` for ordering, precedence, and code.

**Derivation is distinct from unit conversion.** Conversion rescales a value
that *was* present into canonical units — same measurement, different scale.
Derivation computes a field that was *absent*, from fields that were present. A
dataset reporting testosterone in ng/dL requires a conversion; a dataset
reporting testosterone and SHBG but no FAI permits a derivation.

**A derived value never replaces a source-supplied one.** Where both exist, the
source value is authoritative and the derived value is recorded alongside it.

### 7.1 Arithmetic derivations

Defined by the formulas given in §3. Valid only when every input is present in
canonical units.

`bmi` · `waist_hip_ratio` · `free_androgen_index` · `homa_ir` · `lh_fsh_ratio` ·
`antral_follicle_count_max` · `ovarian_volume_max_ml`

### 7.2 Criterion derivations

**`ovulatory_dysfunction_derived`** — true if any of: `amenorrhea_flag`,
`oligomenorrhea_flag`, `cycles_per_year` < 8, `cycle_length_days_typical` > 35,
or `irregular_cycles_self_report`.

*Not valid* — and must be left `not_applicable` — when `hysterectomy_flag`,
`pregnancy_status = pregnant`, `breastfeeding_flag`, or
`hormonal_contraceptive_use = current`. Each of these produces cycle patterns
unrelated to ovulatory function.

**`hyperandrogenism_derived`** — true if clinical (`hirsutism_flag`, or
`hirsutism_score_mfg` above the recorded threshold) or biochemical (elevated
`total_testosterone`, `free_testosterone`, `free_androgen_index`, or `dheas`
relative to the source's stated reference range).

*Not valid* when `antiandrogen_use` or `hormonal_contraceptive_use = current`,
both of which suppress the signal being measured.

> Biochemical thresholds are **deliberately not fixed** in v0.1. Use the source
> dataset's own reference range and record it. Assay-method differences make
> universal cut-points unsafe.

**`pcom_flag`** — valid only when `antral_follicle_count_max`,
`ovarian_volume_max_ml`, or `amh` is present *and* `pcom_threshold_applied` is
recorded. Never inferred without a stated threshold.

*Not valid* within approximately 8 years of menarche, where multifollicular
ovaries are developmentally normal.

### 7.3 Diagnosis derivations

**`phenotype`** — from `criteria_met`:

| Phenotype | Criteria |
|---|---|
| A | ovulatory + hyperandrogenism + pcom |
| B | ovulatory + hyperandrogenism |
| C | hyperandrogenism + pcom |
| D | ovulatory + pcom |

**`pcos_diagnosis_flag`** — true when 2 of 3 criteria are met **and**
`exclusions_assessed_flag` is true.

Where exclusions were not assessed, the derived value is `unknown`, never
`false`. An unexcluded PCOS-like presentation is not a negative result.

---

## 8. Out-of-scope input handling

Longitudinal and time-series data — wearables, CGM, daily symptom logs, cycle
event streams — is outside v0.1.

Such data must not be collapsed into subject-level summaries to fit this schema.
The choice of aggregation (mean resting heart rate? luteal-phase mean? nadir?)
is a research decision that changes what the value means, and encoding one
choice into a harmonization layer silently commits every downstream user to it.

Planned for v0.2: a companion long-format table
(`subject_id`, `timestamp`, `metric`, `value_canonical`, `unit_canonical`,
`device_model`) plus a `cycle_events` table for phase alignment.

---

## 9. Dataset coverage

A dataset conforming to this schema will populate only part of it. That is
expected — partial coverage is a supported outcome, not a failure — but the
*extent* of coverage determines what research questions the dataset can answer.

Coverage is assessed per Rotterdam criterion:

| Level | Meaning |
|---|---|
| `full` | The criterion can be evaluated for most subjects. |
| `partial` | Some evidence present, but insufficient or indirect. |
| `absent` | No field bearing on this criterion is populated. |

**A dataset can support a Rotterdam case definition only if at least two of the
three criteria are evaluable and `exclusions_assessed_flag` is populated.**
Datasets failing this remain useful for other purposes — androgen distribution,
metabolic phenotyping — but cannot define cases.

Two fields warrant separate reporting because their absence invalidates analyses
that would otherwise appear valid:

- **`hormonal_contraceptive_use`** — without it, androgen and cycle values
  cannot be interpreted.
- **`androgen_assay_method`** — without it, androgen values cannot be pooled
  across datasets.

A dataset failing coverage is a valid and useful result.

---

## 10. Known limitations

- Not reviewed by a clinical domain expert.
- Biochemical hyperandrogenism thresholds are deliberately not fixed.
- Ethnicity-specific hirsutism thresholds are not encoded.
- Adolescent-specific diagnostic rules are flagged by the validator but not
  fully implemented.
- Longitudinal data is out of scope.
- Assay harmonization is recorded but not corrected for — no cross-assay
  calibration is applied.

---

## 11. License

Schema and specification released under CC BY 4.0. Reference implementation
released under MIT.
