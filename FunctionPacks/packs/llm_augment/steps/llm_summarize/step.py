from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


async def _summarize_one(cfg, text: str, max_words: int) -> str | None:
    from dig.ai.client import chat, AiError

    if not text.strip():
        return None
    sys_prompt = (
        f"Summarise the user's text in at most {max_words} words. "
        "Plain text only — no Markdown, no bullets, no quoting."
    )
    try:
        resp = await chat(
            cfg,
            messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": text[:8000]}],
            temperature=0.2,
            max_tokens=max(64, max_words * 6),
        )
    except AiError:
        return None
    return resp.text.strip()


class LlmSummarizeStep(Step):
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
        max_words = int(params.get("max_words", 30))
        out_col = params.get("output_column", "summary")

        async def _run() -> list[str | None]:
            async with SessionLocal() as session:
                cfg = await load_config(session)
            if not cfg.enabled:
                raise ValueError("llm_summarize: AI is disabled — enable it in Settings → AI")
            results: list[str | None] = []
            texts = df[text_col].to_list()
            for i in range(0, len(texts), 8):
                chunk = texts[i:i + 8]
                tasks = [_summarize_one(cfg, str(t) if t is not None else "", max_words) for t in chunk]
                results.extend(await asyncio.gather(*tasks))
            return results

        summaries = asyncio.run(_run())
        return PolarsResult(output=df.with_columns(pl.Series(name=out_col, values=summaries)))


step = LlmSummarizeStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
