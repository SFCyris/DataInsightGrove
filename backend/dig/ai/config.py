"""Resolve AiConfig from the existing key/value settings table.

The five keys live in dig/api/settings.py's allow-list:
  ai_enabled    : bool
  ai_provider   : enum("local", "openai_compat", "disabled")
  ai_endpoint   : string (e.g. http://localhost:11434/v1)
  ai_model      : string (e.g. gemma4:e4b)
  ai_api_key    : string (masked on read in the settings API)

Sane defaults: provider=local, endpoint=Ollama loopback, model=Gemma 4 E4B.
The user changes them in Settings → AI.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dig.ai.client import AiConfig
from dig.storage.models import Setting


_DEFAULTS: dict[str, object] = {
    "ai_enabled": False,
    "ai_provider": "local",
    "ai_endpoint": "http://localhost:11434/v1",
    "ai_model": "gemma4:e4b",
    "ai_api_key": "",
    "ai_max_tokens": 4096,
    "ai_temperature": 0.0,
}


async def load_config(db: AsyncSession) -> AiConfig:
    """Read the five ai_* keys from the settings table; fall back to
    defaults for any that aren't set. Returns a populated AiConfig
    even when AI is disabled (so probes / settings reads still work).
    """
    rows = (await db.execute(
        select(Setting).where(Setting.key.in_(list(_DEFAULTS.keys()))),
    )).scalars().all()
    values: dict[str, object] = dict(_DEFAULTS)
    for r in rows:
        if r.value is not None:
            values[r.key] = r.value

    return AiConfig(
        enabled=bool(values["ai_enabled"]),
        provider=str(values["ai_provider"]),
        endpoint=str(values["ai_endpoint"]),
        model=str(values["ai_model"]),
        api_key=str(values["ai_api_key"]) or None,
        max_tokens=int(values["ai_max_tokens"]),  # type: ignore[arg-type]
        temperature=float(values["ai_temperature"]),  # type: ignore[arg-type]
    )
