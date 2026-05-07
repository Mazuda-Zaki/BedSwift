"""
BedSwift — Demo Data Seeder
============================
Populates TiDB with 15 realistic pre-triaged patients across all wards so
every dashboard looks live on the day of the presentation.

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
# DEMO PATIENTS  (15 records — one per Occupied bed)
# Each dict maps 1-to-1 with Patient model columns.
# ─────────────────────────────────────────────────────────────────────────────
DEMO_PATIENTS = [

    # ── SURGICAL WARD ────────────────────────────────────────────────────────

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
        admission_notes="Patient presented with acute RIF pain, rebound tenderness, fever 38.9°C. Suspected acute appendicitis.",
        ai_triage_summary=(
            "ADMISSION REQUIRED\n"
            "Patient presents with a clinical picture consistent with acute appendicitis, characterised by "
            "progressive right iliac fossa pain over 18 hours, point tenderness at McBurney's point, "
            "positive Rovsing's sign, and pyrexia at 38.9°C. WBC 16.2 × 10⁹/L with neutrophilia. "
            "Urgent surgical review and theatre booking recommended. IV antibiotics commenced."
        ),
    ),

    dict(
        name="Siti Nabilah binti Zainudin",
        bed_id="S2", department="Surgical",
        ic_number="920607-06-2234",
        date_of_birth="1992-06-07", age=33,
        patient_phone="601123456789",
        nok_phone="601187654321",
        triage_priority="urgent",
        admitted_at=_hours_ago(8),
        assigned_doctor_username="dr.ahmad.r@hkl.moh.gov.my",
        assigned_doctor_name="Dr. Ahmad Razali",
        admission_notes="Post-op day 1 laparoscopic cholecystectomy. Routine monitoring.",
        ai_triage_summary=(
            "ADMISSION REQUIRED\n"
            "Patient is post-operative day one following elective laparoscopic cholecystectomy for "
            "symptomatic cholelithiasis. Vital signs stable; Sp0₂ 98% on room air. Wound site clean "
            "and dry. Pain controlled with PRN analgesia. Tolerating clear fluids; diet to be advanced "
            "as tolerated. Discharge anticipated within 24 hours pending review."
        ),
    ),

    dict(
        name="Rajesh Kumar a/l Subramaniam",
        bed_id="S3", department="Surgical",
        ic_number="750821-10-7732",
        date_of_birth="1975-08-21", age=50,
        patient_phone="601134567890",
        nok_phone="601176543210",
        triage_priority="urgent",
        admitted_at=_hours_ago(22),
        assigned_doctor_username="dr.ahmad.r@hkl.moh.gov.my",
        assigned_doctor_name="Dr. Ahmad Razali",
        admission_notes="Incarcerated inguinal hernia, right side. Pain and swelling 6h. Unable to reduce.",
        ai_triage_summary=(
            "ADMISSION REQUIRED\n"
            "Patient presents with a right inguinal hernia that is irreducible and clinically incarcerated, "
            "with associated pain rated 7/10, overlying skin erythema, and absent bowel sounds on auscultation. "
            "Duration of symptoms is approximately six hours with no spontaneous reduction. Risk of strangulation "
            "is high. Emergency surgical exploration and herniorrhaphy indicated; NBM enforced and IV access secured."
        ),
    ),

    dict(
        name="Lim Ai Ling",
        bed_id="S4", department="Surgical",
        ic_number="860915-14-4412",
        date_of_birth="1986-09-15", age=39,
        patient_phone="601145678901",
        nok_phone="601165432109",
        triage_priority="urgent",
        admitted_at=_hours_ago(5),
        assigned_doctor_username="dr.ahmad.r@hkl.moh.gov.my",
        assigned_doctor_name="Dr. Ahmad Razali",
        admission_notes="Sudden onset severe epigastric pain radiating to back. Lipase 1800 U/L.",
        ai_triage_summary=(
            "ADMISSION REQUIRED\n"
            "Patient presents with acute pancreatitis, evidenced by sudden-onset severe epigastric pain "
            "radiating to the dorsum, nausea, and vomiting. Serum lipase markedly elevated at 1800 U/L. "
            "CT abdomen demonstrates pancreatic oedema without evidence of necrosis (Balthazar Grade B). "
            "Aggressive IV fluid resuscitation commenced; strict NBM, analgesia, and NG decompression initiated. "
            "ICU escalation criteria being monitored."
        ),
    ),

    dict(
        name="Norhakim bin Abdullah",
        bed_id="S5", department="Surgical",
        ic_number="010203-03-5511",
        date_of_birth="2001-02-03", age=25,
        patient_phone="601156789012",
        nok_phone="",
        triage_priority="routine",
        admitted_at=_hours_ago(3),
        assigned_doctor_username="dr.ahmad.r@hkl.moh.gov.my",
        assigned_doctor_name="Dr. Ahmad Razali",
        admission_notes="Pilonidal sinus excision planned for tomorrow morning. Pre-op review.",
        ai_triage_summary=(
            "ADMISSION REQUIRED\n"
            "Patient admitted for elective excision of a chronic pilonidal sinus under general anaesthesia "
            "scheduled for the following morning. Pre-operative workup completed: FBC, coagulation profile, "
            "and group-and-screen reported normal. Anaesthesia pre-assessment cleared; patient consented. "
            "NBM from midnight."
        ),
    ),

    # ── MEDICAL WARD ─────────────────────────────────────────────────────────

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
            "Elderly diabetic patient presents in acute decompensated heart failure with dyspnoea at rest, "
            "bilateral pitting oedema to mid-thigh, orthopnoea (3-pillow), and peripheral oxygen saturation "
            "of 88% on room air. CXR demonstrates cardiomegaly with bilateral pleural effusions and "
            "pulmonary vascular congestion. IV frusemide administered; high-flow O₂ therapy initiated. "
            "Cardiology review and echo arranged urgently."
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
        admission_notes="DM2, poorly controlled. RBS 31.4 mmol/L. Confused, dehydrated, no ketonuria.",
        ai_triage_summary=(
            "ADMISSION REQUIRED\n"
            "Patient with poorly controlled Type 2 diabetes mellitus presents with hyperosmolar hyperglycaemic "
            "state. Random blood sugar 31.4 mmol/L; serum osmolality 328 mOsm/kg; GCS 13/15 with mild "
            "confusion. No ketonuria detected. IV fluid resuscitation commenced with 0.9% NaCl; insulin "
            "infusion protocol initiated. Electrolytes, renal function, and hourly glucose monitoring in place."
        ),
    ),

    dict(
        name="Aminah binti Yusoff",
        bed_id="M3", department="Medical",
        ic_number="780515-12-6612",
        date_of_birth="1978-05-15", age=47,
        patient_phone="601189012345",
        nok_phone="601132109876",
        triage_priority="urgent",
        admitted_at=_hours_ago(10),
        assigned_doctor_username="dr.ahmad.r@hkl.moh.gov.my",
        assigned_doctor_name="Dr. Ahmad Razali",
        admission_notes="Fever 39.4°C, rigors, productive cough, right basal crackles. SpO2 93%.",
        ai_triage_summary=(
            "ADMISSION REQUIRED\n"
            "Patient presents with community-acquired pneumonia localised to the right lower lobe, confirmed "
            "on PA chest radiograph demonstrating consolidation with air bronchograms. CURB-65 score of 3 "
            "indicating moderate-to-severe illness. IV co-amoxiclav and azithromycin commenced; supplemental "
            "oxygen maintaining SpO₂ above 95%. Sputum cultures and blood cultures dispatched. Physiotherapy "
            "referral placed."
        ),
    ),

    dict(
        name="Mohamad Zulkifli bin Othman",
        bed_id="M4", department="Medical",
        ic_number="550330-01-4422",
        date_of_birth="1955-03-30", age=71,
        patient_phone="601190123456",
        nok_phone="601121098765",
        triage_priority="urgent",
        admitted_at=_hours_ago(26),
        assigned_doctor_username="dr.ahmad.r@hkl.moh.gov.my",
        assigned_doctor_name="Dr. Ahmad Razali",
        admission_notes="Haematemesis x2, known liver cirrhosis, on propranolol. BP 90/60, HR 118.",
        ai_triage_summary=(
            "ADMISSION REQUIRED\n"
            "Patient with known hepatic cirrhosis secondary to chronic hepatitis B presents with upper "
            "gastrointestinal haemorrhage; two episodes of haematemesis with fresh blood and haemodynamic "
            "compromise (BP 90/60 mmHg, HR 118 bpm). Clinical suspicion of oesophageal variceal bleed. "
            "Two large-bore IV cannulae inserted; resuscitation with normal saline and packed red cells "
            "commenced. Terlipressin and prophylactic IV ceftriaxone administered. Urgent endoscopy booked."
        ),
    ),

    dict(
        name="Priya a/p Krishnamurthy",
        bed_id="M5", department="Medical",
        ic_number="940820-10-8897",
        date_of_birth="1994-08-20", age=31,
        patient_phone="601101234567",
        nok_phone="601109876543",
        triage_priority="routine",
        admitted_at=_hours_ago(4),
        assigned_doctor_username="dr.ahmad.r@hkl.moh.gov.my",
        assigned_doctor_name="Dr. Ahmad Razali",
        admission_notes="Recurrent UTI, dysuria, frequency, temp 38.0°C. MSU dispatched. IV antibiotics started.",
        ai_triage_summary=(
            "ADMISSION REQUIRED\n"
            "Young female patient presents with a second episode of urinary tract infection within six weeks, "
            "characterised by dysuria, urinary frequency, suprapubic discomfort, and low-grade pyrexia at "
            "38.0°C. Urinalysis demonstrates leucocyturia and nitrites; midstream urine dispatched for "
            "culture and sensitivity. IV co-amoxiclav initiated pending sensitivities. Renal ultrasound "
            "arranged to exclude structural abnormality. Oral step-down therapy planned once afebrile."
        ),
    ),

    # ── ORTHOPAEDIC WARD ─────────────────────────────────────────────────────

    dict(
        name="Haji Roslan bin Daud",
        bed_id="O1", department="Orthopaedic",
        ic_number="490101-06-1100",
        date_of_birth="1949-01-01", age=77,
        patient_phone="601112233445",
        nok_phone="601155443322",
        triage_priority="urgent",
        admitted_at=_hours_ago(20),
        assigned_doctor_username="dr.ahmad.r@hkl.moh.gov.my",
        assigned_doctor_name="Dr. Ahmad Razali",
        admission_notes="Mechanical fall. Right hip pain, shortened externally rotated right leg. X-ray: NOF fracture.",
        ai_triage_summary=(
            "ADMISSION REQUIRED\n"
            "Elderly male presents following a ground-level mechanical fall with a displaced intracapsular "
            "neck-of-femur fracture of the right hip confirmed on AP pelvis and lateral hip radiographs. "
            "Neurovascular status of the right lower limb intact. Patient is medically optimised for "
            "hemiarthroplasty within 36 hours as per BOAST guidelines. IV analgesia, skin traction, "
            "and DVT prophylaxis initiated. Pre-operative cardiac clearance requested."
        ),
    ),

    dict(
        name="Nur Izzati binti Hasrul",
        bed_id="O2", department="Orthopaedic",
        ic_number="000811-11-5566",
        date_of_birth="2000-08-11", age=25,
        patient_phone="601122334455",
        nok_phone="601166554433",
        triage_priority="urgent",
        admitted_at=_hours_ago(9),
        assigned_doctor_username="dr.ahmad.r@hkl.moh.gov.my",
        assigned_doctor_name="Dr. Ahmad Razali",
        admission_notes="RTA motorcyclist. Closed tib-fib fracture right leg. Splinted in ED. Awaiting OR slot.",
        ai_triage_summary=(
            "ADMISSION REQUIRED\n"
            "Young female motorcyclist involved in a road traffic accident presents with a closed displaced "
            "fracture of the right tibia and fibula at the junction of the middle and distal thirds. Limb "
            "neurovascularly intact; compartment syndrome excluded clinically. Temporary splinting applied "
            "in the emergency department. Consent obtained for intramedullary nailing; placed on emergency "
            "operating list. NBM enforced; anaesthesia review completed."
        ),
    ),

    dict(
        name="Kevin Ong Jia Wei",
        bed_id="O3", department="Orthopaedic",
        ic_number="850223-07-9988",
        date_of_birth="1985-02-23", age=41,
        patient_phone="601133445566",
        nok_phone="",
        triage_priority="routine",
        admitted_at=_hours_ago(2),
        assigned_doctor_username="dr.ahmad.r@hkl.moh.gov.my",
        assigned_doctor_name="Dr. Ahmad Razali",
        admission_notes="Elective right knee arthroscopy + partial medial meniscectomy tomorrow AM. Pre-op assessment done.",
        ai_triage_summary=(
            "ADMISSION REQUIRED\n"
            "Patient admitted for elective arthroscopic partial medial meniscectomy of the right knee "
            "for chronic medial compartment pain with confirmed bucket-handle tear on MRI. Pre-operative "
            "assessment complete: baseline bloods normal, ECG sinus rhythm, ASA Grade I. Consent signed; "
            "antibiotic prophylaxis prescribed. Day-surgery slot confirmed for 08:00 the following morning."
        ),
    ),

    # ── ICU ──────────────────────────────────────────────────────────────────

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
        admission_notes="STEMI, transferred from Klang. Primary PCI done 4h ago. Now intubated and ventilated in ICU.",
        ai_triage_summary=(
            "ADMISSION REQUIRED\n"
            "Elderly male with anterior STEMI transferred from a peripheral hospital following primary PCI "
            "to the LAD with residual cardiogenic shock. Currently intubated and mechanically ventilated; "
            "noradrenaline 0.12 mcg/kg/min for haemodynamic support. Post-PCI echocardiogram demonstrates "
            "severe anterior wall hypokinesia with EF 25%. Intra-aortic balloon pump in situ. "
            "Hourly haemodynamic monitoring and continuous cardiac monitoring in place. Prognosis guarded."
        ),
    ),

    dict(
        name="Fatimah binti Harun",
        bed_id="ICU2", department="ICU",
        ic_number="670303-05-3344",
        date_of_birth="1967-03-03", age=59,
        patient_phone="601155667788",
        nok_phone="601188776655",
        triage_priority="immediate",
        admitted_at=_hours_ago(12),
        assigned_doctor_username="dr.ahmad.r@hkl.moh.gov.my",
        assigned_doctor_name="Dr. Ahmad Razali",
        admission_notes="Septic shock secondary to biliary source. BP 72/40 on 2 pressors. Lactate 6.1.",
        ai_triage_summary=(
            "ADMISSION REQUIRED\n"
            "Patient presents in septic shock with a probable biliary source, evidenced by right upper "
            "quadrant tenderness, jaundice, pyrexia at 39.8°C, and serum lactate of 6.1 mmol/L. "
            "Currently requiring dual vasopressor support (noradrenaline + vasopressin). SOFA score 14 "
            "consistent with multi-organ dysfunction. Biliary decompression via ERCP planned urgently; "
            "broad-spectrum IV antibiotics covering Gram-negatives and anaerobes commenced. Daily Goals "
            "ICU bundle initiated."
        ),
    ),
]


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
        discharged_at=_hours_ago(2),
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
        discharged_at=_hours_ago(5),
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
        discharged_at=_hours_ago(7),
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
            session.commit()
            print(f"[CLEAN] Removed {deleted_p} patients and {deleted_dr} discharge records.\n")

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
