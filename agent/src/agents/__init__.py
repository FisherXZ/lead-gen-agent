"""Agent configurations — factory functions for different runtime modes."""

from .chat import build_chat_runtime
from .research import build_research_runtime

__all__ = ["build_chat_runtime", "build_research_runtime"]
