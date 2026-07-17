from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


_SYSTEM = (
    "You are a strict classifier. The user gives you a list of allowed labels "
    "and a text. Respond with JSON only, no prose, no Markdown:\n"
    "{\"label\": \"<one of the allowed labels>\", \"confidence\": \"high|medium|low\"}\n"
    "If the text doesn't fit any label cleanly, pick the closest and use confidence=low."
)


async def _classify_one(cfg, text: str, labels: list[str], context: str) -> tuple[str | None, str]:
    from dig.ai.client import chat, AiError

    user = (
        f"Task: {context}\n\n"
        f"Allowed labels: {', '.join(labels)}\n\n"
        f"Text:\n{text[:4000]}"
    )
    try:
        resp = await chat(
            cfg,
            messages=[{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
            response_format="json_object",
            temperature=0.1,
            max_tokens=128,
        )
    except AiError:
        return (None, "low")
    txt = resp.text.strip()
    if txt.startswith("```"):
        txt = txt.strip("`")
        if txt.lower().startswith("json"):
            txt = txt[4:].strip()
    try:
        obj = json.loads(txt)
        label = obj.get("label")
        if label not in labels:
            return (None, "low")
        conf = obj.get("confidence", "medium")
        if conf not in ("high", "medium", "low"):
            conf = "medium"
        return (label, conf)
    except json.JSONDecodeError:
        return (None, "low")


class LlmClassifyStep(Step):
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
        raw_labels = params.get("labels", "")
        labels = [s.strip() for s in str(raw_labels).split(",") if s.strip()]
        if not labels:
            raise ValueError("llm_classify: at least one label required")
        context = params.get("context", "Classify the text into one of the labels.")
        out_col = params.get("output_column", "label")

        async def _run() -> tuple[list[str | None], list[str]]:
            async with SessionLocal() as session:
                cfg = await load_config(session)
            if not cfg.enabled:
                raise ValueError("llm_classify: AI is disabled — enable it in Settings → AI")
            results: list[tuple[str | None, str]] = []
            # Run in parallel batches of 8 to keep memory + provider rate limits sane.
            batch = 8
            texts = df[text_col].to_list()
            for i in range(0, len(texts), batch):
                chunk = texts[i:i + batch]
                tasks = [
                    _classify_one(cfg, str(t) if t is not None else "", labels, context)
                    for t in chunk
                ]
                results.extend(await asyncio.gather(*tasks))
            return [r[0] for r in results], [r[1] for r in results]

        labels_out, conf_out = asyncio.run(_run())
        return PolarsResult(output=df.with_columns([
            pl.Series(name=out_col, values=labels_out),
            pl.Series(name=f"{out_col}_confidence", values=conf_out),
        ]))


step = LlmClassifyStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
