"""Embed text via an OpenAI-compatible /v1/embeddings endpoint.

Supports any provider speaking the OpenAI embeddings spec — OpenAI proper,
Ollama (local, free), Together, Groq, OpenRouter, vLLM, llama.cpp. Returns
a `DOUBLE[N]` vector column compatible with the `vector_similarity` step.

Batching:
  - Texts are sent `batchSize` at a time.
  - Empty/NULL texts get a NULL vector (no API call wasted on them).
  - Rate-limit / network errors raise after a single retry with backoff;
    we don't paper over because partial-success would leave NULL gaps in
    the output that look like data, not errors.

Cost discipline:
  - The full input column is materialized so we know upfront how many
    tokens we're about to send. Caller (the user) sees the row count in
    the preview before clicking Run.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import socket
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step

log = logging.getLogger(__name__)


def _is_private_address(host: str) -> bool:
    """Same private-network guard as the REST + HTTPS connectors."""
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, socket.herror, OSError):
        return True
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if (
            ip.is_loopback or ip.is_private or ip.is_link_local
            or ip.is_multicast or ip.is_reserved or ip.is_unspecified
        ):
            return True
    return False


def _assert_endpoint_safe(endpoint: str) -> None:
    """Reject schemes other than http/https + private destinations so the
    API key in the ``Authorization`` header can't be exfiltrated to a
    cloud-metadata address or sibling service. The user can override
    with ``DIG_EMBED_ALLOW_PRIVATE=1`` to point at a local Ollama, etc."""
    parts = urlsplit(endpoint)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError(
            f"embed_text: endpoint scheme {scheme!r} not allowed; "
            "only http and https are permitted",
        )
    if not parts.hostname:
        raise ValueError(f"embed_text: no host in endpoint {endpoint!r}")
    if os.environ.get("DIG_EMBED_ALLOW_PRIVATE") == "1":
        return
    if _is_private_address(parts.hostname):
        raise ValueError(
            f"embed_text: endpoint host {parts.hostname!r} resolves to a "
            "private / loopback / link-local address. Set "
            "DIG_EMBED_ALLOW_PRIVATE=1 on a trusted host to allow local "
            "Ollama / vLLM targets.",
        )


def _embed_batch(
    texts: list[str],
    *,
    endpoint: str,
    model: str,
    api_key: str | None,
    timeout_s: float = 60.0,
) -> list[list[float]]:
    """Synchronous embeddings call against an OpenAI-compat endpoint.
    Returns one vector per input (in the same order).

    The endpoint format is fixed by the OpenAI API spec:
      POST /v1/embeddings  {model, input: [text1, text2, ...]}
      → {data: [{embedding: [...], index: 0}, ...]}
    """
    _assert_endpoint_safe(endpoint)
    import httpx
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {"model": model, "input": texts}
    # Disable redirects so a malicious server can't 302 to a private host
    # AFTER we already attached the Authorization header.
    with httpx.Client(timeout=timeout_s, follow_redirects=False) as client:
        r = client.post(endpoint, json=payload, headers=headers)
    if r.status_code == 429:
        # One retry with linear backoff for rate limits.
        time.sleep(2.0)
        with httpx.Client(timeout=timeout_s, follow_redirects=False) as client:
            r = client.post(endpoint, json=payload, headers=headers)
    if not r.is_success:
        raise RuntimeError(
            f"embeddings endpoint returned HTTP {r.status_code}: {r.text[:300]}",
        )
    body = r.json()
    items = body.get("data") or []
    if len(items) != len(texts):
        raise RuntimeError(
            f"embeddings endpoint returned {len(items)} vectors for {len(texts)} inputs",
        )
    # Sort by index in case the server doesn't preserve request order.
    items.sort(key=lambda d: d.get("index", 0))
    return [list(d["embedding"]) for d in items]


class EmbedTextStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        df = inputs["in"]
        text_col = params["textColumn"]
        out_col = params["outputColumn"]
        endpoint = params.get("endpoint") or "https://api.openai.com/v1/embeddings"
        model = params.get("model") or "text-embedding-3-small"
        api_key = (params.get("apiKey") or "") or None
        batch_size = max(1, min(int(params.get("batchSize") or 100), 2048))

        if text_col not in df.columns:
            raise ValueError(f"text column {text_col!r} not in input")

        # Pull text into a Python list. NULL/empty rows get a placeholder
        # so we don't waste API budget on them, and the output is NULL.
        texts: list[str | None] = list(df.get_column(text_col).cast(pl.Utf8).to_list())
        embed_inputs: list[tuple[int, str]] = [
            (i, t) for i, t in enumerate(texts)
            if t is not None and t.strip()
        ]

        embeddings: list[list[float] | None] = [None] * len(texts)
        for batch_start in range(0, len(embed_inputs), batch_size):
            batch = embed_inputs[batch_start : batch_start + batch_size]
            batch_texts = [t for _, t in batch]
            try:
                vecs = _embed_batch(
                    batch_texts,
                    endpoint=endpoint,
                    model=model,
                    api_key=api_key,
                )
            except Exception as e:
                # Fail loudly — partial embedding output is worse than none.
                # The user can re-run with smaller batches.
                raise RuntimeError(
                    f"embed_text failed at batch {batch_start // batch_size + 1}: {e}",
                ) from e
            for (orig_idx, _), vec in zip(batch, vecs):
                embeddings[orig_idx] = vec

        # Detect dimension from the first non-null embedding for the
        # output schema. If all rows were null, we still emit a list column
        # (empty arrays) so downstream steps don't break.
        dim = next((len(v) for v in embeddings if v is not None), 0)
        if dim == 0:
            log.warning("embed_text: all input texts were null/empty — output is all NULL")

        out_series = pl.Series(out_col, embeddings, dtype=pl.List(pl.Float64))
        result_df = df.with_columns(out_series)
        return PolarsResult(
            output=result_df,
            artifacts=[{
                "kind": "embedding_summary",
                "label": "Embeddings",
                "model": model,
                "endpoint": endpoint.replace(api_key, "***") if api_key else endpoint,
                "rows_embedded": sum(1 for v in embeddings if v is not None),
                "rows_skipped_null": sum(1 for v in embeddings if v is None),
                "dimension": dim,
            }],
        )

    def infer_schema(
        self,
        input_schemas: dict[str, dict[str, str]],
        params: dict[str, Any],
    ) -> dict[str, str]:
        s = dict(input_schemas.get("in", {}))
        out = params.get("outputColumn")
        if out:
            s[str(out)] = "vector"
        return s


step = EmbedTextStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
