"""
BedSwift — Demo Data Seeder
============================
Populates TiDB with 5 realistic pre-triaged patients across 3 wards so
the dashboards look live without crowding the bed map on presentation day.

Ward distribution (5 occupied / 2 clearing / 19 available / 26 total):
  ICU      — 1 patient   (ICU1)
  Medical  — 2 patients  (M1, M2)
  Surgical — 2 patients  (S1, S2)

Two additional beds (M3, O1) are set to "Clearing" to demonstrate the
full bed-status lifecycle on the Ward Dashboard KPI cards.

HOW TO RUN
----------
1. Make sure the server is NOT running (or it can be running — the script
   talks directly to the DB and doesn't conflict with Uvicorn).

2. Activate the virtual environment:
       .\\venv\\Scripts\\Activate.ps1          # Windows PowerShell
       source venv/bin/activate               # macOS / Linux

3. From the project root:
       python seed_demo_data.py

4. (Optional) To wipe existing patients before seeding add --clean:
       python seed_demo_data.py --clean

What it does
------------
  • Leaves Users and Beds tables untouched (beds already seeded by init_db).
  • Inserts Patient rows that map to the Occupied beds defined in DEFAULT_BEDS.
  • Adds 3 completed DischargeRecord rows (for the History page).
  • Skips any patient_id that already exists (idempotent — safe to re-run).
"""

import sys
import datetime
import argparse

from sqlalchemy.orm import Session
from core.database import engine, Patient, Bed, DischargeRecord, init_db
from core.id_generator import generate_patient_id

# ── Timezone: Malaysia (UTC+8) ───────────────────────────────────────────────
_MYT = datetime.timezone(datetime.timedelta(hours=8))
_now = datetime.datetime.now(tz=_MYT)

def _hours_ago(h: float) -> datetime.datetime:
    return (_now - datetime.timedelta(hours=h)).replace(tzinfo=None)


