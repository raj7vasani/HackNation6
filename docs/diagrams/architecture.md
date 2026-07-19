# PCOS Schema Mapper — Architecture

One pipeline: an LLM *proposes* how to map a raw dataset onto the canonical PCOS schema, a human confirms it only when the pipeline is genuinely stuck, and deterministic code does every calculation. No model ever touches a number.

```mermaid
flowchart TD
    IN["📁 Raw input files<br/><small>CSV · XPT · Excel — NHANES, clinic exports, anything</small>"]
    ING["Ingest + Profile<br/><small>join multi-file inputs, extract per-column signals</small>"]
    PROP{{"🤖 Propose<br/><small>LLM/heuristic: column → canonical field + unit</small>"}}
    STUCK{"Confident?"}
    REVIEW["🧑 Human review<br/><small>confirm the unit — pipeline pauses here</small>"]
    TRANSFORM["Transform<br/><small>unit conversion · missingness · value maps</small>"]
    DERIVE["Derive<br/><small>BMI, FAI, HOMA-IR → Rotterdam criteria → diagnosis</small>"]
    VALIDATE["Validate<br/><small>schema rules, plausibility checks</small>"]
    REPORT["Report<br/><small>coverage verdict: can this dataset diagnose PCOS?</small>"]
    OUT["📊 Standardized dataset<br/><small>+ per-value provenance</small>"]
    CHAT["💬 Chat assistant<br/><small>ask questions grounded in this run</small>"]

    IN --> ING --> PROP --> STUCK
    STUCK -- "yes, pause" --> REVIEW --> TRANSFORM
    STUCK -- "no" --> TRANSFORM
    TRANSFORM --> DERIVE --> VALIDATE --> REPORT
    REPORT --> OUT
    REPORT --> CHAT

    classDef llm fill:#7c3aed,stroke:#a78bfa,color:#fff;
    classDef human fill:#f59e0b,stroke:#fbbf24,color:#000;
    classDef det fill:#0e7490,stroke:#22d3ee,color:#fff;
    classDef out fill:#1e293b,stroke:#475569,color:#e2e8f0;
    class PROP llm;
    class REVIEW human;
    class ING,TRANSFORM,DERIVE,VALIDATE,REPORT det;
    class IN,OUT,CHAT out;
```

**The one thing to say out loud:** the LLM only labels columns and units — it never converts, derives, or diagnoses. Everything below the propose step is deterministic, auditable Python, so the same reviewed mapping always produces the same output.
