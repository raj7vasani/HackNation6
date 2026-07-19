"""PCOS Canonical Schema Converter — Streamlit UI wired to the harmonizer backend.

Run from the repo root:
    streamlit run UI/upload/app.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

# --- make the backend package importable -----------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from pcos_harmonizer import app_api, to_bytes  # noqa: E402
from pcos_harmonizer.config import (  # noqa: E402
    get_openai_api_key,
    mock_data_files,
    use_mock_data,
)
from pcos_harmonizer.report.coverage import format_report  # noqa: E402

# -----------------------------
# Page config
# -----------------------------
st.set_page_config(page_title="PCOS Canonical Schema Converter", layout="wide")

st.markdown(
    """
    <style>
    .stApp {
        background:
        radial-gradient(circle at 20% 20%, rgba(59,130,246,0.25), transparent 30%),
        radial-gradient(circle at 80% 80%, rgba(139,92,246,0.20), transparent 35%),
        #030712;
        color: white;
    }
    #MainMenu, footer { visibility: hidden; }
    .block-container { max-width: 1200px; padding-top: 2.5rem; }
    .title { text-align:center; font-size: 2.8rem; font-weight: 800; color:white; letter-spacing:-1px; }
    .subtitle { text-align:center; color:#94a3b8; font-size:1.1rem; margin-bottom:1.5rem; }
    .verdict-ok { background:rgba(34,197,94,0.15); border:1px solid rgba(34,197,94,0.5);
                  border-radius:16px; padding:18px 24px; font-size:1.3rem; font-weight:700; color:#4ade80; }
    .verdict-no { background:rgba(245,158,11,0.12); border:1px solid rgba(245,158,11,0.5);
                  border-radius:16px; padding:18px 24px; font-size:1.3rem; font-weight:700; color:#fbbf24; }
    .badge { display:inline-block; padding:4px 12px; border-radius:999px; font-size:0.8rem;
             font-weight:600; background:rgba(255,255,255,0.1); border:1px solid rgba(255,255,255,0.2); }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="title">PCOS Canonical Schema Converter</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="subtitle">Standardize clinical datasets into a reproducible, auditable canonical schema.</div>',
    unsafe_allow_html=True,
)


# -----------------------------
# Sidebar controls
# -----------------------------
ENGINE_LABELS = {
    "AI mapping (LLM)": "llm",
    "Heuristic (offline)": "heuristic",
    "Demo (curated mapping)": "demo",
}

with st.sidebar:
    st.header("Settings")

    has_key = bool(get_openai_api_key())
    st.caption(f"OpenAI key: {'detected' if has_key else 'not found'}")
    st.caption(f"USE_MOCK_DATA: {'on' if use_mock_data() else 'off'}")

    default_engine_idx = 0 if has_key else 1
    engine_label = st.radio("Mapping engine", list(ENGINE_LABELS), index=default_engine_idx)
    engine = ENGINE_LABELS[engine_label]
    if engine == "llm" and not has_key:
        st.info("No API key — LLM will fall back to the heuristic engine.")

    out_format = st.selectbox(
        "Download format",
        ["csv", "json", "jsonl", "xlsx", "parquet", "stata", "xpt"],
        index=0,
    )
    source = st.selectbox("Source overrides", ["nhanes", "(none)"], index=0)
    source_val = None if source == "(none)" else source


# -----------------------------
# Input selection
# -----------------------------
st.markdown("### 1 · Choose input data")

input_paths: list[Path] = []
mock_available = mock_data_files()

col_a, col_b = st.columns(2)
with col_a:
    use_mock = st.toggle(
        "Use bundled mock data",
        value=use_mock_data() and bool(mock_available),
        help="Synthetic .xpt files in mock_data/ for testing and demos.",
    )

if use_mock:
    if not mock_available:
        st.warning("No files found in mock_data/. Run `python mock_data/generate_mock_data.py`.")
    else:
        names = [p.name for p in mock_available]
        default = [n for n in names if "clinic" in n] or names[:1]
        chosen = st.multiselect("Mock files", names, default=default)
        input_paths = [p for p in mock_available if p.name in chosen]
else:
    uploaded = st.file_uploader(
        "Upload XPT / CSV / Excel files",
        type=["xpt", "csv", "tsv", "xlsx", "xls"],
        accept_multiple_files=True,
    )
    if uploaded:
        tmp_dir = Path(tempfile.mkdtemp(prefix="pcos_upload_"))
        for f in uploaded:
            dest = tmp_dir / f.name
            dest.write_bytes(f.getbuffer())
            input_paths.append(dest)
        st.caption(f"{len(input_paths)} file(s) ready.")


# -----------------------------
# Run
# -----------------------------
st.markdown("### 2 · Analyze")
run = st.button("Analyze Dataset →", use_container_width=True, type="primary", disabled=not input_paths)

if run and input_paths:
    with st.spinner(f"Running the {engine_label} pipeline…"):
        try:
            outcome = app_api.analyze(input_paths, engine=engine, source=source_val)
            st.session_state["outcome"] = outcome
        except Exception as exc:  # noqa: BLE001
            st.session_state.pop("outcome", None)
            st.error(f"Analysis failed: {exc}")


# -----------------------------
# Results
# -----------------------------
outcome = st.session_state.get("outcome")
if outcome is not None:
    res = outcome.result

    if outcome.engine_used != outcome.requested_engine or outcome.notes:
        st.info(
            f"Engine used: **{outcome.engine_used}** "
            + (f"(requested: {outcome.requested_engine}). " if outcome.engine_used != outcome.requested_engine else "")
            + (" ".join(outcome.notes) if outcome.notes else "")
        )
    else:
        st.markdown(f'<span class="badge">engine: {outcome.engine_used}</span>', unsafe_allow_html=True)

    cov = res.coverage
    verdict_cls = "verdict-ok" if "Can support" in cov["verdict"] else "verdict-no"
    st.markdown(f'<div class="{verdict_cls}">{cov["verdict"]}</div>', unsafe_allow_html=True)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Subjects", cov["n_subjects"])
    m2.metric("Criteria evaluable", f"{cov['n_criteria_evaluable']}/3")
    m3.metric("Mapped columns", len(res.mapping.active_mappings()))
    m4.metric("Warnings", len(res.warnings))

    tab_cov, tab_map, tab_data, tab_warn, tab_dl = st.tabs(
        ["Coverage report", "Column mapping", "Standardized data", "Warnings", "Download"]
    )

    with tab_cov:
        st.code(format_report(cov), language="text")

    with tab_map:
        rows = []
        for m in res.mapping.mappings:
            rows.append(
                {
                    "source_column": m.source_column,
                    "canonical_field": m.canonical_field or "— (unmapped)",
                    "unit_raw": m.unit_raw or "",
                    "unit_canonical": m.unit_canonical or "",
                    "confidence": m.mapping_confidence,
                    "source": m.source,
                    "reviewed": m.human_reviewed,
                    "value_map": ", ".join(f"{k}→{v}" for k, v in (m.value_map or {}).items()),
                    "rationale": m.mapping_rationale or "",
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        if res.mapping.unmapped_columns:
            st.caption(f"{len(res.mapping.unmapped_columns)} column(s) left unmapped (visible, not guessed).")
        if res.mapping.blocked:
            st.caption(f"{len(res.mapping.blocked)} column(s) blocked pending unit review.")

    with tab_data:
        st.dataframe(res.table, use_container_width=True, hide_index=True)

    with tab_warn:
        if not res.warnings:
            st.success("No validator warnings.")
        else:
            by_rule: dict[str, int] = {}
            for w in res.warnings:
                by_rule[w.get("rule", "?")] = by_rule.get(w.get("rule", "?"), 0) + 1
            st.dataframe(
                pd.DataFrame(sorted(by_rule.items(), key=lambda x: -x[1]), columns=["rule", "count"]),
                use_container_width=True,
                hide_index=True,
            )
            with st.expander("All warnings"):
                st.dataframe(pd.DataFrame(res.warnings), use_container_width=True, hide_index=True)

    with tab_dl:
        try:
            payload = to_bytes(res.table, out_format)
            ext = {"stata": "dta"}.get(out_format, out_format)
            st.download_button(
                f"Download standardized.{ext}",
                data=payload,
                file_name=f"standardized.{ext}",
                use_container_width=True,
            )
            st.caption(
                "Nested provenance is embedded in JSON/JSONL; for flat formats it is "
                "available as a sidecar when writing to disk via the API."
            )
        except Exception as exc:  # noqa: BLE001
            st.error(f"Could not serialize to {out_format}: {exc}")
else:
    st.caption("Select input data and click Analyze to see the coverage report, mapping, and download options.")
