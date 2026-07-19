"""PCOS Canonical Schema Converter — Streamlit UI.

Two tools in one app:
  • Schema Harmonizer  — maps a dataset onto the PCOS canonical schema and reports
    Rotterdam-criteria coverage (backend/pcos_harmonizer).
  • Quick Convert & Profile — loads a file, profiles its columns, and exports a
    converted CSV + profile report (src/pipeline.process_file).

Run from the repo root:
    streamlit run UI/upload/app.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

# --- make backend/ and repo root importable --------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"
for _p in (BACKEND, REPO_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from pcos_harmonizer import app_api, review, to_bytes  # noqa: E402
from pcos_harmonizer.chat import (  # noqa: E402
    DataChatAssistant,
    build_data_context,
    chat_available,
)
from pcos_harmonizer.config import (  # noqa: E402
    get_openai_api_key,
    mock_data_files,
    use_mock_data,
)
from pcos_harmonizer.report.coverage import format_report  # noqa: E402

# Quick-convert pipeline from main (optional — degrade gracefully if absent).
try:
    from src.pipeline import process_file  # noqa: E402

    HAS_QUICK_CONVERT = True
except Exception:  # noqa: BLE001
    process_file = None
    HAS_QUICK_CONVERT = False


# -----------------------------
# Page config + styling
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
    .file-card { background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.1);
                 padding:15px; border-radius:15px; margin-top:10px; color:white; }
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
# Sidebar controls (Schema Harmonizer)
# -----------------------------
ENGINE_LABELS = {
    "AI mapping (LLM)": "llm",
    "Heuristic (offline)": "heuristic",
    "Demo (curated mapping)": "demo",
}

with st.sidebar:
    st.header("Harmonizer settings")

    has_key = bool(get_openai_api_key())
    st.caption(f"OpenAI key: {'detected' if has_key else 'not found'}")
    st.caption(f"USE_MOCK_DATA: {'on' if use_mock_data() else 'off'}")
    # Helps confirm .streamlit/config.toml was loaded (upload 403 if still True).
    st.caption(f"XSRF protection: {'on' if st.get_option('server.enableXsrfProtection') else 'off'}")

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


tab_harm, tab_chat, tab_convert = st.tabs(
    ["🧬 Schema Harmonizer", "💬 Chat with your data", "⚡ Quick Convert & Profile"]
)


# ===========================================================================
# TAB 1 — Schema Harmonizer
# ===========================================================================
with tab_harm:
    st.markdown("### 1 · Choose input data")

    input_paths: list[Path] = []
    mock_available = mock_data_files()

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
            max_upload_size=3,
            key="harm_uploader",
        )
        if uploaded:
            tmp_dir = Path(tempfile.mkdtemp(prefix="pcos_upload_"))
            for f in uploaded:
                dest = tmp_dir / f.name
                dest.write_bytes(f.getbuffer())
                input_paths.append(dest)
            st.caption(f"{len(input_paths)} file(s) ready.")

    st.markdown("### 2 · Analyze")
    run = st.button(
        "Analyze Dataset →",
        use_container_width=True,
        type="primary",
        disabled=not input_paths,
        key="harm_run",
    )

    def _harm_progress_cb():
        """A progress bar + step log, and the callback that drives them."""
        bar = st.progress(0.0, text="Starting pipeline…")
        log = st.empty()
        done: list[str] = []

        def cb(step: int, total: int, message: str) -> None:
            done.append(f"{step}/{total}  {message}")
            bar.progress(min(step / total, 1.0), text=message)
            log.markdown("\n".join(f"- {'✅' if i < len(done) - 1 else '⏳'} {l}"
                                   for i, l in enumerate(done)))
        return bar, cb

    def _finish(paths, mapping, prop) -> None:
        """Run the deterministic tail and store the outcome."""
        _bar, cb = _harm_progress_cb()
        st.session_state["outcome"] = app_api.complete_after_review(
            paths, mapping, engine_used=prop.engine_used,
            source=source_val, notes=prop.notes, on_progress=cb,
        )
        _bar.progress(1.0, text="Done")

    if run and input_paths:
        # Fresh run: clear any prior result / paused review.
        for k in ("outcome", "harm_phase", "harm_prop"):
            st.session_state.pop(k, None)
        st.session_state["harm_paths"] = [str(p) for p in input_paths]

        if engine == "demo":
            # Curated mapping — nothing to review, runs straight through.
            with st.spinner("Running curated demo mapping…"):
                try:
                    st.session_state["outcome"] = app_api.analyze(
                        input_paths, engine="demo", source=source_val)
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Analysis failed: {exc}")
        else:
            # Phase 1 — ingest + propose (this is where it may get "stuck").
            _bar, cb = _harm_progress_cb()
            try:
                prop = app_api.propose_for_review(
                    input_paths, engine=engine, source=source_val, on_progress=cb)
            except Exception as exc:  # noqa: BLE001
                _bar.empty()
                st.error(f"Analysis failed: {exc}")
                prop = None

            if prop is not None:
                if prop.mapping.blocked:
                    # Stuck → pause and ask the user for units.
                    st.session_state["harm_prop"] = prop
                    st.session_state["harm_phase"] = "review"
                    _bar.empty()
                    st.rerun()
                else:
                    _finish(st.session_state["harm_paths"], prop.mapping, prop)

    # -----------------------------------------------------------------------
    # Paused for review — ask for the missing units, then resume.
    # -----------------------------------------------------------------------
    if st.session_state.get("harm_phase") == "review":
        prop = st.session_state["harm_prop"]
        paths = st.session_state["harm_paths"]
        blocked = review.pending_units(prop.mapping)

        # The same column name can appear in several source files; ask once per
        # distinct column (the answer is applied to every matching entry).
        unique_blocked = []
        seen: set[str] = set()
        for b in blocked:
            if b.source_column in seen:
                continue
            seen.add(b.source_column)
            unique_blocked.append(b)

        extra = len(blocked) - len(unique_blocked)
        msg = f"⏸️ **Paused — {len(unique_blocked)} column(s) are stuck on an unknown unit.** "
        if extra:
            msg += f"({len(blocked)} blocked entries total, some repeated across files.) "
        st.warning(
            msg + "Pick the unit each value is recorded in, then continue. Leave one "
            "unresolved to pass it through unconverted."
        )
        if prop.notes:
            st.caption(" ".join(prop.notes))

        answers: dict[str, str] = {}
        for i, b in enumerate(unique_blocked):
            entry = review.entry_for(prop.mapping, b.source_column)
            cu = entry.unit_canonical if entry else None
            opts = review.unit_options(cu)
            choices = ["(leave unresolved)"] + opts
            default_idx = 1 if len(opts) == 1 else 0
            c1, c2 = st.columns([2, 3])
            with c1:
                st.markdown(f"**{b.source_column}** → `{entry.canonical_field}`")
                st.caption(f"canonical unit: {cu}")
            with c2:
                pick = st.selectbox(
                    f"Unit for {b.source_column}", choices, index=default_idx,
                    key=f"harm_unit_{i}_{b.source_column}", label_visibility="collapsed",
                )
            if pick != "(leave unresolved)":
                answers[b.source_column] = pick

        go, skip, cancel = st.columns([2, 2, 1])
        with go:
            if st.button("Apply units & continue →", type="primary",
                         use_container_width=True, key="harm_apply"):
                review.apply_unit_answers(prop.mapping, answers)
                _finish(paths, prop.mapping, prop)
                st.session_state.pop("harm_phase", None)
                st.rerun()
        with skip:
            if st.button("Skip all & continue", use_container_width=True, key="harm_skip"):
                _finish(paths, prop.mapping, prop)
                st.session_state.pop("harm_phase", None)
                st.rerun()
        with cancel:
            if st.button("Cancel", use_container_width=True, key="harm_cancel"):
                for k in ("harm_phase", "harm_prop"):
                    st.session_state.pop(k, None)
                st.rerun()

    outcome = st.session_state.get("outcome")
    if st.session_state.get("harm_phase") == "review":
        pass  # results are hidden while paused
    elif outcome is not None:
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

        r_cov, r_map, r_data, r_warn, r_dl = st.tabs(
            ["Coverage report", "Column mapping", "Standardized data", "Warnings", "Download"]
        )

        with r_cov:
            st.code(format_report(cov), language="text")

        with r_map:
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
                with st.expander(
                    f"🔎 {len(res.mapping.unmapped_columns)} column(s) left unmapped (visible, not guessed)"
                ):
                    st.dataframe(
                        pd.DataFrame(
                            {
                                "source_file": u.source_file,
                                "source_column": u.source_column,
                                "reason": u.reason,
                            }
                            for u in res.mapping.unmapped_columns
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )
            if res.mapping.blocked:
                with st.expander(
                    f"⏸️ {len(res.mapping.blocked)} column(s) blocked pending unit review"
                ):
                    st.dataframe(
                        pd.DataFrame(
                            {
                                "source_file": b.source_file,
                                "source_column": b.source_column,
                                "reason": b.reason,
                                "detail": b.detail or "",
                            }
                            for b in res.mapping.blocked
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )

        with r_data:
            st.dataframe(res.table, use_container_width=True, hide_index=True)

        with r_warn:
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

        with r_dl:
            try:
                payload = to_bytes(res.table, out_format)
                ext = {"stata": "dta"}.get(out_format, out_format)
                st.download_button(
                    f"Download standardized.{ext}",
                    data=payload,
                    file_name=f"standardized.{ext}",
                    use_container_width=True,
                    key="harm_dl",
                )
                st.caption(
                    "Nested provenance is embedded in JSON/JSONL; for flat formats it is "
                    "available as a sidecar when writing to disk via the API."
                )
            except Exception as exc:  # noqa: BLE001
                st.error(f"Could not serialize to {out_format}: {exc}")
    else:
        st.caption("Select input data and click Analyze to see the coverage report, mapping, and download options.")


# ===========================================================================
# TAB 2 — Chat with your data
# ===========================================================================
SUGGESTED_QUESTIONS = [
    "Can this dataset support a Rotterdam diagnosis? Why or why not?",
    "Which columns had unit conversions, and what were they?",
    "What are the biggest data-quality gaps I should know about?",
]


def _run_chat_turn(question: str) -> None:
    """Append the question + assistant answer to history, then rerun to render."""
    history = st.session_state.setdefault("chat_history", [])
    history.append({"role": "user", "content": question})
    assistant = DataChatAssistant(st.session_state["chat_context"])
    try:
        with st.spinner("Reading your standardized data…"):
            answer = assistant.answer(history)
    except Exception as exc:  # noqa: BLE001
        answer = f"⚠️ {exc}"
    history.append({"role": "assistant", "content": answer})
    st.rerun()


with tab_chat:
    st.markdown("### 💬 Chat with your standardized data")

    outcome = st.session_state.get("outcome")
    if outcome is None:
        st.info(
            "Run an analysis in the **Schema Harmonizer** tab first. Once your dataset "
            "is standardized, it loads into the assistant automatically and you can ask "
            "questions about it here."
        )
    elif not chat_available():
        st.warning(
            "Data chat needs an OpenAI API key. Set `OPENAI_API_KEY` in your `.env` and "
            "restart. (The mapping pipeline runs offline, but free-form chat does not.)"
        )
    else:
        res = outcome.result
        # Rebuild context + reset history whenever a new analysis is loaded.
        token = id(res)
        if st.session_state.get("chat_token") != token:
            st.session_state["chat_token"] = token
            st.session_state["chat_context"] = build_data_context(res)
            st.session_state["chat_history"] = []

        cov = res.coverage
        top_l, top_r = st.columns([4, 1])
        with top_l:
            st.caption(
                f"✅ Loaded into context: **{cov['n_subjects']} subjects**, "
                f"**{len(res.mapping.active_mappings())} mapped columns**, "
                f"coverage verdict *“{cov['verdict']}”*. Ask anything about it below."
            )
        with top_r:
            if st.button("🧹 Clear chat", use_container_width=True, key="chat_clear"):
                st.session_state["chat_history"] = []
                st.rerun()

        history = st.session_state.get("chat_history", [])

        if not history:
            st.markdown("**Try asking:**")
            for i, q in enumerate(SUGGESTED_QUESTIONS):
                if st.button(q, key=f"chat_suggest_{i}", use_container_width=True):
                    _run_chat_turn(q)

        for msg in history:
            with st.chat_message(msg["role"], avatar="🧑‍⚕️" if msg["role"] == "user" else "🤖"):
                st.markdown(msg["content"])

        user_q = st.chat_input("Ask about your standardized data…")
        if user_q:
            _run_chat_turn(user_q)

        st.caption(
            "The assistant explains the harmonized data — it does not recompute values "
            "or give medical advice. Answers are grounded in this run's snapshot only."
        )


# ===========================================================================
# TAB 3 — Quick Convert & Profile (from main's src/ pipeline)
# ===========================================================================
with tab_convert:
    st.markdown("### Upload research dataset(s)")
    st.caption("Load XPT / CSV / Excel, profile the columns, and download a converted CSV + profile report.")

    if not HAS_QUICK_CONVERT:
        st.warning("`src/pipeline.process_file` is not importable, so quick convert is unavailable.")
    else:
        DATA_DIR = REPO_ROOT / "data"
        DATA_DIR.mkdir(exist_ok=True)

        convert_files = st.file_uploader(
            "Drop XPT, CSV, or Excel files",
            type=["xpt", "csv", "xlsx", "xls"],
            accept_multiple_files=True,
            max_upload_size=3,
            key="convert_uploader",
        )

        if convert_files:
            for file in convert_files:
                size_kb = file.size / 1024
                st.markdown(
                    f'<div class="file-card">📄 <b>{file.name}</b><br>'
                    f'<span style="color:#94a3b8">{size_kb:.1f} KB</span>'
                    f'<span style="float:right;color:#22c55e">✓ Ready</span></div>',
                    unsafe_allow_html=True,
                )

            if st.button("Convert & Profile →", use_container_width=True, key="convert_run"):
                progress = st.progress(0)
                for index, uploaded_file in enumerate(convert_files):
                    st.divider()
                    st.subheader(f"Processing {uploaded_file.name}")

                    file_path = DATA_DIR / uploaded_file.name
                    file_path.write_bytes(uploaded_file.getbuffer())

                    try:
                        with st.spinner("Analyzing dataset…"):
                            result = process_file(file_path)

                        st.success(f"{uploaded_file.name} processed successfully!")

                        if "df" in result:
                            st.subheader("Dataset preview")
                            st.dataframe(result["df"].head(), use_container_width=True)

                        if "profile" in result:
                            st.subheader("Column profile")
                            st.dataframe(result["profile"], use_container_width=True)

                        if "csv" in result:
                            with open(result["csv"], "rb") as fh:
                                st.download_button(
                                    "⬇ Download converted CSV",
                                    data=fh.read(),
                                    file_name=Path(result["csv"]).name,
                                    use_container_width=True,
                                    key=f"convert_dl_csv_{index}",
                                )
                        if "profile_csv" in result:
                            with open(result["profile_csv"], "rb") as fh:
                                st.download_button(
                                    "⬇ Download profile report",
                                    data=fh.read(),
                                    file_name=Path(result["profile_csv"]).name,
                                    use_container_width=True,
                                    key=f"convert_dl_profile_{index}",
                                )
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"Error processing {uploaded_file.name}")
                        st.exception(exc)

                    progress.progress((index + 1) / len(convert_files))

                st.success("All datasets processed.")
