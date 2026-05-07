# 1. Project Title & Tagline

# BedSwift — Agentic AI for Intelligent Hospital Bed Management

**Tagline:** BedSwift helps hospitals reduce ED gridlock, accelerate triage support, maintain real-time bed visibility, and coordinate discharge workflows across nurse, doctor, pharmacy, and admin teams.

---

# 2. The Problem

Hospitals face daily operational bottlenecks that delay patient care:

- ED overcrowding and admission gridlock
- Manual triage documentation and inconsistent handoffs
- Slow bed assignment when availability is unclear
- Limited real-time ward visibility for frontline staff
- Bed blocking caused by delayed discharge, pharmacy, and bed turnover
- Fragmented communication between ED, ward, doctor, pharmacy, and operations teams

---

# 3. The Solution / Key Features

BedSwift is a full-stack hospital operations prototype that connects pre-arrival triage, admission, ward occupancy, discharge, and pharmacy status into one workflow.

## Core Features Implemented

- 🧑‍⚕️ **Public Patient Portal (`/patient`)**
  - Patient self-submits demographics, symptoms, and optional attachment (image/PDF).
  - Generates and saves pre-arrival reference ID (`HKL-YYYYNNNN`).

- 🤖 **AI-Assisted Triage (`/api/triage`)**
  - **Groq LLaMA 3.3** for text triage.
  - **Gemini 2.5 Flash** for multimodal triage (image/PDF).
  - Returns admission recommendation, AI summary, live bed counts, and **recommended ward** metadata.

- 🚑 **ED Fast-Track + Nurse Admission (`/`)**
  - Nurse can lookup pre-arrival reference (`/api/lookup-reference/{ref_id}`).
  - Auto-fills triage details and attachment availability.
  - Admission confirmation creates patient + assigns bed with ward-priority fallback logic.

- 🏥 **Live Ward Dashboard (`/ward`)**
  - Real-time bed stats and ward-level occupancy visibility.
  - Search-to-reveal table workflow for bed lookup.
  - Bed status management (`Occupied`, `Clearing`, `Empty`).

- 📋 **Doctor Discharge Assistant (`/discharge-portal`)**
  - Select admitted patient (grouped by ward, sorted by bed ID).
  - Generate AI draft discharge content (clinical summary, meds, TCA plan).
  - Human-in-the-loop review + finalize discharge.

- 💊 **Pharmacy Workflow (`/pharmacy`, `/api/pharmacy-queue`)**
  - Tracks medication preparation status in discharge records.
  - Status updates via API for pharmacy/admin role.

- 🧾 **PDF Discharge Report**
  - Generated via ReportLab (`/api/discharge-records/{id}/pdf`).
  - Includes patient snapshot fields preserved at discharge time.
  - Timestamps converted to **MYT (Asia/Kuala_Lumpur)**.

- 🔐 **Role-Based Access Control**
  - Session-based login with role-gated routes and data visibility.
  - Roles: nurse, doctor, pharmacy, admin.

## Honest Notes on Current State

- “Agentic” notifications (`_notify_pharmacy`, `_notify_kin`) are currently simulated/logged.
- Payment status exists as a record field but no standalone payment module UI.
- AI outputs are support tools and require clinician review.

---

# 4. System Architecture

## Architecture Overview

- **Frontend:** Jinja2-rendered HTML templates + Tailwind CSS + vanilla JS Fetch workflows
- **Backend:** FastAPI (`patient_api.py`) with session middleware
- **Database:** TiDB Cloud (MySQL-compatible) via SQLAlchemy
- **AI Services:**
  - Groq (LLaMA triage + Whisper transcription)
  - Gemini (multimodal triage + discharge drafting)
- **PDF Layer:** ReportLab discharge PDF generation
- **Auth:** Session cookies (`SessionMiddleware`)
- **RBAC:** Role-checked route handlers and per-role data filters

## Text Diagram

