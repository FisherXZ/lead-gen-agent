"""Skills registry — auto-discovers skill modules.

Skills are higher-level capabilities (PDF processing, CSV export, etc.)
that can be used by tools or invoked directly. Each skill lives in its
own sub-package under ``skills/``.

To add a new skill:
    1. Create ``skills/<name>/__init__.py`` with a ``SKILL_META`` dict
    2. Implement the skill's functions in the sub-package
    3. It auto-registers on import

``SKILL_META`` example::

    SKILL_META = {
        "name": "pdf",
        "description": "Extract text and tables from PDF documents",
        "version": "0.1.0",
    }
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import Any

logger = logging.getLogger(__name__)

_SKILLS: dict[str, Any] = {}


def _discover() -> None:
    """Walk sub-packages and register any with SKILL_META."""
    import src.skills as pkg

    for info in pkgutil.iter_modules(pkg.__path__, prefix=pkg.__name__ + "."):
        if not info.ispkg:
            continue
        try:
            mod = importlib.import_module(info.name)
            meta = getattr(mod, "SKILL_META", None)
            if meta and "name" in meta:
                _SKILLS[meta["name"]] = mod
                logger.debug("Registered skill: %s", meta["name"])
        except Exception:
            logger.warning("Failed to load skill: %s", info.name, exc_info=True)


def get_skill(name: str) -> Any:
    """Return a skill module by name, or None."""
    if not _SKILLS:
        _discover()
    return _SKILLS.get(name)


def list_skills() -> list[dict]:
    """Return metadata for all registered skills."""
    if not _SKILLS:
        _discover()
    return [getattr(mod, "SKILL_META", {}) for mod in _SKILLS.values()]
