"""keyword_rake_yake — unsupervised keyword extraction."""
from __future__ import annotations
import json
import re
from collections import defaultdict
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


_STOPS = set("""a an and are as at be by for from has have he in is it its of on or that the their this to was were will with you your i""".split())
_WORD_RE = re.compile(r"\b[a-zA-Z]{2,}\b")


def _rake(text: str, top_k: int) -> list[str]:
    """Minimal RAKE: split on stops + punctuation, score each phrase."""
    text = text.lower()
    # Split on stopwords + punctuation.
    tokens = _WORD_RE.findall(text)
    phrases: list[list[str]] = []
    cur: list[str] = []
    for tok in tokens:
        if tok in _STOPS:
            if cur: phrases.append(cur); cur = []
        else:
            cur.append(tok)
    if cur: phrases.append(cur)
    # Word-frequency + word-degree.
    word_freq: dict[str, int] = defaultdict(int)
    word_deg: dict[str, int] = defaultdict(int)
    for ph in phrases:
        deg = len(ph) - 1
        for w in ph:
            word_freq[w] += 1; word_deg[w] += deg + 1
    word_score = {w: word_deg[w] / word_freq[w] for w in word_freq}
    # Phrase score = sum of word scores.
    scored = [(" ".join(ph), sum(word_score.get(w, 0) for w in ph)) for ph in phrases]
    scored.sort(key=lambda x: -x[1])
    seen: set[str] = set()
    out: list[str] = []
    for ph, _ in scored:
        if ph not in seen:
            seen.add(ph); out.append(ph)
        if len(out) >= top_k: break
    return out


def _yake(text: str, top_k: int) -> list[str]:
    """Minimal YAKE-style: position + casing + co-occurrence weighting."""
    text_low = text.lower()
    tokens = _WORD_RE.findall(text_low)
    if not tokens: return []
    freq: dict[str, int] = defaultdict(int)
    pos: dict[str, int] = {}
    for i, t in enumerate(tokens):
        freq[t] += 1
        if t not in pos: pos[t] = i
    # Score: lower is better — normalised position * 1/freq.
    scored = sorted(
        ((t, pos[t] / max(1, len(tokens)) * (1 / freq[t])) for t in freq if t not in _STOPS),
        key=lambda x: x[1],
    )
    return [t for t, _ in scored[:top_k]]


class KeywordRakeYakeStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        col = params["textColumn"]
        algo = (params.get("algorithm") or "rake").lower()
        top_k = int(params.get("topK", 5))
        keywords = []
        for t in df[col].to_list():
            text = str(t or "")
            if not text:
                keywords.append([]); continue
            if algo == "yake":
                keywords.append(_yake(text, top_k))
            else:
                keywords.append(_rake(text, top_k))
        out = df.with_columns(pl.Series("keywords", keywords))
        return PolarsResult(output=out)


step = KeywordRakeYakeStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