```text
Patient Portal / Staff Portals
        ↓
FastAPI Backend (patient_api.py)
        ↓
AI Triage + AI Draft Discharge
        ↓
TiDB Cloud Database (SQLAlchemy)
        ↓
Ward Dashboard / Discharge Assistant / Pharmacy Dashboard / PDF Reports
```

---

# 5. Tech Stack

| Component | Technology | Purpose |
|---|---|---|
| Backend Framework | FastAPI | API routes + server-side rendering |
| UI Layer | Jinja2 / HTML / CSS / JavaScript | Interactive staff and patient portals |
| Database | TiDB Cloud | Persistent operational hospital data |
| ORM | SQLAlchemy 2.0 | Database modeling and queries |
| AI (Triage + Transcription) | Groq (`llama-3.3-70b-versatile`, `whisper-large-v3-turbo`) | Triage reasoning + voice transcription |
| AI (Multimodal + Drafting) | Gemini 2.5 Flash (LangChain) | Image/PDF triage + discharge extraction |
| PDF Engine | ReportLab | Discharge report generation |
| Server Runtime | Uvicorn | ASGI app serving |
| Env Management | python-dotenv | Loads `.env` configuration |

---

# 6. Role-Based Access

| Role | Main Access |
|---|---|
| **Nurse** | ED Triage (`/`), Ward Dashboard (`/ward`), admission/bed assignment flow |
| **Doctor** | Ward Dashboard (`/ward`), Discharge Assistant (`/discharge-portal`), own discharge records (`/history`, filtered) |
| **Pharmacy** | Pharmacy Dashboard (`/pharmacy`), Ward Dashboard (`/ward`) |
| **Admin** | Full access: ED, Ward, Discharge, History, Pharmacy, and demo reset (`/api/reset`) |

---

# 7. Database Overview

Main models are defined in `core/database.py`.

| Table | Key Fields | Purpose |
|---|---|---|
| `Users` | `username`, `password_hash`, `role`, `full_name` | Staff authentication and role mapping |
| `Beds` | `bed_id`, `ward`, `status` | Bed inventory and occupancy state |
| `Patients` | `patient_id`, `name`, `bed_id`, `triage_priority`, `admission_notes`, `ai_triage_summary`, contact + demographics | Active admitted patients |
| `Discharge_Records` | `patient_id`, `clinical_summary`, `medications`, `tca_plan`, `discharge_status`, `pharmacy_status`, patient snapshot fields (`pt_*`) | Discharge audit trail and workflow status |
| `Pre_Arrival_Triage` | `ref_id`, patient info, `symptoms`, `ai_summary`, `admission_required`, `available_beds`, `status`, `attachment_path` | Patient portal submissions and fast-track lookup queue |

Notes:
- `Patients.patient_id` and `Pre_Arrival_Triage.ref_id` are unique enterprise IDs.
- Discharge records store snapshot fields so PDF remains valid even after patient row deletion.

---

# 8. Setup Instructions

## 1) Open project

```bash
cd BedSwift
```

## 2) Create and activate virtual environment

```bash
python -m venv venv
venv\Scripts\activate
# macOS/Linux: source venv/bin/activate
```

## 3) Install dependencies

```bash
pip install -r requirements.txt
```

## 4) Create `.env`

```env
DATABASE_URL=mysql+pymysql://<user>:<password>@<host>:<port>/<db>?ssl_verify_cert=true&ssl_verify_identity=true
GROQ_API_KEY=...
GOOGLE_API_KEY=...
SECRET_KEY=...
```

## 5) (Optional) Seed demo data

```bash
python seed_demo_data.py
# Optional full refresh:
# python seed_demo_data.py --clean
```

## 6) Start the app

```bash
python -m uvicorn patient_api:app --host 127.0.0.1 --port 8001 --reload
```

