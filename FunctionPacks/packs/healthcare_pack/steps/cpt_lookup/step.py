"""cpt_lookup — bundled mini CPT lookup table."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


_CPT = {
    "99213": ("Office visit, established patient, low complexity", "E&M"),
    "99214": ("Office visit, established patient, moderate complexity", "E&M"),
    "99215": ("Office visit, established patient, high complexity", "E&M"),
    "99203": ("Office visit, new patient, low complexity", "E&M"),
    "99281": ("Emergency department visit, low complexity", "E&M"),
    "99285": ("Emergency department visit, high complexity", "E&M"),
    "27447": ("Total knee arthroplasty", "Surgery"),
    "27130": ("Total hip arthroplasty", "Surgery"),
    "44970": ("Laparoscopic appendectomy", "Surgery"),
    "47562": ("Laparoscopic cholecystectomy", "Surgery"),
    "33533": ("CABG, single coronary venous graft", "Surgery"),
    "70450": ("CT head without contrast", "Radiology"),
    "70551": ("MRI brain without contrast", "Radiology"),
    "71045": ("Chest X-ray, single view", "Radiology"),
    "71046": ("Chest X-ray, two views", "Radiology"),
    "76700": ("Abdominal ultrasound, complete", "Radiology"),
    "80048": ("Basic metabolic panel", "Pathology/Lab"),
    "80050": ("General health panel", "Pathology/Lab"),
    "80053": ("Comprehensive metabolic panel", "Pathology/Lab"),
    "85025": ("Complete blood count with differential", "Pathology/Lab"),
    "83036": ("Hemoglobin A1c", "Pathology/Lab"),
    "84443": ("Thyroid stimulating hormone", "Pathology/Lab"),
    "87086": ("Urine culture, quantitative colony count", "Pathology/Lab"),
    "90834": ("Psychotherapy, 45 minutes", "Mental Health"),
    "90837": ("Psychotherapy, 60 minutes", "Mental Health"),
    "90791": ("Psychiatric diagnostic evaluation", "Mental Health"),
    "97110": ("Therapeutic exercise, 15 min", "PT/OT"),
    "97140": ("Manual therapy, 15 min", "PT/OT"),
    "G0438": ("Annual wellness visit, initial", "Preventive"),
    "G0439": ("Annual wellness visit, subsequent", "Preventive"),
    "90471": ("Immunisation administration", "Preventive"),
    "11042": ("Debridement, subcutaneous tissue", "Surgery"),
}


class CptLookupStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        col = params["codeColumn"]
        descs, cats = [], []
        for v in df[col].to_list():
            if v is None:
                descs.append(None); cats.append(None); continue
            entry = _CPT.get(str(v).strip())
            if entry:
                descs.append(entry[0]); cats.append(entry[1])
            else:
                descs.append(None); cats.append(None)
        out = df.with_columns([
            pl.Series("cpt_description", descs),
            pl.Series("service_category", cats),
        ])
        return PolarsResult(output=out)


step = CptLookupStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
