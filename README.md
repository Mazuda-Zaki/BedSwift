# 🏥 BedSwift — Agentic AI for Intelligent Hospital Bed Management

> **AI-Powered Hospital Operations & Autonomous Discharge System**  
> Built for the Malaysian public healthcare ecosystem · Powered by Groq, Gemini, and TiDB Cloud

BedSwift automates the full patient lifecycle — from self-service pre-arrival triage on a public patient portal, through ED nurse admission and AI-driven ward assignment, to a Human-in-the-Loop discharge workflow that autonomously releases beds, routes e-prescriptions, and notifies next-of-kin upon doctor approval.

---

## 📋 Table of Contents

- [The Problem](#the-problem)
- [Key Features](#key-features)
- [System Architecture](#system-architecture)
- [Tech Stack](#tech-stack)
- [Role-Based Access Control](#role-based-access-control)
- [Database Overview](#database-overview)
- [The Agentic Data Flow](#the-agentic-data-flow)
- [File Structure](#file-structure)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [Demo Accounts](#demo-accounts)
- [How to Use the System](#how-to-use-the-system)
- [Deployment Notes](#deployment-notes)
- [Future Scalability](#future-scalability)
- [Notes & Limitations](#notes--limitations)

---

## The Problem

Hospitals face daily operational bottlenecks that delay patient care:

- ED overcrowding and admission gridlock
- Manual triage documentation and inconsistent handoffs
- Slow bed assignment when real-time availability is unclear
- Limited ward visibility for frontline staff across shifts
- Bed blocking caused by delayed discharge, pharmacy, and cleaning workflows
- Fragmented communication between ED, ward, doctor, pharmacy, and operations teams

---

## Key Features

### 🧑‍⚕️ Public Patient Portal (`/patient`)
- Patient self-submits demographics, symptoms, and optional attachment (image/PDF).
- **Groq LLaMA 3.3** assesses text symptoms; **Gemini 2.5 Flash** handles multimodal (image/PDF) triage.
- Returns admission recommendation, AI clinical summary, live bed count, and **recommended ward**.
- Generates enterprise reference ID (`HKL-YYYYNNNN`) upon hospital notification.

### 🚑 ED Fast-Track + Nurse Admission (`/`)
- Nurse enters pre-arrival reference ID into Fast-Track panel to instantly auto-fill triage form.
- Full triage form with patient demographics, DOB/age sync, priority, chief complaint, voice dictation.
- Admission assigns bed in AI-recommended ward first, with hospital-wide fallback logic.

### 🏥 Live Ward Dashboard (`/ward`)
- Real-time KPI cards: Total / Occupied / Available / Cleaning bed counts.
- Search-to-reveal lookup table (by bed ID, patient name, ward, or patient ID).
- Bed status management (`Occupied`, `Clearing`, `Empty`) updated live.
- Clickable patient cards revealing AI clinical summary in a detail modal.

### 📋 Doctor Discharge Assistant (`/discharge-portal`)
- Patient selector grouped by ward and sorted by bed ID.
- Admission summary panel (AI triage summary, demographics, priority) shown to doctor for clinical context.
- Voice dictation via Groq Whisper for hands-free note entry.
- **Step 1:** Generate AI draft (clinical summary, medications, TCA plan) — no DB writes.
- **Step 2:** Doctor reviews, edits, then approves and executes final discharge.

### 🧾 PDF Discharge Report
- ReportLab A4 PDF generated server-side from snapshot fields preserved at discharge time.
- All timestamps converted from UTC to **MYT (Asia/Kuala_Lumpur)**.
- Streamable download via `/api/discharge-records/{id}/pdf`.

### 🔐 Role-Based Access Control
- Session cookie authentication with SHA-256 password hashing.
- Route handlers and API data are role-gated (nurse / doctor / pharmacy / admin).

---

## System Architecture

```
Patient Portal (/patient)          Staff Portals (/,  /ward,  /discharge-portal,  /history,  /pharmacy)
        │                                               │
        └──────────────────┬────────────────────────────┘
                           ▼
              FastAPI Backend (patient_api.py)
                  Session Auth · RBAC · REST API
                           │
               ┌───────────┴──────────────┐
               ▼                          ▼
   AI Services (Groq + Gemini)      TiDB Cloud (SQLAlchemy ORM)
   Triage · Drafting · Transcription  Beds · Patients · Discharge_Records
                                      Pre_Arrival_Triage · Users
                           │
                           ▼
       Ward Dashboard · Discharge Assistant · PDF Reports
```

**Frontend:** Jinja2-rendered HTML templates · Tailwind CSS (CDN) · Vanilla JS Fetch API  
**Backend:** FastAPI · Starlette SessionMiddleware · Uvicorn (ASGI)  
**AI Layer:** Groq (LLaMA 3.3-70b, Whisper) · Google Gemini 2.5 Flash via LangChain  
**Data Layer:** TiDB Cloud (MySQL-compatible) · SQLAlchemy 2.0 · PyMySQL  
**PDF:** ReportLab server-side A4 generation  

---

## Tech Stack

| Component | Technology | Purpose |
|---|---|---|
| Backend Framework | FastAPI | API routes + server-side rendering |
| UI Layer | Jinja2 / HTML / Tailwind CSS / JavaScript | Interactive staff and patient portals |
| Database | TiDB Cloud (MySQL-compatible) | Persistent operational hospital data |
| ORM | SQLAlchemy 2.0 | Database modeling and queries |
| AI — Triage + Transcription | Groq (`llama-3.3-70b-versatile`, `whisper-large-v3-turbo`) | Triage reasoning + doctor voice-to-text |
| AI — Multimodal + Discharge | Gemini 2.5 Flash via LangChain | Image/PDF triage + discharge note extraction |
| PDF Engine | ReportLab | A4 discharge summary generation |
| Server | Uvicorn (ASGI) | Application serving |
| Auth | Starlette SessionMiddleware + SHA-256 | Session cookies + password hashing |
| Env Config | python-dotenv | Loads `.env` secrets |

---

## Role-Based Access Control

| Role | Default Landing | Accessible Portals |
|---|---|---|
| **Nurse** | ED Triage (`/`) | ED Triage, Ward Dashboard |
| **Doctor** | Discharge Assistant (`/discharge-portal`) | Discharge Assistant, Discharge Records (own only), Ward Dashboard |
| **Admin** | Ward Dashboard (`/ward`) | All portals + demo reset |
| **Patient (public)** | — | Patient Portal (`/patient`) — no login required |

---

## Database Overview

Five SQLAlchemy models defined in `core/database.py`.

| Table | Key Fields | Purpose |
|---|---|---|
| `Users` | `username`, `password_hash`, `role`, `full_name` | Staff accounts and role mapping |
| `Beds` | `bed_id`, `ward`, `status` | 26 beds across 6 wards; `Empty` / `Occupied` / `Clearing` |
| `Patients` | `patient_id`, `name`, `bed_id`, `triage_priority`, `admission_notes`, `ai_triage_summary`, demographics, contacts | Active admitted patients — **deleted on final discharge** |
| `Discharge_Records` | `patient_id`, `clinical_summary`, `medications`, `tca_plan`, `discharge_status`, `pt_*` snapshot fields | Permanent audit trail; snapshot fields ensure PDF survives patient deletion |
| `Pre_Arrival_Triage` | `ref_id`, patient info, `symptoms`, `ai_summary`, `admission_required`, `available_beds`, `status`, `attachment_path` | Patient portal submissions; `Pending` → `Claimed` lifecycle |

> **`patient_id` and `ref_id`** use enterprise format `HKL-YYYYNNNN`, generated by the shared `core/id_generator.py` utility — single source of truth for both live admissions and seeded demo data.

---

## The Agentic Data Flow

### Flow A — Patient Self-Triage → ED Pre-Arrival Fast-Track

```
[Patient Portal  /patient]
        │  Patient enters: name, IC, phone, symptoms (and optional image/PDF)
        ▼
POST /api/triage  (no auth required)
        │  Text → Groq LLaMA-3.3-70b
        │  Image/PDF → Gemini 2.5 Flash (multimodal)
        │  Returns: { admission_required, ai_summary, recommended_ward, available_beds }
        ▼
[Patient sees AI triage result]
        │  Clicks "Notify Hospital & Proceed to ED"
        ▼
POST /api/pre-arrival
        │  Saves Pre_Arrival_Triage row: status = "Pending"
        │  Assigns enterprise Reference ID: HKL-20260023
        ▼
[Patient arrives at ED — shows Reference ID to nurse]
        │
        ▼
GET /api/lookup-reference/{ref_id}  (nurse/admin/doctor auth)
        │  Fetches pre-arrival record
        │  Marks status = "Claimed", claimed_by = nurse_username
        │  Returns auto-fill data to triage form
        ▼
[Triage form auto-populated: name, IC, phone, AI triage summary, priority, attachment link]
```

---

### Flow B — ED Admission → AI Ward Assignment → Bed Occupied

```
[Nurse fills triage form on /]
        │  Optional: "Analyse & Triage" → POST /api/triage → ai_summary returned
        ▼
[Nurse selects assigned doctor + clicks "Confirm Admission"]
        │
POST /api/admit
        │  ID preserved if HKL format; otherwise generates new HKL-YYYYNNNN
        │  Validates doctor exists in Users table
        │  Ward priority: recommended_ward Empty → recommended_ward Clearing
        │                 → any Empty → any Clearing
        │  Sets Bed.status = "Occupied"
        │  Creates Patient row with full triage context
        ▼
[Ward Dashboard refreshes — bed marked Occupied]
[Doctor sees new patient in Discharge Assistant dropdown]
```

---

### Flow C — Doctor Discharge → Agentic Orchestration → Bed Release

```
[Doctor opens /discharge-portal — selects patient from ward-grouped dropdown]
        │  Admission Summary panel shows: AI triage, demographics, priority, doctor
        ▼
[Doctor enters clinical notes — typed or voice-dictated]
        │  Voice path: POST /api/transcribe-audio
        │              Groq Whisper large-v3-turbo → plain text
        ▼

── STEP 1: AI DRAFT  (no DB writes) ─────────────────────────────────────────
POST /api/draft-discharge
        │  Gemini 2.5 Flash + DischargeDraftLite structured output
        │  Rewrites raw dictation → professional clinical narrative
        │  Extracts: clinical_summary, medications[], tca_plan
        ▼
[Doctor reviews AI draft in editable fields — corrects any errors]

── STEP 2: HUMAN APPROVAL + AGENTIC FINALISATION ────────────────────────────
POST /api/process-discharge
        │  ①  Uses doctor's reviewed/edited text (Gemini skipped)
        │  ②  Snapshots Patient row → DischargeRecord (preserves data post-deletion)
        │  ③  Sets Bed.status = "Clearing" → visible on Ward Dashboard immediately
        │  ④  Deletes Patient row atomically
        │
        │  ── ORCHESTRATOR AGENT (post-commit, simulated) ─────────────────
        │  ⑤  _notify_kin() → logs SMS to next-of-kin
        ▼
[Frontend renders "Mission Control" checklist:]
    ✅  Discharge Record & PDF Ready
    ✅  SMS Sent to Next-of-Kin  (or ⚠️ skipped if no NOK phone)
    ✅  Bed Released to ED Dashboard

GET /api/discharge-records/{id}/pdf
        │  ReportLab builds A4 PDF from snapshot fields
        │  Timestamps: UTC → MYT (Asia/Kuala_Lumpur)
        │  Streamed as application/pdf download
```

---

## File Structure

```
BedSwift/
├── patient_api.py          # Entire FastAPI backend — routes, AI calls, PDF builder,
│                           # orchestrator agent, triage parsing, admission logic
├── core/
│   ├── database.py         # SQLAlchemy ORM models, DB init/seed, safe ALTER TABLE migrations
│   ├── id_generator.py     # Shared HKL-YYYYNNNN ID generator (used by API + seeder)
│   └── schemas.py          # Pydantic structured-output schemas (DischargeDraft, DischargeDraftLite)
├── templates/
│   ├── login.html          # Auth page with demo account quick-fill buttons
│   ├── patient.html        # Public patient portal — symptom checker, no login required
│   ├── index.html          # ED Nurse Triage — Pre-Arrival Fast-Track, admission workflow
│   ├── doctor.html         # Ward Dashboard — KPI cards, bed lookup table, patient modal
│   ├── discharge.html      # Discharge Assistant — AI draft + Human-in-the-Loop review
│   └── history.html        # Discharge Records — audit table, modal, PDF download
├── seed_demo_data.py       # Injects 15 realistic pre-triaged patients for demo
├── data/
│   └── hospital_beds.csv   # Reference: 26-bed ward layout (mirrored in DEFAULT_BEDS)
├── static/uploads/         # Patient attachment files (images/PDFs)
├── .env                    # Local secrets (not committed)
└── requirements.txt
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- [TiDB Cloud](https://tidbcloud.com) cluster (free tier works)
- [Groq API key](https://console.groq.com)
- [Google AI Studio API key](https://aistudio.google.com) (Gemini)

### 1) Clone and enter project

```bash
cd BedSwift
```

### 2) Create virtual environment

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS / Linux
```

### 3) Install dependencies

```bash
pip install -r requirements.txt
```

### 4) Configure environment

Create `.env` in the project root:

```env
DATABASE_URL=mysql+pymysql://<user>:<password>@<host>:<port>/<db>?ssl_verify_cert=true&ssl_verify_identity=true
GROQ_API_KEY=gsk_...
GOOGLE_API_KEY=AIza...
SECRET_KEY=your-random-secret-key-here
```

### 5) (Optional) Seed demo data

```bash
python seed_demo_data.py        # Safe re-run — skips existing records
python seed_demo_data.py --clean   # Full reset — wipes + reseeds
```

### 6) Start the server

```bash
python -m uvicorn patient_api:app --host 127.0.0.1 --port 8001 --reload
```

Open [http://127.0.0.1:8001](http://127.0.0.1:8001) in your browser.

---

## Environment Variables

| Variable | Description |
|---|---|
| `DATABASE_URL` | TiDB Cloud / MySQL connection string (SSL required for TiDB) |
| `GROQ_API_KEY` | Groq Cloud key for LLaMA triage + Whisper voice transcription |
| `GOOGLE_API_KEY` | Google AI Studio key for Gemini 2.5 Flash (multimodal triage + discharge drafting) |
| `SECRET_KEY` | Random string used to sign Starlette session cookies |

---

## Demo Accounts

Seeded automatically by `core/database.py` on first startup.

| Role | Username | Password |
|---|---|---|
| Ward Nurse | `azura.h@hkl.moh.gov.my` | `Hkl@Nrs2026!` |
| Doctor | `dr.ahmad.r@hkl.moh.gov.my` | `Hkl@Med2026!` |
| Administrator | `admin.ops@hkl.moh.gov.my` | `Hkl@Ops2026!` |
| Pharmacy | `pharmacy1` | `pharmacy123` |

> Login is **case-insensitive** on the username/email field.  
> The **Admin** account has full system access including the **Reset Demo** button (Ward Dashboard) to wipe all patients + records and restore 26 default beds.

---

## How to Use the System

| Step | Actor | Action |
|---|---|---|
| 1 | Patient | Submit symptoms (text or image/PDF) on Patient Portal → receive Reference ID |
| 2 | Nurse | Look up Reference ID in ED Triage Fast-Track → form auto-fills → Analyze & Triage |
| 3 | Nurse | Confirm Admission → system assigns bed in AI-recommended ward |
| 4 | Doctor | Open Discharge Assistant → review patient context → dictate or type clinical notes |
| 5 | Doctor | Generate AI Draft → review and edit → Approve & Execute Discharge |
| 6 | System | Bed set to Clearing → can be set to Empty after housekeeping |
| 7 | Doctor/Admin | Download PDF discharge report from Discharge Records history |

---

## Deployment Notes

BedSwift can be deployed on Render, Railway, Fly.io, or any container/VM platform.

```bash
# Production start command
uvicorn patient_api:app --host 0.0.0.0 --port $PORT
```

- Use environment variables for all secrets — never hardcode credentials.
- TiDB Cloud remains the managed cloud database backend.
- `SECRET_KEY` must be a cryptographically random string in production.
- Ensure `static/uploads/` is writable for patient attachment storage.

---

## Future Scalability

1. **Replace mock agents with real integrations.** `_notify_kin()` is an isolated function ready to accept Twilio/AWS SNS for live SMS delivery to next-of-kin.

2. **LangGraph multi-agent orchestration.** A full pipeline would chain `TriageAgent → BedAllocatorAgent → ScribeAgent → KinNotificationAgent` with shared state, retries, and LangSmith observability.

3. **WebSocket real-time push.** Ward Dashboard currently polls every 30 seconds. WebSocket or Server-Sent Events would eliminate lag in high-volume ED scenarios.

4. **Multi-hospital / multi-tenant support.** A `hospital_id` foreign key on `Beds`, `Patients`, and `Discharge_Records` would allow a single deployment to serve multiple sites with isolated data.

5. **Async database layer.** Migrating to SQLAlchemy `AsyncSession` with `aiomysql` would improve throughput under concurrent load.

6. **Structured audit logging.** Emitting structured JSON logs (patient ID, actor, action, timestamp) to a log aggregator (Datadog, GCP Logging) would satisfy clinical audit requirements.

---

## Notes & Limitations

- ⚠️ **Notification step** (`_notify_kin`) is simulated/logged — not integrated with a live SMS provider.
- ⚠️ **AI recommendations** (triage priority, ward selection, discharge drafting) require clinical oversight and are support tools only.
- ⚠️ **Ward recommendation** is a structured metadata field used internally for bed routing — it is intentionally stripped from displayed clinical narrative.
- ⚠️ **Not a replacement** for clinical judgment or certified hospital information systems.
- ⚠️ Some legacy prototype files (`app.py`, `agents/`, `workflow/`, `reporting/`) remain in the repository but are not active in the current FastAPI runtime.

---

*BedSwift v1.0 · FastAPI · TiDB Cloud · Groq · Google Gemini · ReportLab · Hospital Kuala Lumpur · Kementerian Kesihatan Malaysia*
