#!/usr/bin/env python3
"""Generate the healthcare demo: 5 interrelated CSVs simulating a hospital's
clinical, lab, and encounter records.

Tables (every dataset 5k–10k rows × 5–10 columns):
  - healthcare-patients-demo.csv    (≈ 6,000 rows × 9 cols)
  - healthcare-encounters-demo.csv  (≈ 8,500 rows × 9 cols)
  - healthcare-lab-orders-demo.csv  (≈ 9,500 rows × 7 cols)
  - healthcare-lab-results-demo.csv (≈ 9,800 rows × 8 cols)
  - healthcare-diagnoses-demo.csv   (≈ 7,500 rows × 6 cols)

The numbers are stylized so the demo pipeline can:
  - join all five tables in a sensible chain (patients → encounters → orders
    → results, plus diagnoses linked to encounters),
  - surface abnormal-result + length-of-stay + department signals,
  - present a 30+ step interwoven pipeline ending in 5 different charts.

Deterministic — seed = 42. Stdlib only (random / csv / datetime).

Run:
  python samples/_generators/healthcare_demo.py
"""

from __future__ import annotations

import csv
import os
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

SEED = 42
REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "samples"

START_DATE = datetime(2025, 11, 1)
END_DATE = datetime(2026, 5, 1)

# ---- entity counts ------------------------------------------------------

N_PATIENTS = 6_000
N_ENCOUNTERS = 8_500
N_LAB_ORDERS = 9_500
N_LAB_RESULTS = 9_800
N_DIAGNOSES = 7_500

DEPARTMENTS = [
    "Cardiology", "Emergency", "Internal Medicine", "Oncology",
    "Pediatrics", "Surgery", "OB-GYN", "Neurology",
    "Orthopedics", "Pulmonology", "Radiology", "Endocrinology",
]
ENCOUNTER_TYPES = ["inpatient", "outpatient", "emergency", "telehealth"]
ENCOUNTER_TYPE_WEIGHTS = [0.18, 0.55, 0.20, 0.07]
DISCHARGE_DISPOSITIONS = ["home", "rehab", "skilled-nursing", "expired", "left-AMA", "transferred"]
DISCHARGE_WEIGHTS = [0.78, 0.10, 0.06, 0.01, 0.02, 0.03]
SEXES = ["F", "M", "X"]
SEX_WEIGHTS = [0.51, 0.47, 0.02]
BLOOD_TYPES = ["O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-"]
BLOOD_WEIGHTS = [0.38, 0.07, 0.34, 0.06, 0.09, 0.02, 0.03, 0.01]

# Lab tests — code, name, unit, low, high.
LAB_TESTS = [
    ("CBC-WBC",  "WBC",                "10^9/L", 4.0,  11.0),
    ("CBC-RBC",  "RBC",                "10^12/L", 4.2, 5.9),
    ("CBC-HGB",  "Hemoglobin",         "g/dL",   12.0, 17.5),
    ("CBC-PLT",  "Platelets",          "10^9/L", 150,  400),
    ("CMP-NA",   "Sodium",             "mmol/L", 135,  145),
    ("CMP-K",    "Potassium",          "mmol/L", 3.5,  5.1),
    ("CMP-CL",   "Chloride",           "mmol/L", 96,   106),
    ("CMP-CO2",  "CO2",                "mmol/L", 22,   29),
    ("CMP-BUN",  "BUN",                "mg/dL",  7,    20),
    ("CMP-CR",   "Creatinine",         "mg/dL",  0.6,  1.3),
    ("CMP-GLU",  "Glucose",            "mg/dL",  70,   99),
    ("LFT-ALT",  "ALT",                "U/L",    7,    56),
    ("LFT-AST",  "AST",                "U/L",    10,   40),
    ("LFT-ALP",  "Alk Phos",           "U/L",    44,   147),
    ("LFT-TBIL", "Total Bilirubin",    "mg/dL",  0.1,  1.2),
    ("LIPID-TC", "Total Cholesterol",  "mg/dL",  100,  200),
    ("LIPID-LDL", "LDL",               "mg/dL",  0,    100),
    ("LIPID-HDL", "HDL",               "mg/dL",  40,   60),
    ("LIPID-TG", "Triglycerides",      "mg/dL",  0,    150),
    ("HBA1C",    "HbA1c",              "%",      4.0,  5.7),
    ("TSH",      "TSH",                "mIU/L",  0.4,  4.0),
    ("TROP",     "Troponin I",         "ng/mL",  0.0,  0.04),
    ("CRP",      "C-Reactive Protein", "mg/L",   0.0,  3.0),
]

