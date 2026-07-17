"""ner_spacy — spaCy named entity recognition."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class NerSpacyStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        try:
            import spacy
            try:
                nlp = spacy.load("en_core_web_sm")
            except OSError as e:
                raise ImportError(
                    "ner_spacy: spaCy is installed but the en_core_web_sm model is not. "
                    "Install via `python -m spacy download en_core_web_sm`. See INTERNAL_NOTES.md."
                ) from e
        except ImportError as e:
            raise ImportError(
                "ner_spacy requires spacy + en_core_web_sm. See INTERNAL_NOTES.md."
            ) from e
        df = inputs["in"]
        col = params["textColumn"]
        all_entities, all_types = [], []
        for text in df[col].to_list():
            if text is None:
                all_entities.append([]); all_types.append([]); continue
            doc = nlp(str(text))
            all_entities.append([ent.text for ent in doc.ents])
            all_types.append([ent.label_ for ent in doc.ents])
        out = df.with_columns([
            pl.Series("entities", all_entities),
            pl.Series("entity_types", all_types),
        ])
        return PolarsResult(output=out)


step = NerSpacyStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