# ─────────────────────────────────────────────────────────────────────────────
# DEMO PATIENTS  (5 records)
# Distribution: 1 ICU · 2 Medical · 2 Surgical
#
# triage_priority values MUST be one of: immediate | urgent | routine
# (these map directly to the colour chips in doctor.html and index.html)
# ─────────────────────────────────────────────────────────────────────────────
DEMO_PATIENTS = [

    # ── ICU (1) ───────────────────────────────────────────────────────────────

    dict(
        name="Dato' Sulaiman bin Hamzah",
        bed_id="ICU1", department="ICU",
        ic_number="430617-03-6677",
        date_of_birth="1943-06-17", age=82,
        patient_phone="601144556677",
        nok_phone="601177665544",
        triage_priority="immediate",
        admitted_at=_hours_ago(48),
        assigned_doctor_username="dr.ahmad.r@hkl.moh.gov.my",
        assigned_doctor_name="Dr. Ahmad Razali",
        admission_notes="STEMI transferred from Klang. Primary PCI done 4h ago. Intubated and ventilated in ICU.",
        ai_triage_summary=(
            "ADMISSION REQUIRED\n"
            "Elderly male with anterior STEMI transferred following primary PCI to the LAD with residual "
            "cardiogenic shock. Currently intubated and mechanically ventilated; noradrenaline 0.12 mcg/kg/min "
            "for haemodynamic support. Post-PCI echo: severe anterior wall hypokinesia EF 25%. Intra-aortic "
            "balloon pump in situ. Continuous cardiac monitoring in place. Prognosis guarded."
        ),
    ),

    # ── MEDICAL (2) ───────────────────────────────────────────────────────────

    dict(
        name="Datin Rosnah binti Mahmud",
        bed_id="M1", department="Medical",
        ic_number="580422-04-7890",
        date_of_birth="1958-04-22", age=68,
        patient_phone="601167890123",
        nok_phone="601154321098",
        triage_priority="immediate",
        admitted_at=_hours_ago(36),
        assigned_doctor_username="dr.ahmad.r@hkl.moh.gov.my",
        assigned_doctor_name="Dr. Ahmad Razali",
        admission_notes="Known T2DM and HTN. SOB at rest, bilateral leg oedema, orthopnoea. SpO2 88% on air.",
        ai_triage_summary=(
            "ADMISSION REQUIRED\n"
            "Elderly diabetic patient in acute decompensated heart failure. Dyspnoea at rest, bilateral "
            "pitting oedema to mid-thigh, 3-pillow orthopnoea, SpO₂ 88% on room air. CXR: cardiomegaly "
            "with bilateral pleural effusions. IV frusemide and high-flow O₂ commenced. Urgent cardiology "
            "review and echo arranged."
        ),
    ),

    dict(
        name="Tan Chee Keong",
        bed_id="M2", department="Medical",
        ic_number="650709-08-3341",
        date_of_birth="1965-07-09", age=60,
        patient_phone="601178901234",
        nok_phone="601143210987",
        triage_priority="urgent",
        admitted_at=_hours_ago(18),
        assigned_doctor_username="dr.ahmad.r@hkl.moh.gov.my",
        assigned_doctor_name="Dr. Ahmad Razali",
        admission_notes="DM2 poorly controlled. RBS 31.4 mmol/L. Confused, dehydrated, no ketonuria.",
        ai_triage_summary=(
            "ADMISSION REQUIRED\n"
            "Poorly controlled Type 2 DM presenting with hyperosmolar hyperglycaemic state. RBS 31.4 mmol/L, "
            "osmolality 328 mOsm/kg, GCS 13/15. No ketonuria. IV 0.9% NaCl resuscitation and insulin infusion "
            "commenced. Hourly electrolytes, renal function, and glucose monitoring in place."
        ),
    ),

    # ── SURGICAL (2) ─────────────────────────────────────────────────────────

    dict(
        name="Muhammad Hafiz bin Rosli",
        bed_id="S1", department="Surgical",
        ic_number="880314-10-5521",
        date_of_birth="1988-03-14", age=38,
        patient_phone="601112345678",
        nok_phone="601198765432",
        triage_priority="immediate",
        admitted_at=_hours_ago(14),
        assigned_doctor_username="dr.ahmad.r@hkl.moh.gov.my",
        assigned_doctor_name="Dr. Ahmad Razali",
        admission_notes="Acute RIF pain, rebound tenderness, fever 38.9°C. Suspected acute appendicitis.",
        ai_triage_summary=(
            "ADMISSION REQUIRED\n"
            "Clinical picture consistent with acute appendicitis: progressive RIF pain over 18 hours, "
            "McBurney's point tenderness, positive Rovsing's sign, pyrexia 38.9°C. WBC 16.2 × 10⁹/L with "
            "neutrophilia. Urgent surgical review and theatre booking arranged. IV antibiotics commenced."
        ),
    ),

    dict(
        name="Siti Nabilah binti Zainudin",
        bed_id="S2", department="Surgical",
        ic_number="920607-06-2234",
        date_of_birth="1992-06-07", age=33,
        patient_phone="601123456789",
        nok_phone="601187654321",
        triage_priority="routine",
        admitted_at=_hours_ago(8),
        assigned_doctor_username="dr.ahmad.r@hkl.moh.gov.my",
        assigned_doctor_name="Dr. Ahmad Razali",
        admission_notes="Post-op day 1 laparoscopic cholecystectomy. Routine monitoring.",
        ai_triage_summary=(
            "ADMISSION REQUIRED\n"
            "Post-operative day one following elective laparoscopic cholecystectomy for symptomatic "
            "cholelithiasis. Vitals stable, SpO₂ 98% on room air. Wound site clean and dry. Pain "
            "controlled with PRN analgesia. Tolerating clear fluids. Discharge anticipated within "
            "24 hours pending review."
        ),
    ),
]

# Beds to set as "Clearing" after patient rows are inserted (no patient linked —
# demonstrates the full Occupied → Clearing → Empty lifecycle on the dashboard).
CLEARING_BEDS = ["M3", "O1"]