PRIORITIES = ["routine", "urgent", "stat"]
PRIORITY_WEIGHTS = [0.78, 0.16, 0.06]

ICD_CODES = [
    ("E11.9",  "Type 2 diabetes mellitus without complications"),
    ("I10",    "Essential hypertension"),
    ("J45.909","Unspecified asthma, uncomplicated"),
    ("F32.9",  "Major depressive disorder, single episode"),
    ("M54.5",  "Low back pain"),
    ("N39.0",  "Urinary tract infection"),
    ("J20.9",  "Acute bronchitis"),
    ("R51",    "Headache"),
    ("R10.9",  "Unspecified abdominal pain"),
    ("K21.9",  "GERD without esophagitis"),
    ("M25.50", "Pain in unspecified joint"),
    ("E78.5",  "Hyperlipidemia"),
    ("Z00.00", "General adult medical exam"),
    ("R07.9",  "Chest pain, unspecified"),
    ("J06.9",  "Acute upper respiratory infection"),
    ("I48.91", "Atrial fibrillation"),
    ("E03.9",  "Hypothyroidism"),
    ("F41.1",  "Generalized anxiety disorder"),
    ("M79.10", "Myalgia, unspecified site"),
    ("L70.0",  "Acne vulgaris"),
    ("I25.10", "Atherosclerotic heart disease"),
    ("E66.9",  "Obesity, unspecified"),
    ("J44.9",  "COPD, unspecified"),
]


# ---- helpers ------------------------------------------------------------

def weighted_choice(rng: random.Random, items: list, weights: list) -> object:
    return rng.choices(items, weights=weights, k=1)[0]


def random_dt(rng: random.Random, start: datetime, end: datetime) -> datetime:
    span = int((end - start).total_seconds())
    return start + timedelta(seconds=rng.randint(0, span))


