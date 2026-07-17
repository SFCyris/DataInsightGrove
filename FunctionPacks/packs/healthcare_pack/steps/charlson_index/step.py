"""charlson_index — per-patient Quan / Deyo Charlson score."""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


# Simplified Quan/Deyo Charlson mapping: (condition, ICD-10 prefix list, weight).
_CHARLSON = [
    ("myocardial_infarction", ["I21", "I22", "I252"], 1),
    ("congestive_heart_failure", ["I50"], 1),
    ("peripheral_vascular", ["I70", "I71"], 1),
    ("cerebrovascular", ["I60", "I61", "I62", "I63", "I64", "G45"], 1),
    ("dementia", ["F00", "F01", "F02", "F03", "G30"], 1),
    ("chronic_pulmonary", ["J40", "J41", "J42", "J43", "J44", "J45", "J47"], 1),
    ("rheumatic", ["M05", "M06", "M315"], 1),
    ("peptic_ulcer", ["K25", "K26", "K27", "K28"], 1),
    ("mild_liver", ["K70", "K71", "K73", "K74"], 1),
    ("diabetes_no_complications", ["E10", "E11", "E12", "E13", "E14"], 1),
    ("diabetes_with_complications", ["E102", "E112"], 2),
    ("hemiplegia", ["G81", "G82"], 2),
    ("renal_disease", ["N03", "N05", "N18", "N19"], 2),
    ("any_malignancy", ["C0", "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8"], 2),
    ("moderate_severe_liver", ["K72"], 3),
    ("metastatic_solid_tumor", ["C77", "C78", "C79"], 6),
    ("aids", ["B20", "B21", "B22", "B24"], 6),
]


class CharlsonIndexStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        p = params["patientColumn"]; c = params["codeColumn"]
        per_patient: dict[str, set[str]] = defaultdict(set)
        for pid, code in zip(df[p].to_list(), df[c].to_list()):
            if code is None: continue
            code_s = str(code).strip().upper()
            for name, prefixes, _w in _CHARLSON:
                if any(code_s.startswith(pre) for pre in prefixes):
                    per_patient[pid].add(name)
                    break
        rows = []
        for pid, conditions in per_patient.items():
            score = sum(w for name, _, w in _CHARLSON if name in conditions)
            rows.append({"patient_id": pid, "charlson_score": score,
                          "n_conditions": len(conditions),
                          "conditions": sorted(conditions)})
        out = pl.DataFrame(rows).sort("charlson_score", descending=True)
        return PolarsResult(output=out)


step = CharlsonIndexStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