Open: [http://127.0.0.1:8001](http://127.0.0.1:8001)

---

# 9. Demo Accounts

Accounts are seeded in `core/database.py` (`DEFAULT_USERS`):

| Role | Username | Password |
|---|---|---|
| Nurse | `azura.h@hkl.moh.gov.my` | `Hkl@Nrs2026!` |
| Doctor | `dr.ahmad.r@hkl.moh.gov.my` | `Hkl@Med2026!` |
| Admin | `admin.ops@hkl.moh.gov.my` | `Hkl@Ops2026!` |
| Pharmacy | `pharmacy1` | `pharmacy123` |

---

# 10. How to Use the System

Typical end-to-end flow:

1. Patient submits symptoms/attachment on Patient Portal **or** nurse performs ED triage.
2. AI returns triage summary, admission recommendation, and recommended ward metadata.
3. Nurse confirms admission, assigns doctor, and system assigns bed based on availability priority.
4. Doctor opens Discharge Assistant, reviews patient context, and generates AI discharge draft.
5. Doctor edits/approves and executes final discharge workflow.
6. Pharmacy tracks medication preparation status in dashboard queue.
7. Final discharge updates statuses; bed moves to `Clearing`/`Empty` per workflow controls.
8. PDF discharge report is downloadable from records.

---

# 11. Deployment Notes

BedSwift can be deployed to services like Render, Railway, Fly.io, or VM/container platforms.

- Use environment variables for all secrets (never hardcode).
- Recommended production start command:

```bash
uvicorn patient_api:app --host 0.0.0.0 --port $PORT
```

- Keep TiDB Cloud as the managed persistent database backend.
- Set a strong `SECRET_KEY` and production-grade database credentials.

---

# 12. Notes / Limitations

- ⚠️ Notification steps (`notify_pharmacy`, `notify_kin`) are currently simulated/log outputs, not integrated with live SMS/pharmacy APIs.
- ⚠️ AI recommendations (triage/ward/discharge drafting) require clinical oversight.
- ⚠️ This prototype supports operations and documentation acceleration; it is **not** a replacement for medical judgment.
- ⚠️ Some legacy fields/routes remain for compatibility while the workflow evolves.

---

**BedSwift** · FastAPI · TiDB Cloud · Groq · Gemini · ReportLab
# 🏥 BedSwift

> **AI-Powered Hospital Bed Management & Autonomous Discharge System**  
> Built for the Malaysian public healthcare ecosystem · Powered by Groq, Gemini, and TiDB Cloud

---

## 📋 Table of Contents

- [High-Level Overview](#high-level-overview)
- [Tech Stack](#tech-stack)
- [File Structure](#file-structure)
- [Role-Based Access Control](#role-based-access-control)
- [The Agentic Data Flow](#the-agentic-data-flow)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [Demo Accounts](#demo-accounts)
- [Future Scalability](#future-scalability)

---

## High-Level Overview

BedSwift is an AI-powered hospital bed management and patient discharge platform built for Malaysian public hospitals. It automates the full patient lifecycle — from self-service pre-arrival symptom triage on a public patient portal, through ED nurse admission and ward bed assignment, to a Human-in-the-Loop AI discharge workflow that autonomously releases beds, routes e-prescriptions, and notifies next-of-kin upon doctor approval.

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.11+, FastAPI, Uvicorn (ASGI), Starlette `SessionMiddleware` |
| **Frontend** | Jinja2 HTML templates, Tailwind CSS (CDN), Vanilla JavaScript (Fetch API) |
| **Database** | TiDB Cloud (MySQL-compatible), SQLAlchemy ORM 2.0, PyMySQL |
| **AI — Triage** | Groq Cloud · `llama-3.3-70b-versatile` (symptom assessment & admission decision) |
| **AI — Transcription** | Groq Cloud · `whisper-large-v3-turbo` (doctor voice-to-text dictation) |
| **AI — Discharge** | Google Gemini 2.5 Flash via LangChain (structured clinical summarisation) |
| **PDF Generation** | ReportLab (server-side A4 discharge summary, streamed to browser) |
| **Auth** | Starlette session cookies, SHA-256 password hashing, role-based access control |

---

## File Structure

```
BedSwift/
├── patient_api.py          # Sole application entrypoint — all FastAPI routes,
│                           # AI calls, PDF builder, Orchestrator Agent functions
├── core/
│   ├── database.py         # SQLAlchemy ORM models, DB init/seed, safe ALTER TABLE migration
│   └── schemas.py          # Pydantic structured-output schemas for Gemini
│                           # (DischargeDraft, DischargeDraftLite)
├── agents/
│   └── scribe.py           # Legacy Chainlit/LangGraph scribe prototype (not active)
├── templates/
│   ├── login.html          # Auth page with demo account quick-fill
│   ├── patient.html        # Public patient portal — symptom checker (no login required)
│   ├── index.html          # ED Nurse Triage — admit patients, Pre-Arrival Fast-Track
│   ├── doctor.html         # Ward Dashboard — live KPI cards, bed accordion grid
│   ├── discharge.html      # Discharge Assistant — AI draft + Human-in-the-Loop review
│   ├── history.html        # Discharge Records — full audit table + modal + PDF download
│   └── pharmacy.html       # Pharmacy Dashboard (legacy; e-prescriptions now auto-routed)
├── data/
│   └── hospital_beds.csv   # Seed reference: 26 default beds across 6 wards
├── .env                    # Local secrets (not committed)
├── requirements.txt
└── README.md
```

### Key Module Roles

**`patient_api.py`** — The entire backend in one file. Registers all routes for auth, triage, admission, AI drafting, finalisation, PDF generation, bed management, and demo reset. Contains the two Orchestrator Agent mock functions (`_notify_pharmacy`, `_notify_kin`) and the full ReportLab PDF builder (`_build_pdf`).

**`core/database.py`** — Defines 5 SQLAlchemy ORM models (`Bed`, `Patient`, `DischargeRecord`, `User`, `PreArrivalTriage`), the 26-bed seed dataset, `init_db()` called at startup, and `_safe_add_columns()` — an idempotent migration helper that adds new columns to live tables via `ALTER TABLE` without data loss.

**`core/schemas.py`** — Two Pydantic models used as Gemini structured-output targets: `DischargeDraft` (includes `bed_number`, legacy path) and `DischargeDraftLite` (slim, no `bed_number`, more reliable for the Human-in-the-Loop draft step).

---

## Role-Based Access Control

| Role | Accessible Portals |
|---|---|
| **Nurse** | ED Triage (`/`), Ward Dashboard (`/ward`) |
| **Doctor** | Ward Dashboard, Discharge Assistant (`/discharge-portal`), Discharge Records (`/history`) — own patients only |
| **Admin** | All routes including demo reset |
| **Pharmacy** | Pharmacy Dashboard (`/pharmacy`) only |
| **Patient (public)** | Patient Portal (`/patient`) — no login required |

---

## The Agentic Data Flow

### Flow A — Patient Self-Triage → ED Pre-Arrival Fast-Track

```
[Patient Portal  /patient]
        │
        │  1. Patient enters name, IC, phone, symptoms
        ▼
POST /api/triage  (no auth required)
        │  Groq LLaMA-3.3-70b assesses symptoms
        │  Returns: { admission_required, ai_summary, available_beds }
        │  (live bed count queried from TiDB in real time)
        ▼
[Patient sees AI result + auto-generated Reference ID e.g. REF-AB12CD]
        │
        │  2. Patient clicks "Notify Hospital & Proceed to ED"
        ▼
POST /api/pre-arrival
        │  Saves Pre_Arrival_Triage row in TiDB with status = "Pending"
        │  Stores: ref_id, patient_name, ic_number, patient_phone,
        │          symptoms, ai_summary, admission_required, available_beds
        ▼
[Patient arrives at ED and shows Reference ID to nurse]
        │
        │  3. Nurse types REF-ID into Fast-Track panel on /index.html
        ▼
GET /api/lookup-reference/{ref_id}  (nurse/admin/doctor auth)
        │  Fetches PreArrivalTriage by ref_id
        │  Marks record status = "Claimed", claimed_by = nurse_username
        │  Returns patient data for triage form auto-fill
        ▼
[Triage form auto-populated: name, IC, phone, symptoms, AI triage priority]
```

---

### Flow B — ED Admission → Ward Bed Assignment

```
[Nurse fills Triage form on /index.html]
        │
        │  Optional: "Analyse & Triage" → POST /api/triage
        │  Groq AI evaluates symptoms → ai_summary cached
        ▼
[Nurse selects assigned doctor + clicks "Confirm Admission"]
        │
POST /api/admit
        │  Auto-generates Patient ID (P-XXXXXX) if blank
        │  Validates doctor exists in Users table
        │  Finds best bed: preferred_ward → any Empty → any Clearing
        │  Sets Bed.status = "Occupied" in TiDB
        │  Creates Patient row with all fields including ai_triage_summary
        ▼
[Ward Dashboard refreshes — bed tile turns red (Occupied)]
[Doctor sees new patient in Discharge Assistant dropdown]
```

---

### Flow C — Doctor Discharge → Agentic Orchestration → Bed Release

```
[Doctor opens /discharge-portal, selects admitted patient]
        │  GET /api/admitted-patients → ai_triage_summary shown as "Chief Complaint"
        ▼
[Doctor dictates clinical notes — text or voice]
        │  If voice: POST /api/transcribe-audio
        │            Groq Whisper large-v3-turbo → plain text
        ▼

── STEP 1: AI DRAFT  (no DB writes) ────────────────────────────────────────
POST /api/draft-discharge
        │  Gemini 2.5 Flash + DischargeDraftLite structured output
        │  Rewrites raw dictation → professional third-person clinical narrative
        │  Extracts: medications[], tca_plan
        │  Returns: { clinical_summary, medications[], tca_plan }
        ▼
[Doctor reviews AI draft in editable textareas — corrects any errors]

── STEP 2: HUMAN APPROVAL + FINALISATION ────────────────────────────────────
POST /api/process-discharge
        │  ①  Uses doctor's reviewed/edited text (Gemini skipped)
        │  ②  Snapshots full Patient row before deletion
        │  ③  Creates DischargeRecord: discharge_status = "Discharged"
        │  ④  Sets Bed.status = "Empty" → instantly visible on Ward Dashboard
        │  ⑤  Deletes Patient row atomically
        │
        │  ── ORCHESTRATOR AGENT (post-commit) ──────────────────────────────
        │  ⑥  _notify_pharmacy()  → logs e-Prescription dispatch (mock)
        │  ⑦  _notify_kin()       → logs SMS to next-of-kin (mock)
        ▼
[Frontend renders "Mission Control" success card:]
    ✅  Discharge Record & PDF Generated
    ✅  e-Prescription Routed to Pharmacy
    ✅  SMS Sent to Next-of-Kin
    ✅  Bed Released to ED Dashboard

GET /api/discharge-records/{id}/pdf
        │  ReportLab builds A4 PDF from DischargeRecord snapshot fields
        │  All timestamps converted UTC → MYT (UTC+8)
        │  Streamed as application/pdf download
```

---

### Database Tables

| Table | Purpose |
|---|---|
| `Beds` | 26 physical beds across 6 wards; status: `Empty` / `Occupied` / `Clearing` |
| `Patients` | Active admitted patients; **deleted on final discharge** |
| `Discharge_Records` | Permanent audit trail; 10-field patient snapshot preserves data after patient deletion |
| `Pre_Arrival_Triage` | Patient self-triage submissions; status: `Pending` → `Claimed` |
| `Users` | Staff accounts with roles: `nurse` / `doctor` / `admin` / `pharmacy` |

---

## Getting Started

### Prerequisites

- Python 3.11+
- A [TiDB Cloud](https://tidbcloud.com) cluster (free tier works)
- A [Groq](https://console.groq.com) API key
- A [Google AI Studio](https://aistudio.google.com) API key (Gemini)

### Installation

```bash
# Clone the repository
git clone https://github.com/your-org/bedswift.git
cd bedswift

# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# Install dependencies
pip install -r requirements.txt
```

### Configure environment

Create a `.env` file in the project root (see [Environment Variables](#environment-variables)).

### Run the server

```bash
uvicorn patient_api:app --reload --port 8001
```

Open [http://127.0.0.1:8001](http://127.0.0.1:8001) in your browser.

---

## Environment Variables

Create a `.env` file with the following keys:

```env
DATABASE_URL=mysql+pymysql://<user>:<password>@<host>:<port>/<db>?ssl_verify_cert=true&ssl_verify_identity=true
GROQ_API_KEY=gsk_...
GOOGLE_API_KEY=AIza...
SECRET_KEY=your-random-secret-key-here
```

| Variable | Description |
|---|---|
| `DATABASE_URL` | TiDB Cloud / MySQL connection string (SSL required for TiDB) |
| `GROQ_API_KEY` | Groq Cloud key for LLaMA triage + Whisper transcription |
| `GOOGLE_API_KEY` | Google AI Studio key for Gemini 2.5 Flash discharge drafting |
| `SECRET_KEY` | Random string used to sign Starlette session cookies |

---

## Demo Accounts

| Role | Username (HKL-format email) | Password |
|---|---|---|
| Ward Nurse | `azura.h@hkl.moh.gov.my` | `Hkl@Nrs2026!` |
| Doctor | `dr.ahmad.r@hkl.moh.gov.my` | `Hkl@Med2026!` |
| Administrator | `admin.ops@hkl.moh.gov.my` | `Hkl@Ops2026!` |

Login matching is **case-insensitive** on the email/username field.

> The **Admin** account can access all portals and use the **Reset Demo** button on the Ward Dashboard to wipe all patients and discharge records, and restore the 26 default beds.

If your database was seeded before these credentials existed, either use a fresh database or insert/update the `Users` table so these three accounts exist; `_seed_users()` only adds users whose usernames are missing.

---

## Future Scalability

1. **Replace mock agents with real integrations.**
   `_notify_pharmacy()` and `_notify_kin()` are isolated, single-responsibility functions designed to be swapped in. Production targets: HL7 FHIR pharmacy API, Twilio/AWS SNS for SMS.

2. **LangGraph multi-agent orchestration.**
   The `agents/scribe.py` skeleton shows the original intent. A full pipeline would chain `TriageAgent → BedAllocatorAgent → ScribeAgent → NotificationAgent` with shared state, retries, and LangSmith observability.

3. **WebSocket real-time push.**
   The Ward Dashboard currently polls every 30 seconds. Server-sent events or WebSocket broadcasts on bed-status changes would eliminate lag in high-volume ED scenarios.

4. **Multi-hospital / multi-tenant support.**
   Adding a `hospital_id` foreign key to `Beds`, `Patients`, and `Discharge_Records` would allow a single deployment to serve multiple hospital sites with fully isolated data.

5. **Async database layer.**
   SQLAlchemy `Session` is used synchronously inside `async` FastAPI handlers. Migrating to `AsyncSession` with `aiomysql` would improve throughput under concurrent load.

6. **Structured audit logging.**
   Agent actions currently print to stdout. Emitting structured JSON logs (patient ID, actor, action, timestamp) to a log aggregator (Datadog, GCP Logging) would satisfy clinical audit requirements.

---

*BedSwift v1.0 · TiDB Cloud · Groq · Google Gemini · Hospital Kuala Lumpur · Kementerian Kesihatan Malaysia*
