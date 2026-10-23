"""QuantOS LLM plumbing: the model registry and the call log (ADR-14, ADR-19)."""

from core.llm.calllog import log_call
from core.llm.registry import model_for, prices

__all__ = ["log_call", "model_for", "prices"]
