"""icd10_lookup — bundled mini ICD-10 lookup table."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


# Mini bundled lookup — most common chronic / acute codes.
_ICD10 = {
    "A09":   ("Infectious gastroenteritis", "Certain infectious and parasitic diseases"),
    "A41.9": ("Sepsis, unspecified", "Certain infectious and parasitic diseases"),
    "C50.9": ("Malignant neoplasm of breast", "Neoplasms"),
    "C61":   ("Malignant neoplasm of prostate", "Neoplasms"),
    "C78.0": ("Secondary malignant neoplasm of lung", "Neoplasms"),
    "D50.9": ("Iron deficiency anaemia", "Diseases of the blood"),
    "E11.9": ("Type 2 diabetes mellitus", "Endocrine, nutritional and metabolic"),
    "E11.65": ("Type 2 diabetes with hyperglycaemia", "Endocrine, nutritional and metabolic"),
    "E66.9": ("Obesity, unspecified", "Endocrine, nutritional and metabolic"),
    "F32.9": ("Major depressive disorder, single episode", "Mental and behavioural"),
    "F41.1": ("Generalized anxiety disorder", "Mental and behavioural"),
    "G47.33": ("Obstructive sleep apnea", "Diseases of the nervous system"),
    "I10":   ("Essential primary hypertension", "Diseases of the circulatory system"),
    "I21.9": ("Acute myocardial infarction, unspecified", "Diseases of the circulatory system"),
    "I25.10": ("Coronary artery disease without angina", "Diseases of the circulatory system"),
    "I48.91": ("Atrial fibrillation, unspecified", "Diseases of the circulatory system"),
    "I50.9": ("Heart failure, unspecified", "Diseases of the circulatory system"),
    "J18.9": ("Pneumonia, unspecified organism", "Diseases of the respiratory system"),
    "J44.9": ("COPD, unspecified", "Diseases of the respiratory system"),
    "J45.909": ("Asthma, unspecified, uncomplicated", "Diseases of the respiratory system"),
    "K21.9": ("Gastro-oesophageal reflux disease", "Diseases of the digestive system"),
    "K57.30": ("Diverticulosis of large intestine", "Diseases of the digestive system"),
    "K76.0": ("Fatty liver, not elsewhere classified", "Diseases of the digestive system"),
    "L70.0": ("Acne vulgaris", "Diseases of the skin"),
    "M17.9": ("Osteoarthritis of knee, unspecified", "Diseases of the musculoskeletal system"),
    "M54.5": ("Low back pain", "Diseases of the musculoskeletal system"),
    "M81.0": ("Postmenopausal osteoporosis without fracture", "Diseases of the musculoskeletal system"),
    "N17.9": ("Acute kidney failure, unspecified", "Diseases of the genitourinary system"),
    "N18.6": ("End-stage renal disease", "Diseases of the genitourinary system"),
    "N39.0": ("Urinary tract infection, site not specified", "Diseases of the genitourinary system"),
    "O80":   ("Encounter for full-term uncomplicated delivery", "Pregnancy, childbirth and the puerperium"),
    "P07.30": ("Preterm newborn, unspecified weight", "Conditions originating in the perinatal period"),
    "Q21.0": ("Ventricular septal defect", "Congenital malformations"),
    "R07.9": ("Chest pain, unspecified", "Symptoms, signs and abnormal findings"),
    "R10.9": ("Unspecified abdominal pain", "Symptoms, signs and abnormal findings"),
    "R51":   ("Headache", "Symptoms, signs and abnormal findings"),
    "R55":   ("Syncope and collapse", "Symptoms, signs and abnormal findings"),
    "S06.0": ("Concussion", "Injury, poisoning"),
    "S72.001A": ("Femoral fracture, unspecified, initial encounter", "Injury, poisoning"),
    "T84.84": ("Pain due to internal orthopaedic prosthetic devices", "Injury, poisoning"),
    "V03.10": ("Pedestrian struck by car, traffic", "External causes"),
    "Z00.00": ("General adult medical examination", "Factors influencing health status"),
    "Z51.11": ("Encounter for antineoplastic chemotherapy", "Factors influencing health status"),
    "Z79.4": ("Long term use of insulin", "Factors influencing health status"),
}


class Icd10LookupStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        col = params["codeColumn"]
        codes = df[col].to_list()
        descs = []
        chapters = []
        for c in codes:
            if c is None:
                descs.append(None); chapters.append(None); continue
            entry = _ICD10.get(str(c).strip().upper())
            if entry:
                descs.append(entry[0]); chapters.append(entry[1])
            else:
                descs.append(None); chapters.append(None)
        out = df.with_columns([
            pl.Series("icd_description", descs),
            pl.Series("icd_chapter", chapters),
        ])
        return PolarsResult(output=out)


step = Icd10LookupStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
