"""language_detect — ISO-639 language detection per text row."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class LanguageDetectStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        try:
            from langdetect import detect_langs, DetectorFactory
            DetectorFactory.seed = 42
        except ImportError as e:
            raise ImportError(
                "language_detect requires langdetect. Install via "
                "`pip install langdetect`. See INTERNAL_NOTES.md."
            ) from e
        df = inputs["in"]
        col = params["textColumn"]
        langs = []; confs = []
        for t in df[col].to_list():
            text = str(t or "").strip()
            if not text:
                langs.append(None); confs.append(None); continue
            try:
                detected = detect_langs(text)[0]
                langs.append(detected.lang); confs.append(float(detected.prob))
            except Exception:
                langs.append(None); confs.append(None)
        out = df.with_columns([
            pl.Series("language", langs),
            pl.Series("language_confidence", confs),
        ])
        return PolarsResult(output=out)


step = LanguageDetectStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
