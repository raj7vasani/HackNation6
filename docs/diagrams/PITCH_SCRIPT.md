# 50-Second Pitch Script

Read alongside [architecture.md](architecture.md).

---

> PCOS research data is scattered — different formats, units, and column names, with no common schema. This tool fixes that with one pipeline.
>
> Raw files get ingested and profiled. An LLM proposes which column maps to which canonical field, and what unit it's in — that's the *only* place AI touches the data.
>
> Confident mappings flow straight through. If it's stuck — say, an ambiguous unit — the pipeline **pauses** and asks a human to confirm, right in the UI.
>
> Everything after that is deterministic: unit conversion, derived fields like BMI, the Rotterdam criteria logic, and validation.
>
> The output is a standardized dataset, plus a coverage report — an honest verdict on whether this dataset can actually support a PCOS diagnosis.
>
> And afterward, you can chat with the results, grounded in that exact run.

---

*~135 words — read at a natural pace, this lands at about 50 seconds.*
