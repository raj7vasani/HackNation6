# 📝 Problem Statement

---

## 1. Problem Statement

Research on PCOS (Polycystic Ovary Syndrome) is fragmented across incompatible data sources. Population health surveys (e.g. NHANES), hospital exports, wearable-derived datasets, and independent research studies each capture PCOS-relevant variables — cycle regularity, androgen levels, BMI, insulin markers — under different column names, units, and formats. There is no shared standard that lets a researcher combine two PCOS datasets without manually rewriting a mapping script from scratch every time.

This is not a hypothetical gap. The clinical diagnostic standard for PCOS, the **Rotterdam criteria**, has existed since 2003 and is universally recognized, yet no lightweight, open data schema translates that standard into a machine-usable format. As a result, researchers rebuild the same harmonization work in isolation for every new dataset, which slows down comparative research and makes results across studies difficult to reproduce or combine. This mirrors the challenge brief's own diagnosis: *"data, models, and benchmarks are scattered across institutions, making approaches difficult to compare and research slow to compound."*

**PCOS Schema Mapper** addresses this by defining an open, Rotterdam-criteria-grounded data schema for PCOS research, and providing a tool that uses AI to propose — and a human to approve — a mapping from any raw input dataset into that standardized schema, producing a clean, analysis-ready output file.

---



## 2. Main Functionality

The project covers two core layers:

- **Standardized PCOS Schema** — An open, documented data schema grounded in the Rotterdam criteria (oligo/anovulation, biochemical/clinical hyperandrogenism, polycystic ovarian morphology) plus common supporting covariates (age, BMI, fasting glucose/insulin). Each field has a defined type, unit, and valid range, published with a rationale for its clinical relevance.
- **AI-Assisted Mapping Tool** — Given a user-provided input file (e.g. a CSV export from NHANES, a hospital dataset, or a Kaggle PCOS dataset), an LLM inspects the column names and a sample of values, then proposes a candidate mapping from each input column to a schema field, including unit conversions where needed (e.g. testosterone in nmol/L vs ng/dL).
- **Human-in-the-Loop Review** — The user is guided through each proposed mapping, with a preview of sample values, and can approve, reassign to a different schema field, or discard it. No mapping is applied without explicit confirmation.
- **Deterministic Transformation & Validation** — Once mappings are approved, a deterministic (non-AI) transformation step applies the unit conversions and produces the final output file conforming to the schema. Validation checks flag out-of-range values, missing units, or type mismatches before the file is finalized.

---



## 3. Intended Users


| User                     | Role in the System                                                                                                             |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------ |
| **Researchers**          | Upload a raw dataset, review AI-proposed field mappings, export a schema-conformant file for analysis                          |
| **Data Engineers / RAs** | Reuse the published schema and mapping tool to harmonize new datasets without rebuilding mapping logic from scratch            |
| **Future Contributors**  | Extend the schema (e.g. add new fields, support new Rotterdam-adjacent conditions) since it is published under an open license |


---



## 4. GenAI Integration

The AI component is a **schema-mapping assistant** that inspects an uploaded dataset's columns and proposes correspondences to the standardized PCOS schema. It is grounded in the actual column names and sample values from the user's file, rather than guessing from field names alone, and it never writes final data values itself — it only proposes a mapping, which a human must confirm before any deterministic transformation runs.

Because the AI's output is a **proposal subject to human approval and deterministic execution**, the tool avoids the failure mode of black-box LLM data transformation: mappings are auditable, reproducible, and never silently applied.

**Example interaction:**

- *Input file has a column* `T_total_nmol_L` *→ AI proposes mapping to schema field* `testosterone_total_ng_dl`, *flags the unit mismatch, and suggests the conversion factor.*
- *Input file has a column* `cycle_len_days` *→ AI proposes mapping to schema field* `cycle_regularity`, *with a suggested categorical binning rule (e.g. <21 or >35 days = irregular).*
- *User reviews both proposals, edits the second one's binning threshold, and confirms.*

The integration is meaningful rather than cosmetic: it directly targets the documented "fragmented infrastructure" problem by making dataset harmonization fast and reviewable instead of a from-scratch manual task each time.

---



## 5. Application Scenarios



### Scenario 1 — Researcher harmonizes a NHANES export

Dr. Lee downloads a NHANES subset with reproductive health, hormone lab, and demographic variables. She uploads the raw CSV to PCOS Schema Mapper. The AI proposes mappings for each relevant column to the standardized schema, including a unit conversion for testosterone. She reviews the suggestions, accepts most, corrects one field mapping, and exports a schema-conformant file ready for analysis.

### Scenario 2 — Research assistant harmonizes a second, differently-structured dataset

A research assistant receives a PCOS dataset from a public Kaggle source, with entirely different column names and no shared structure with the NHANES export. Instead of writing a new mapping script from scratch, they run it through the same tool. The AI proposes a new set of mappings tailored to this file's columns. Once approved, the output file uses the same standardized schema as the NHANES file, so both datasets can now be directly combined or compared.

### Scenario 3 — Reviewing and correcting an ambiguous mapping

The AI proposes mapping a column named `hair_score` to the schema's hirsutism field, but flags low confidence since the scale used isn't clear from the data alone. The user inspects the sample values, recognizes it as a Ferriman-Gallwey score, and confirms the mapping with the correct scale noted. The deterministic validation step then checks the values fall within the expected 0–36 range for that score.

### Scenario 4 — Future researcher reuses the published schema

Months after the hackathon, another research group encounters the published PCOS schema and mapping tool. Rather than designing their own data model, they adopt the existing schema, use the tool to harmonize their own dataset, and their results become directly comparable to work built on the same standard — compounding progress instead of duplicating it.