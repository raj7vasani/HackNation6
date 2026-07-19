"""Tests for the read-only data-chat assistant (context + grounding)."""

from __future__ import annotations

import pytest

from pcos_harmonizer.chat import DataChatAssistant, build_data_context
from pcos_harmonizer.chat import assistant as assistant_mod
from pcos_harmonizer.config import MOCK_DATA_DIR
from pcos_harmonizer.pipeline import run_from_mapping

MOCK_XPT = MOCK_DATA_DIR / "mock_pcos_clinic.xpt"
CURATED = MOCK_DATA_DIR / "demo_snapshot" / "mock_pcos_clinic.mapping.yaml"

pytestmark = pytest.mark.skipif(
    not (MOCK_XPT.exists() and CURATED.exists()),
    reason="mock demo snapshot not present",
)


@pytest.fixture
def result():
    # Deterministic, offline: re-run the curated (human-reviewed) mapping.
    return run_from_mapping([MOCK_XPT], CURATED, source=None)


class FakeClient:
    """Records the last call so we can assert on what the model was given."""

    def __init__(self) -> None:
        self.system = None
        self.messages = None

    def complete_text(self, system, messages, temperature=0.2):
        self.system = system
        self.messages = messages
        return "canned answer"


def test_context_has_all_sections(result):
    ctx = build_data_context(result)
    for header in ("COVERAGE REPORT", "COLUMN MAPPING", "COLUMN STATISTICS",
                   "VALIDATOR WARNINGS", "SAMPLE ROWS"):
        assert header in ctx
    # Coverage verdict text is carried into the context verbatim.
    assert result.coverage["verdict"] in ctx


def test_context_is_bounded(result):
    # Should summarize, not dump the whole table.
    ctx = build_data_context(result)
    assert len(ctx) < 40_000


def test_assistant_embeds_context_and_only_passes_turns(result):
    fake = FakeClient()
    assistant = DataChatAssistant.from_result(result, client=fake)
    history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "system", "content": "should be dropped"},
        {"role": "user", "content": "how many subjects?"},
    ]
    answer = assistant.answer(history)

    assert answer == "canned answer"
    # The dataset snapshot is injected into the system prompt.
    assert "COVERAGE REPORT" in fake.system
    # System-role turns from history are not forwarded to the model.
    assert fake.messages == [m for m in history if m["role"] in ("user", "assistant")]
    assert {"role": "system", "content": "should be dropped"} not in fake.messages


def test_assistant_requires_a_client(result, monkeypatch):
    # Simulate "no API key": get_default_client() returns None.
    monkeypatch.setattr(assistant_mod, "get_default_client", lambda: None)
    assistant = DataChatAssistant.from_result(result)
    assert assistant.available is False
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        assistant.answer([{"role": "user", "content": "hi"}])
