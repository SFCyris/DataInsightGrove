from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


_SYSTEM = (
    "You are a strict structured-data extractor. The user gives you a list of "
    "field names and a text. Respond with JSON only — exactly one object whose "
    "keys are the requested field names. Use null when a field isn't present. "
    "Do not invent values."
)


async def _extract_one(cfg, text: str, fields: list[str], context: str) -> dict[str, Any]:
    from dig.ai.client import chat, AiError

    user = (
        f"Task: {context}\n\n"
        f"Fields: {', '.join(fields)}\n\n"
        f"Text:\n{text[:6000]}"
    )
    try:
        resp = await chat(
            cfg,
            messages=[{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
            response_format="json_object",
            temperature=0.0,
            max_tokens=512,
        )
    except AiError:
        return {f: None for f in fields}
    txt = resp.text.strip()
    if txt.startswith("```"):
        txt = txt.strip("`")
        if txt.lower().startswith("json"):
            txt = txt[4:].strip()
    try:
        obj = json.loads(txt)
        return {f: obj.get(f) for f in fields}
    except json.JSONDecodeError:
        return {f: None for f in fields}


class LlmExtractStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        from dig.ai.config import load_config
        from dig.storage.db import SessionLocal

        df = inputs["in"]
        text_col = params["text_column"]
        fields_raw = params.get("fields", "")
        fields = [s.strip() for s in str(fields_raw).split(",") if s.strip()]
        if not fields:
            raise ValueError("llm_extract: at least one field required")
        context = params.get("context", "Extract the listed fields from the text.")

        async def _run() -> list[dict[str, Any]]:
            async with SessionLocal() as session:
                cfg = await load_config(session)
            if not cfg.enabled:
                raise ValueError("llm_extract: AI is disabled — enable it in Settings → AI")
            rows: list[dict[str, Any]] = []
            texts = df[text_col].to_list()
            for i in range(0, len(texts), 8):
                chunk = texts[i:i + 8]
                tasks = [_extract_one(cfg, str(t) if t is not None else "", fields, context) for t in chunk]
                rows.extend(await asyncio.gather(*tasks))
            return rows

        extracted = asyncio.run(_run())
        # Build new columns one per field
        cols_to_add = []
        for f in fields:
            cols_to_add.append(pl.Series(name=f, values=[r.get(f) for r in extracted]))
        return PolarsResult(output=df.with_columns(cols_to_add))


step = LlmExtractStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
