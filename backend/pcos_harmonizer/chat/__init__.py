"""Data-chat assistant — talk to a harmonized dataset in natural language.

A *read-only* advisory layer on top of a completed pipeline run. It summarizes a
:class:`~pcos_harmonizer.pipeline.PipelineResult` into a compact text context
(coverage, column mapping, per-column statistics, warnings, sample rows) and lets
the user ask questions grounded in that context.

This does **not** touch the numeric path. The LLM never computes or rewrites a
value here — it only explains figures that the deterministic pipeline already
produced. The project's "propose, don't execute" boundary is preserved.
"""

from .assistant import DataChatAssistant, chat_available
from .context import build_data_context

__all__ = ["DataChatAssistant", "build_data_context", "chat_available"]