# ─────────────────────────────────────────────────────────────────────────────
# COMPLETED DISCHARGE RECORDS (for the Discharge Records history page)
# ─────────────────────────────────────────────────────────────────────────────
DEMO_DISCHARGE_RECORDS = [
    dict(
        patient_id="HKL-20260000",
        bed_id="S6", department="Surgical",
        mo_name="Dr. Ahmad Razali",
        created_by_username="dr.ahmad.r@hkl.moh.gov.my",
        discharge_status="Discharged",
        pharmacy_status="Auto-Routed",
        payment_status="Pending",
        discharged_at=_hours_ago(72),
        clinical_summary=(
            "Patient underwent uncomplicated open appendicectomy for confirmed acute appendicitis. "
            "Post-operative recovery was uneventful; pain well-controlled with oral analgesia. "
            "Wound site clean and dry on review. Tolerating a full diet and ambulant independently. "
            "Discharged home in stable condition."
        ),
        medications="Amoxicillin-Clavulanate 625mg TDS × 5 days\nParacetamol 1g QID PRN\nIbuprofen 400mg TDS with food × 3 days",
        tca_plan="Review at Surgical OPD in 2 weeks for wound inspection and histology result. Return to ED immediately if fever, wound dehiscence, or worsening pain.",
        # Snapshot fields
        pt_name="Ahmad Firdaus bin Kamarul",
        pt_ic="960430-14-5500",
        pt_dob="1996-04-30",
        pt_age=29,
        pt_phone="601166778899",
        pt_nok_phone="601199887766",
        pt_triage_priority="urgent",
        pt_chief_complaint="Acute appendicitis — 12h RIF pain, fever, vomiting.",
        pt_ai_summary=(
            "ADMISSION REQUIRED\n"
            "Patient presents with classic features of acute appendicitis including migratory pain "
            "from the periumbilical region to the right iliac fossa, fever, and vomiting. "
            "Alvarado score 8; urgent surgical review and theatre booking arranged."
        ),
    ),
    dict(
        patient_id="HKL-20260099",
        bed_id="M6", department="Medical",
        mo_name="Dr. Ahmad Razali",
        created_by_username="dr.ahmad.r@hkl.moh.gov.my",
        discharge_status="Discharged",
        pharmacy_status="Auto-Routed",
        payment_status="Pending",
        discharged_at=_hours_ago(96),
        clinical_summary=(
            "Patient admitted with an acute exacerbation of bronchial asthma triggered by a concurrent "
            "upper respiratory tract infection. Responded well to nebulised salbutamol and IV "
            "hydrocortisone within 12 hours. Peak flow returned to >80% predicted. No ICU escalation required. "
            "Discharged on step-up maintenance inhaler therapy."
        ),
        medications="Salbutamol MDI 200mcg PRN (max QID)\nBeclomethasone DPI 200mcg BD\nPrednisolone 30mg OD × 5 days\nAmoxicillin 500mg TDS × 7 days",
        tca_plan="Follow-up at Respiratory Clinic in 4 weeks. Spirometry to be repeated at follow-up. "
                 "Patient educated on inhaler technique and asthma action plan provided. Return to ED if peak flow drops below 50% or worsening symptoms.",
        pt_name="Nurul Ain binti Yusri",
        pt_ic="010915-10-3322",
        pt_dob="2001-09-15",
        pt_age=24,
        pt_phone="601177889900",
        pt_nok_phone="601100998877",
        pt_triage_priority="urgent",
        pt_chief_complaint="Acute asthma exacerbation — wheeze, dyspnoea, accessory muscle use.",
        pt_ai_summary=(
            "ADMISSION REQUIRED\n"
            "Young female presents with moderate-to-severe acute asthma exacerbation. "
            "SpO₂ 91% on room air, audible wheeze, use of accessory muscles of respiration. "
            "PEFR 45% of predicted. Immediate bronchodilator therapy and systemic corticosteroids indicated."
        ),
    ),
    dict(
        patient_id="HKL-20260098",
        bed_id="O4", department="Orthopaedic",
        mo_name="Dr. Ahmad Razali",
        created_by_username="dr.ahmad.r@hkl.moh.gov.my",
        discharge_status="Discharged",
        pharmacy_status="Auto-Routed",
        payment_status="Pending",
        discharged_at=_hours_ago(120),
        clinical_summary=(
            "Patient underwent successful left knee total replacement under spinal anaesthesia. "
            "Post-operative physiotherapy commenced on day one; patient independently ambulant with a "
            "walking frame on day two. DVT prophylaxis completed. Wound inspection satisfactory; "
            "sutures intact with no signs of infection. Discharged home with structured rehabilitation plan."
        ),
        medications="Rivaroxaban 10mg OD × 14 days\nParacetamol 1g QID regular × 2 weeks\nOxycodone SR 10mg BD × 3 days (then cease)\nOmeprazole 20mg OD (gastric protection while on Oxycodone)",
        tca_plan="Physiotherapy outpatient programme to begin within 1 week of discharge. "
                 "Orthopaedic OPD review at 6 weeks post-op for wound check and X-ray. "
                 "Wound clips to be removed by GP at 2 weeks. Return to ED if fever, calf pain, or wound breakdown.",
        pt_name="Cheah Beng Huat",
        pt_ic="530618-07-2211",
        pt_dob="1953-06-18",
        pt_age=72,
        pt_phone="601188990011",
        pt_nok_phone="601111009988",
        pt_triage_priority="routine",
        pt_chief_complaint="Elective left knee total replacement for end-stage osteoarthritis.",
        pt_ai_summary=(
            "ADMISSION REQUIRED\n"
            "Elderly male admitted for elective left total knee arthroplasty for end-stage osteoarthritis "
            "refractory to conservative management. Pre-operative optimisation complete. ASA Grade II. "
            "Anaesthetic team briefed; consent signed for procedure under spinal anaesthesia."
        ),
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def _parse_args():
    p = argparse.ArgumentParser(description="BedSwift demo data seeder")
    p.add_argument("--clean", action="store_true",
                   help="Delete ALL existing patients and discharge records before seeding")
    return p.parse_args()


def seed(clean: bool = False) -> None:
    print("-" * 60)
    print("BedSwift Demo Seeder")
    print("-" * 60)

    # Ensure tables exist (safe to call multiple times)
    init_db(seed=True)

    with Session(engine) as session:

        if clean:
            deleted_p  = session.query(Patient).delete()
            deleted_dr = session.query(DischargeRecord).delete()
            # Reset ALL beds to Empty so occupied count matches patients inserted
            reset_beds = session.query(Bed).update({"status": "Empty"})
            session.commit()
            print(f"[CLEAN] Removed {deleted_p} patients and {deleted_dr} discharge records.")
            print(f"[CLEAN] Reset {reset_beds} beds to Empty.\n")

        # ── Insert Patients ─────────────────────────────────────────────────
        inserted_p  = 0
        skipped_p   = 0
        for p in DEMO_PATIENTS:
            row = dict(p)
            exists = session.query(Patient).filter(
                Patient.bed_id == row["bed_id"],
                Patient.name == row["name"],
            ).first()
            if exists:
                skipped_p += 1
                continue

            # Mark the bed as Occupied (in case the demo reset left it Empty)
            bed = session.query(Bed).filter(Bed.bed_id == row["bed_id"]).first()
            if bed and bed.status != "Occupied":
                bed.status = "Occupied"

            row.pop("patient_id", None)  # force single source of truth via generator
            row["patient_id"] = generate_patient_id(session)
            admitted_at = row.pop("admitted_at", datetime.datetime.now(datetime.UTC).replace(tzinfo=None))
            notes       = row.pop("notes",       None)
            session.add(Patient(
                admitted_at=admitted_at,
                notes=notes,
                **row,
            ))
            inserted_p += 1

        session.commit()
        print(f"[Patients]          Inserted {inserted_p}, skipped {skipped_p} (already exist).")

        # ── Mark Clearing beds ──────────────────────────────────────────────
        cleared = 0
        for bid in CLEARING_BEDS:
            bed = session.query(Bed).filter(Bed.bed_id == bid).first()
            if bed and bed.status == "Empty":
                bed.status = "Clearing"
                cleared += 1
        session.commit()
        if cleared:
            print(f"[Beds]              Set {cleared} bed(s) to Clearing: {', '.join(CLEARING_BEDS)}.")

        # ── Insert Discharge Records ────────────────────────────────────────
        inserted_dr = 0
        skipped_dr  = 0
        for dr in DEMO_DISCHARGE_RECORDS:
            exists = session.query(DischargeRecord).filter(
                DischargeRecord.patient_id == dr["patient_id"]
            ).first()
            if exists:
                skipped_dr += 1
                continue

            pt_admitted = dr.pop("pt_admitted_at", None)
            session.add(DischargeRecord(
                updated_at=dr.get("discharged_at", datetime.datetime.now(datetime.UTC).replace(tzinfo=None)),
                pt_admitted_at=pt_admitted,
                **dr,
            ))
            inserted_dr += 1

        session.commit()
        print(f"[DischargeRecords]  Inserted {inserted_dr}, skipped {skipped_dr} (already exist).")

    print("-" * 60)
    print("Done! Open http://127.0.0.1:8001 and log in to see the data.")
    print("-" * 60)


if __name__ == "__main__":
    args = _parse_args()
    seed(clean=args.clean)