def fmt_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def fmt_date(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


# ---- patients -----------------------------------------------------------

def gen_patients(rng: random.Random) -> list[dict]:
    rows: list[dict] = []
    for i in range(N_PATIENTS):
        pid = f"PAT-{i+1:06d}"
        sex = weighted_choice(rng, SEXES, SEX_WEIGHTS)
        # Bias age toward older — most encounters are 40+.
        age = max(0, min(102, int(rng.gauss(54, 22))))
        # Height + weight by sex (rough US-population averages).
        if sex == "M":
            height = round(rng.gauss(176, 7), 1)
            weight = round(rng.gauss(86, 16), 1)
        elif sex == "F":
            height = round(rng.gauss(162, 7), 1)
            weight = round(rng.gauss(72, 14), 1)
        else:
            height = round(rng.gauss(170, 9), 1)
            weight = round(rng.gauss(78, 16), 1)
        bmi = round(weight / max(height / 100, 0.5) ** 2, 1)
        blood = weighted_choice(rng, BLOOD_TYPES, BLOOD_WEIGHTS)
        smoker = "Y" if rng.random() < 0.18 else "N"
        # 1.5% have a missing primary diagnosis to exercise null-handling.
        primary_dx = "" if rng.random() < 0.015 else rng.choice(ICD_CODES)[0]
        # Insurance: weighted public/commercial/self-pay/medicare.
        insurance = rng.choices(
            ["medicare", "medicaid", "commercial", "self-pay"],
            weights=[0.35, 0.20, 0.40, 0.05], k=1,
        )[0]
        rows.append({
            "patient_id": pid,
            "sex": sex,
            "age": age,
            "weight_kg": weight,
            "height_cm": height,
            "bmi": bmi,
            "blood_type": blood,
            "smoker_flag": smoker,
            "insurance_kind": insurance,
            "primary_dx_code": primary_dx,
        })
    return rows


# ---- encounters --------------------------------------------------------

def gen_encounters(rng: random.Random, patients: list[dict]) -> list[dict]:
    rows: list[dict] = []
    pids = [p["patient_id"] for p in patients]
    for i in range(N_ENCOUNTERS):
        eid = f"ENC-{i+1:07d}"
        pid = rng.choice(pids)
        etype = weighted_choice(rng, ENCOUNTER_TYPES, ENCOUNTER_TYPE_WEIGHTS)
        dept = rng.choice(DEPARTMENTS)
        ts = random_dt(rng, START_DATE, END_DATE)
        # length-of-stay (hours) by encounter type.
        if etype == "inpatient":
            los_hours = round(rng.gauss(96, 60), 1)
            los_hours = max(12.0, min(720.0, los_hours))
        elif etype == "emergency":
            los_hours = round(max(0.5, rng.gauss(4.5, 2.5)), 1)
        elif etype == "outpatient":
            los_hours = round(max(0.25, rng.gauss(1.0, 0.4)), 1)
        else:  # telehealth
            los_hours = round(max(0.1, rng.gauss(0.4, 0.2)), 1)
        disposition = weighted_choice(rng, DISCHARGE_DISPOSITIONS, DISCHARGE_WEIGHTS)
        # Charge in USD (roughly proportional to LOS + dept multiplier).
        dept_mult = {"Cardiology": 2.0, "Oncology": 2.4, "Surgery": 3.1, "Emergency": 1.4}.get(dept, 1.0)
        charge = round(max(50, los_hours * 220 * dept_mult * (0.7 + rng.random() * 0.6)), 2)
        # Simulated readmission flag (8% of encounters were within 30d of a previous one).
        readmission = "Y" if rng.random() < 0.08 else "N"
        rows.append({
            "encounter_id": eid,
            "patient_id": pid,
            "encounter_type": etype,
            "department": dept,
            "encounter_date": fmt_dt(ts),
            "length_of_stay_hours": los_hours,
            "discharge_disposition": disposition,
            "charge_usd": charge,
            "readmission_flag": readmission,
        })
    return rows


# ---- lab orders + results ----------------------------------------------

def gen_lab_orders(rng: random.Random, encounters: list[dict]) -> list[dict]:
    rows: list[dict] = []
    eids = [e["encounter_id"] for e in encounters]
    for i in range(N_LAB_ORDERS):
        oid = f"ORD-{i+1:07d}"
        eid = rng.choice(eids)
        test = rng.choice(LAB_TESTS)
        priority = weighted_choice(rng, PRIORITIES, PRIORITY_WEIGHTS)
        ordered_at = random_dt(rng, START_DATE, END_DATE)
        provider = f"PROV-{rng.randint(1, 480):04d}"
        # 2.5% orders are cancelled (no result downstream).
        cancelled = "Y" if rng.random() < 0.025 else "N"
        rows.append({
            "order_id": oid,
            "encounter_id": eid,
            "test_code": test[0],
            "ordered_at": fmt_dt(ordered_at),
            "priority": priority,
            "ordering_provider_id": provider,
            "cancelled_flag": cancelled,
        })
    return rows


def gen_lab_results(rng: random.Random, orders: list[dict]) -> list[dict]:
    rows: list[dict] = []
    valid_orders = [o for o in orders if o["cancelled_flag"] == "N"]
    rng.shuffle(valid_orders)
    test_lookup = {t[0]: t for t in LAB_TESTS}
    for i in range(min(N_LAB_RESULTS, len(valid_orders))):
        rid = f"RES-{i+1:07d}"
        order = valid_orders[i]
        test = test_lookup[order["test_code"]]
        _, _, unit, low, high = test
        # Result drawn around the reference range — about 22% are abnormal.
        if rng.random() < 0.22:
            # Abnormal: skew above or below.
            if rng.random() < 0.55:
                value = round(high + rng.uniform(0.05 * (high - low + 1), 0.45 * (high - low + 1)), 3)
                flag = "H"
            else:
                value = round(max(0, low - rng.uniform(0.05 * (high - low + 1), 0.45 * (high - low + 1))), 3)
                flag = "L"
        else:
            value = round(rng.uniform(low, high), 3)
            flag = "N"
        # ~1% of results have a delayed turnaround.
        ordered_dt = datetime.fromisoformat(order["ordered_at"])
        if rng.random() < 0.01:
            tat_minutes = rng.randint(720, 2880)
        else:
            tat_minutes = rng.randint(20, 240)
        resulted_at = ordered_dt + timedelta(minutes=tat_minutes)
        rows.append({
            "result_id": rid,
            "order_id": order["order_id"],
            "test_code": order["test_code"],
            "value_numeric": value,
            "value_unit": unit,
            "reference_low": low,
            "reference_high": high,
            "abnormal_flag": flag,
            "resulted_at": fmt_dt(resulted_at),
        })
    return rows


# ---- diagnoses ---------------------------------------------------------

def gen_diagnoses(rng: random.Random, encounters: list[dict]) -> list[dict]:
    rows: list[dict] = []
    eids = [e["encounter_id"] for e in encounters]
    for i in range(N_DIAGNOSES):
        did = f"DX-{i+1:07d}"
        eid = rng.choice(eids)
        code, name = rng.choice(ICD_CODES)
        # Each encounter has 1-3 diagnoses; rank within encounter is 1=primary.
        rank = rng.randint(1, 3)
        chronic = "Y" if rng.random() < 0.45 else "N"
        rows.append({
            "diagnosis_id": did,
            "encounter_id": eid,
            "icd10_code": code,
            "icd10_name": name,
            "rank": rank,
            "chronic_flag": chronic,
        })
    return rows


# ---- writer ------------------------------------------------------------

def write_csv(rows: list[dict], path: Path, fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    rng = random.Random(SEED)
    patients = gen_patients(rng)
    encounters = gen_encounters(rng, patients)
    orders = gen_lab_orders(rng, encounters)
    results = gen_lab_results(rng, orders)
    diagnoses = gen_diagnoses(rng, encounters)

    targets = [
        (patients, "healthcare-patients-demo.csv",
         ["patient_id", "sex", "age", "weight_kg", "height_cm", "bmi",
          "blood_type", "smoker_flag", "insurance_kind", "primary_dx_code"]),
        (encounters, "healthcare-encounters-demo.csv",
         ["encounter_id", "patient_id", "encounter_type", "department",
          "encounter_date", "length_of_stay_hours", "discharge_disposition",
          "charge_usd", "readmission_flag"]),
        (orders, "healthcare-lab-orders-demo.csv",
         ["order_id", "encounter_id", "test_code", "ordered_at", "priority",
          "ordering_provider_id", "cancelled_flag"]),
        (results, "healthcare-lab-results-demo.csv",
         ["result_id", "order_id", "test_code", "value_numeric", "value_unit",
          "reference_low", "reference_high", "abnormal_flag", "resulted_at"]),
        (diagnoses, "healthcare-diagnoses-demo.csv",
         ["diagnosis_id", "encounter_id", "icd10_code", "icd10_name", "rank",
          "chronic_flag"]),
    ]

    for rows, fname, fields in targets:
        path = OUT_DIR / fname
        write_csv(rows, path, fields)
        size = path.stat().st_size
        print(f"wrote {path.relative_to(REPO_ROOT)}: {len(rows):,} rows × {len(fields)} cols ({size/1024:.1f} KB)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
