"""The data-chat assistant: answers questions grounded in a run's context.

The dataset summary (see :mod:`.context`) is injected into the system prompt once
and reused on every turn, so from the user's point of view "the data is already
loaded" the moment they open the chat.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..propose.client import LLMClient, get_default_client
from .context import build_data_context

if TYPE_CHECKING:
    from ..pipeline import PipelineResult

SYSTEM_PROMPT = """\
You are a data analyst assistant embedded in the PCOS Canonical Schema Converter.
A clinical dataset has already been harmonized into a canonical schema, and a
snapshot of the results is provided below. Answer the user's questions about THIS
dataset.

Ground rules:
- Use ONLY the dataset snapshot below. Do not invent columns, values, or subjects.
- If the snapshot does not contain what is asked, say so plainly and, if helpful,
  point to where it would come from (e.g. "that column was left unmapped").
- Be concrete: cite counts, ranges, units, and coverage status from the snapshot.
- Units matter. Values are in the canonical unit shown in the column mapping;
  mention the unit when you quote a number.
- Distinguish "not measured" from a real value of zero — missingness codes
  (not_measured, below_lod, not_applicable, withheld, unknown) are not numbers.
- You explain the data; you do NOT recompute or re-derive values, and you do not
  provide medical advice or individual diagnoses. The coverage verdict is about
  what the *dataset* can support, not about any person.
- Keep answers concise and skimmable. Use short bullet lists when it helps.

=== DATASET SNAPSHOT ===
{context}
=== END SNAPSHOT ==="""


def chat_available() -> bool:
    """True when an LLM client can be constructed (an API key is configured)."""
    return get_default_client() is not None


class DataChatAssistant:
    """Stateless-per-call chat over a single :class:`PipelineResult`.

    The caller owns the conversation history (a list of ``{"role", "content"}``
    dicts) so the UI can persist it in session state.
    """

    def __init__(self, context: str, client: LLMClient | None = None) -> None:
        self.context = context
        self.client = client or get_default_client()

    @classmethod
    def from_result(
        cls, result: "PipelineResult", client: LLMClient | None = None
    ) -> "DataChatAssistant":
        return cls(build_data_context(result), client=client)

    @property
    def available(self) -> bool:
        return self.client is not None

    def system_prompt(self) -> str:
        return SYSTEM_PROMPT.format(context=self.context)

    def answer(self, history: list[dict[str, str]]) -> str:
        """Answer given the full prior ``history`` (last entry = the new question)."""
        if self.client is None:
            raise RuntimeError(
                "Data chat needs an OpenAI API key (set OPENAI_API_KEY). "
                "The mapping pipeline runs offline, but free-form chat does not."
            )
        # Only pass user/assistant turns to the model; system holds the context.
        turns = [m for m in history if m.get("role") in ("user", "assistant")]
        return self.client.complete_text(self.system_prompt(), turns)
