import os
import io
import uuid
import datetime
from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from groq import AsyncGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv

# ── PDF generation ────────────────────────────────────────────────────────────
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

from core.database import engine, Bed, Patient, DischargeRecord, PreArrivalTriage, update_bed_status, reseed_beds, init_db, get_user, verify_password, User
from core.schemas import DischargeDraft, DischargeDraftLite

load_dotenv()

_gemini = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)

# ---------------------------------------------------------------------------
# App & middleware
# ---------------------------------------------------------------------------

app = FastAPI(title="BedSwift")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "bedswift-secret-key-2026"),
    session_cookie="bedswift_session",
)
templates = Jinja2Templates(directory="templates")

# Ensure DB tables + default seeds exist at startup
init_db()

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _user(request: Request) -> dict | None:
    return request.session.get("user")

def _redirect_login() -> RedirectResponse:
    return RedirectResponse(url="/login", status_code=303)

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class SymptomRequest(BaseModel):
    symptoms: str


class TriageResponse(BaseModel):
    admission_required: bool
    ai_summary: str
    available_beds: int | None = None
    total_beds: int | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if _user(request):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(request=request, name="login.html", context={"error": ""})


@app.post("/login")
async def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    with Session(engine) as session:
        u = session.query(User).filter(User.username == username).first()
        if u and verify_password(password, u.password_hash):
            request.session["user"] = {
                "username":  u.username,
                "full_name": u.full_name or u.username,
                "role":      u.role,
                "initials":  "".join(w[0].upper() for w in (u.full_name or u.username).split()[:2]),
            }
            if u.role in ("nurse", "admin"):
                landing = "/"
            elif u.role == "pharmacy":
                landing = "/pharmacy"
            else:
                landing = "/ward"
            return RedirectResponse(url=landing, status_code=303)
    return templates.TemplateResponse(request=request, name="login.html",
                                      context={"error": "Invalid username or password."})


@app.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@app.get("/api/doctors")
async def list_doctors():
    """Return all users with role='doctor' — used to populate admission dropdown."""
    with Session(engine) as session:
        doctors = session.query(User).filter(User.role == "doctor").all()
        return [
            {"username": d.username, "full_name": d.full_name or d.username}
            for d in doctors
        ]


@app.get("/", response_class=HTMLResponse)
async def serve_ui(request: Request):
    user = _user(request)
    if not user:
        return _redirect_login()
    if user["role"] not in ("nurse", "admin"):
        return RedirectResponse(url="/ward", status_code=303)
    return templates.TemplateResponse(request=request, name="index.html", context={"user": user})


@app.get("/patient", response_class=HTMLResponse)
async def serve_patient_portal(request: Request):
    """Public patient-facing symptom checker — no login required."""
    return templates.TemplateResponse(request=request, name="patient.html", context={})


@app.get("/ward", response_class=HTMLResponse)
async def serve_ward(request: Request):
    user = _user(request)
    if not user:
        return _redirect_login()
    if user["role"] not in ("nurse", "doctor", "admin", "pharmacy"):
        return _redirect_login()
    return templates.TemplateResponse(request=request, name="doctor.html", context={"user": user})


@app.get("/doctor", response_class=HTMLResponse)
async def legacy_doctor_redirect(request: Request):
    """Keep old URL working — redirect to /ward."""
    return RedirectResponse(url="/ward", status_code=301)


@app.get("/api/dashboard")
async def dashboard_data(request: Request):
    """
    Return live bed stats.  Discharge records are only included for doctor/admin
    roles — nurses receive an empty list so the data is never exposed client-side.
    """
    current_user = _user(request)
    can_see_discharge = current_user and current_user.get("role") in ("doctor", "admin")
    with Session(engine) as db:
        beds = db.query(Bed).all()

        occupied  = sum(1 for b in beds if b.status == "Occupied")
        available = sum(1 for b in beds if b.status == "Empty")
        clearing  = sum(1 for b in beds if b.status == "Clearing")
        total     = len(beds)

        beds_list = [
            {"bed_id": b.bed_id, "ward": b.ward, "status": b.status}
            for b in beds
        ]

        # Per-ward occupancy breakdown
        ward_map: dict = {}
        for b in beds:
            if b.ward not in ward_map:
                ward_map[b.ward] = {"total": 0, "occupied": 0, "clearing": 0, "available": 0}
            ward_map[b.ward]["total"] += 1
            if b.status == "Occupied":
                ward_map[b.ward]["occupied"] += 1
            elif b.status == "Clearing":
                ward_map[b.ward]["clearing"] += 1
            else:
                ward_map[b.ward]["available"] += 1

        ward_stats = []
        for ward_name, counts in ward_map.items():
            in_use = counts["occupied"] + counts["clearing"]
            pct = round(in_use / counts["total"] * 100) if counts["total"] > 0 else 0
            ward_stats.append({
                "ward":      ward_name,
                "total":     counts["total"],
                "occupied":  counts["occupied"],
                "clearing":  counts["clearing"],
                "available": counts["available"],
                "pct":       pct,
            })
        ward_stats.sort(key=lambda x: x["pct"], reverse=True)

        occupancy_pct = round((occupied + clearing) / total * 100) if total > 0 else 0

        # Discharge records are role-gated:
        #   nurse  → empty list (data never sent to client)
        #   doctor → only records created by this doctor (created_by_username)
        #   admin  → all records (including legacy nulls)
        discharge_list = []
        if can_see_discharge:
            q = db.query(DischargeRecord).order_by(DischargeRecord.discharged_at.desc())
            if current_user.get("role") == "doctor":
                q = q.filter(
                    DischargeRecord.created_by_username == current_user.get("username", "")
                )
            discharge_list = [
                {
                    "id":               r.id,
                    "patient_id":       r.patient_id,
                    "bed_id":           r.bed_id,
                    "clinical_summary": r.clinical_summary or "",
                    "medications":      r.medications or "",
                    "tca_plan":         r.tca_plan or "",
                    "mo_name":          r.mo_name or "",
                    "department":       r.department or "",
                    "discharged_at":    r.discharged_at.strftime("%d %b %Y, %I:%M %p")
                                        if r.discharged_at else "—",
                    "discharge_status": r.discharge_status or "Ready for Bed Release",
                    "pharmacy_status":  r.pharmacy_status  or "Pending",
                }
                for r in q.limit(20).all()
            ]

    return {
        "stats": {
            "total":         total,
            "occupied":      occupied,
            "available":     available,
            "clearing":      clearing,
            "occupancy_pct": occupancy_pct,
        },
        "ward_stats":        ward_stats,
        "beds":              beds_list,
        "discharge_records": discharge_list,
    }


class BedStatusUpdate(BaseModel):
    bed_id: str
    status: str


@app.post("/api/beds/status")
async def set_bed_status(payload: BedStatusUpdate):
    """Update a bed's status directly from the doctor dashboard."""
    ok = update_bed_status(payload.bed_id, payload.status)
    if not ok:
        return {"success": False, "error": f"Bed '{payload.bed_id}' not found."}
    return {"success": True, "bed_id": payload.bed_id, "status": payload.status}


class AdmitRequest(BaseModel):
    patient_name:             str = ""
    patient_id:               str = ""   # auto-generated if blank
    preferred_ward:           str = ""   # hint from triage AI
    assigned_doctor_username: str = ""   # doctor assigned at triage
    patient_phone:            str = ""
    nok_phone:                str = ""
    ic_number:                str = ""   # IC / Passport number
    date_of_birth:            str = ""   # YYYY-MM-DD
    age:                      int = 0
    triage_priority:          str = ""   # e.g. P1 / P2 / P3
    admission_notes:          str = ""   # raw chief complaint from nurse/triage form
    ai_triage_summary:        str = ""   # AI-processed summary from /api/triage


@app.post("/api/transcribe-audio")
async def transcribe_audio(request: Request, audio: UploadFile = File(...)):
    """
    Receive a browser audio recording (WebM/opus) and transcribe it with
    Groq Whisper.  Returns { "text": "..." } on success.
    """
    current_user = _user(request)
    if not current_user or current_user.get("role") not in ("doctor", "admin"):
        raise HTTPException(status_code=403, detail="Forbidden")

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY not configured on server")

    # Read the uploaded audio bytes
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file received")

    try:
        client = AsyncGroq(api_key=api_key)
        # Groq Whisper expects a file-like tuple: (filename, bytes, mime_type)
        transcription = await client.audio.transcriptions.create(
            model="whisper-large-v3-turbo",
            file=("recording.webm", audio_bytes, "audio/webm"),
            response_format="text",
        )
        # response_format="text" returns a plain string directly
        text = transcription if isinstance(transcription, str) else transcription.text
        return {"success": True, "text": text.strip()}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@app.post("/api/admit")
async def admit_patient(payload: AdmitRequest):
    """
    Assign an available bed to a patient and create a Patient row.
    Preferred ward is tried first; falls back to any empty/clearing bed.
    Doctor assignment is validated and stored.
    """
    from fastapi import HTTPException
    pid = payload.patient_id.strip() or f"P-{str(uuid.uuid4())[:6].upper()}"

    with Session(engine) as session:
        # ── Validate assigned doctor ─────────────────────────────────────────
        doctor_username = payload.assigned_doctor_username.strip()
        doctor_name     = ""
        if doctor_username:
            doc = session.query(User).filter(
                User.username == doctor_username,
                User.role == "doctor",
            ).first()
            if doc is None:
                return {"success": False, "error": f"Doctor '{doctor_username}' not found or is not a doctor."}
            doctor_name = doc.full_name or doc.username

        # ── Find best bed ────────────────────────────────────────────────────
        def pick_bed(status: str, ward: str = "") -> Bed | None:
            q = session.query(Bed).filter(Bed.status == status)
            if ward:
                match = q.filter(Bed.ward == ward).first()
                if match:
                    return match
            return q.first()

        bed = (
            pick_bed("Empty", payload.preferred_ward)
            or pick_bed("Empty")
            or pick_bed("Clearing", payload.preferred_ward)
            or pick_bed("Clearing")
        )

        if bed is None:
            return {"success": False, "error": "No beds available for admission."}

        bed.status = "Occupied"
        session.add(Patient(
            patient_id               = pid,
            name                     = payload.patient_name.strip()   or "Anonymous",
            bed_id                   = bed.bed_id,
            admitted_at              = datetime.datetime.utcnow(),
            assigned_doctor_username = doctor_username                 or None,
            assigned_doctor_name     = doctor_name                     or None,
            patient_phone            = payload.patient_phone.strip()   or None,
            nok_phone                = payload.nok_phone.strip()       or None,
            ic_number                = payload.ic_number.strip()       or None,
            date_of_birth            = payload.date_of_birth.strip()   or None,
            age                      = payload.age                     or None,
            triage_priority          = payload.triage_priority.strip()    or None,
            admission_notes          = payload.admission_notes.strip()     or None,
            ai_triage_summary        = payload.ai_triage_summary.strip()   or None,
        ))
        session.commit()

        return {
            "success":              True,
            "patient_id":           pid,
            "bed_id":               bed.bed_id,
            "ward":                 bed.ward,
            "assigned_doctor_name": doctor_name,
        }


@app.get("/api/admitted-patients")
async def admitted_patients(request: Request):
    """
    Return admitted patients (bed still Occupied or Clearing).
    Role-filtered:
      doctor → only patients assigned to this doctor
      admin  → all patients
      others → empty list (nurses use ED Triage, not Discharge)
    """
    current_user = _user(request)
    if not current_user or current_user.get("role") not in ("doctor", "admin"):
        return []

    is_doctor = current_user.get("role") == "doctor"

    with Session(engine) as session:
        rows = session.query(Patient).order_by(Patient.admitted_at.desc()).all()
        result = []
        for p in rows:
            # Doctor: only see their own assigned patients
            if is_doctor and (p.assigned_doctor_username or "") != current_user.get("username", ""):
                continue
            bed = session.get(Bed, p.bed_id)
            if bed and bed.status in ("Occupied", "Clearing"):
                result.append({
                    "patient_id":               p.patient_id,
                    "name":                     p.name or "Anonymous",
                    "bed_id":                   p.bed_id,
                    "ward":                     bed.ward,
                    "department":               p.department or bed.ward,
                    "assigned_doctor_username": p.assigned_doctor_username or "",
                    "assigned_doctor_name":     p.assigned_doctor_name     or "",
                    "patient_phone":            p.patient_phone            or "",
                    "nok_phone":                p.nok_phone                or "",
                    "ic_number":                p.ic_number                or "",
                    "date_of_birth":            p.date_of_birth            or "",
                    "age":                      p.age                      or "",
                    "triage_priority":          p.triage_priority          or "",
                    "admission_notes":          p.admission_notes          or "",
                    "ai_triage_summary":        p.ai_triage_summary        or "",
                    "admitted_at":              p.admitted_at.strftime("%d %b %Y, %I:%M %p")
                                                if p.admitted_at else "—",
                    "label":                    f"{p.patient_id} — {p.bed_id} ({bed.ward})",
                })
        return result


# ── Pharmacy queue ────────────────────────────────────────────────────────────

@app.get("/api/pharmacy-queue")
async def pharmacy_queue(request: Request):
    """Return discharge records visible to the current role."""
    user = _user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    role     = user.get("role")
    username = user.get("username")
    if role not in ("pharmacy", "admin", "doctor"):
        raise HTTPException(status_code=403, detail="Forbidden")

    with Session(engine) as session:
        q = session.query(DischargeRecord)
        if role == "doctor":
            q = q.filter(DischargeRecord.created_by_username == username)
        records = q.order_by(DischargeRecord.discharged_at.desc()).all()

        result = []
        for r in records:
            patient = session.query(Patient).filter(Patient.patient_id == r.patient_id).first()
            meds = [m for m in (r.medications or "").split("\n") if m.strip()]
            # Prefer snapshot name (survives patient deletion); fall back to live row
            p_name = (getattr(r, "pt_name", None)
                      or (patient.name if patient else None)
                      or "—")
            result.append({
                "id":               r.id,
                "patient_id":       r.patient_id,
                "patient_name":     p_name,
                "bed_id":           r.bed_id            or "—",
                "ward":             r.department        or "—",
                "department":       r.department        or "—",
                "mo_name":          r.mo_name           or "—",
                "medications":      meds,
                "clinical_summary": r.clinical_summary  or "",
                "tca_plan":         r.tca_plan          or "",
                "pharmacy_status":  r.pharmacy_status   or "Pending",
                "payment_status":   r.payment_status    or "Pending",
                "discharge_status": r.discharge_status  or "Ready for Bed Release",
                "discharged_at":    r.discharged_at.strftime("%d %b %Y, %I:%M %p") if r.discharged_at else "—",
                "can_update_payment": False,
            })
        return result


class StatusUpdate(BaseModel):
    status: str


@app.post("/api/pharmacy-records/{record_id}/pharmacy-status")
async def update_pharmacy_status(record_id: int, payload: StatusUpdate, request: Request):
    user = _user(request)
    if not user or user.get("role") not in ("pharmacy", "admin"):
        raise HTTPException(status_code=403, detail="Forbidden")

    allowed = {"Pending", "Preparing", "Ready for Collection", "Collected"}
    if payload.status not in allowed:
        raise HTTPException(status_code=400, detail=f"Invalid pharmacy status: {payload.status}")

    with Session(engine) as session:
        rec = session.get(DischargeRecord, record_id)
        if not rec:
            raise HTTPException(status_code=404, detail="Record not found")
        rec.pharmacy_status = payload.status
        rec.updated_at      = datetime.datetime.utcnow()
        if (rec.discharge_status or "") != "Discharged":
            rec.discharge_status = "Ready for Bed Release"
        session.commit()
    return {"success": True, "pharmacy_status": payload.status}



@app.get("/api/discharge-records/{record_id}")
async def get_discharge_record(record_id: int, request: Request):
    """Workflow statuses for a discharge record (e.g. refresh UI after pharmacy updates)."""
    user = _user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    role     = user.get("role")
    username = user.get("username")
    if role not in ("nurse", "doctor", "admin"):
        raise HTTPException(status_code=403, detail="Forbidden")

    with Session(engine) as session:
        rec = session.get(DischargeRecord, record_id)
        if not rec:
            raise HTTPException(status_code=404, detail="Record not found")
        if role == "doctor" and rec.created_by_username != username:
            raise HTTPException(status_code=403, detail="Forbidden — not your record")
        # Nurse: only while discharge is still an active workflow (not yet finally discharged)
        if role == "nurse":
            ds = rec.discharge_status or ""
            if ds == "Discharged":
                raise HTTPException(
                    status_code=403,
                    detail="This record is already discharged.",
                )

        return {
            "id":               rec.id,
            "patient_id":       rec.patient_id,
            "bed_id":           rec.bed_id or "",
            "department":       rec.department or "",
            "pharmacy_status":  rec.pharmacy_status  or "Pending",
            "payment_status":   rec.payment_status   or "Pending",
            "discharge_status": rec.discharge_status or "Ready for Bed Release",
        }


@app.post("/api/discharge-records/{record_id}/finalize")
async def finalize_discharge(record_id: int, request: Request):
    """
    Final discharge confirmation: release bed for housekeeping and mark discharged.
    Allowed by nurse, doctor (own records), or admin.
    """
    user = _user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    role     = user.get("role")
    username = user.get("username")

    with Session(engine) as session:
        rec = session.get(DischargeRecord, record_id)
        if not rec:
            raise HTTPException(status_code=404, detail="Record not found")
        if role == "doctor" and rec.created_by_username != username:
            raise HTTPException(status_code=403, detail="Forbidden — not your record")
        if role not in ("nurse", "doctor", "admin"):
            raise HTTPException(status_code=403, detail="Forbidden")

        ds = rec.discharge_status or ""
        if ds == "Discharged":
            raise HTTPException(
                status_code=400,
                detail="This discharge has already been completed; duplicate final discharge is not allowed.",
            )
        # Pharmacy dependency removed: any non-discharged record can be released now.

        # Autonomous release: immediately make the bed available again.
        bed = session.get(Bed, rec.bed_id)
        if bed:
            bed.status = "Empty"
        rec.discharge_status = "Discharged"
        rec.updated_at       = datetime.datetime.utcnow()
        # Remove patient record so they no longer appear in admitted list
        patient = session.query(Patient).filter(Patient.patient_id == rec.patient_id).first()
        if patient:
            session.delete(patient)
        session.commit()

    return {"success": True, "discharge_status": "Discharged", "bed_status": "Empty"}


# ── PDF discharge report ──────────────────────────────────────────────────────

_MYT = datetime.timezone(datetime.timedelta(hours=8))

def _to_myt(dt: datetime.datetime | None) -> datetime.datetime | None:
    """Convert a naive UTC datetime (as stored by SQLAlchemy) to MYT (UTC+8)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(_MYT)

def _fmt_myt(dt: datetime.datetime | None, fmt: str = "%d %b %Y, %I:%M %p MYT") -> str | None:
    """Format a UTC datetime as a MYT string, or return None if dt is None."""
    converted = _to_myt(dt)
    return converted.strftime(fmt) if converted else None


def _build_pdf(rec: DischargeRecord, patient) -> bytes:
    """Generate a professional discharge summary PDF using ReportLab."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=20*mm, bottomMargin=20*mm,
        leftMargin=20*mm, rightMargin=20*mm,
    )

    styles = getSampleStyleSheet()
    W      = A4[0] - 40*mm   # usable width

    def style(name, **kw):
        s = ParagraphStyle(name, parent=styles["Normal"], **kw)
        return s

    title_s    = style("title",    fontSize=16, fontName="Helvetica-Bold",   alignment=TA_CENTER, spaceAfter=2*mm)
    sub_s      = style("sub",      fontSize=9,  fontName="Helvetica",        alignment=TA_CENTER, textColor=colors.grey, spaceAfter=6*mm)
    head_s     = style("head",     fontSize=10, fontName="Helvetica-Bold",   spaceBefore=4*mm, spaceAfter=2*mm, textColor=colors.HexColor("#1e40af"))
    body_s     = style("body",     fontSize=9,  fontName="Helvetica",        leading=14)
    label_s    = style("label",    fontSize=8,  fontName="Helvetica-Bold",   textColor=colors.HexColor("#64748b"))
    footer_s   = style("footer",   fontSize=7,  fontName="Helvetica-Oblique",alignment=TA_CENTER, textColor=colors.grey)

    def lv(label, value):
        """2-cell [label, value] row for the detail table."""
        return [Paragraph(label, label_s), Paragraph(str(value) if value else "—", body_s)]

    story = []

    # ── Header ────────────────────────────────────────────────────────────────
    story.append(Paragraph("BedSwift Hospital Discharge Summary", title_s))
    story.append(Paragraph("Hospital Kuala Lumpur · Kementerian Kesihatan Malaysia", sub_s))
    story.append(HRFlowable(width=W, thickness=1.5, color=colors.HexColor("#2563eb"), spaceAfter=4*mm))

    # ── Resolve patient fields: prefer snapshot on rec, fall back to live patient row ──
    def _pt(snap_field, live_attr=None):
        """Return snapshot value from rec, falling back to the live patient row."""
        v = getattr(rec, snap_field, None)
        if v:
            return v
        if patient and live_attr:
            return getattr(patient, live_attr, None)
        return None

    # ── Patient details ───────────────────────────────────────────────────────
    story.append(Paragraph("Patient Information", head_s))
    pt_name  = _pt("pt_name",  "name")
    pt_dob   = _pt("pt_dob",   "date_of_birth")
    pt_age   = _pt("pt_age",   "age")
    pt_phone = _pt("pt_phone", "patient_phone")
    pt_nok   = _pt("pt_nok_phone", "nok_phone")
    pt_ic    = _pt("pt_ic",    "ic_number")

    age_str  = f"{pt_age} years old" if pt_age else None
    pd_rows = [
        lv("Patient Name",   pt_name),
        lv("Patient ID",     rec.patient_id),
        lv("IC / Passport",  pt_ic),
        lv("Date of Birth",  pt_dob),
        lv("Age",            age_str),
        lv("Patient Phone",  pt_phone),
        lv("NOK Phone",      pt_nok),
    ]
    t = Table(pd_rows, colWidths=[55*mm, W - 55*mm])
    t.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [colors.HexColor("#f8fafc"), colors.white]),
        ("GRID",           (0,0), (-1,-1), 0.3, colors.HexColor("#e2e8f0")),
        ("LEFTPADDING",    (0,0), (-1,-1), 6), ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING",     (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(t)
    story.append(Spacer(1, 4*mm))

    # ── Admission details ─────────────────────────────────────────────────────
    story.append(Paragraph("Admission Details", head_s))
    pt_admitted  = _pt("pt_admitted_at",     "admitted_at")
    pt_triage    = _pt("pt_triage_priority", "triage_priority")
    # Chief Complaint: prefer AI summary snapshot, fall back to raw admission notes, then live patient
    pt_ai_sum    = _pt("pt_ai_summary",      "ai_triage_summary")
    pt_chief_raw = _pt("pt_chief_complaint", "admission_notes")
    pt_chief     = pt_ai_sum or pt_chief_raw   # AI-rewritten summary is preferred

    # Try to get assigned doctor from live patient, then rec
    pt_doctor = (
        getattr(patient, "assigned_doctor_name", None)
        or getattr(patient, "assigned_doctor_username", None)
        or rec.mo_name
    )

    ad_rows = [
        lv("Admission Date/Time", _fmt_myt(pt_admitted) if pt_admitted else None),
        lv("Ward / Department",   rec.department),
        lv("Bed Number",          rec.bed_id),
        lv("Assigned Doctor",     pt_doctor),
        lv("Triage Priority",     pt_triage),
        lv("Chief Complaint",     pt_chief),
    ]
    t2 = Table(ad_rows, colWidths=[55*mm, W - 55*mm])
    t2.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [colors.HexColor("#f8fafc"), colors.white]),
        ("GRID",           (0,0), (-1,-1), 0.3, colors.HexColor("#e2e8f0")),
        ("LEFTPADDING",    (0,0), (-1,-1), 6), ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING",     (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(t2)
    story.append(Spacer(1, 4*mm))

    # ── Discharge details ─────────────────────────────────────────────────────
    story.append(Paragraph("Discharge Details", head_s))
    dd_rows = [
        lv("Discharge Date/Time", _fmt_myt(rec.discharged_at) if rec.discharged_at else None),
        lv("MO / Doctor",         rec.mo_name),
        lv("Department",          rec.department),
    ]
    t3 = Table(dd_rows, colWidths=[55*mm, W - 55*mm])
    t3.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [colors.HexColor("#f8fafc"), colors.white]),
        ("GRID",           (0,0), (-1,-1), 0.3, colors.HexColor("#e2e8f0")),
        ("LEFTPADDING",    (0,0), (-1,-1), 6), ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING",     (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(t3)
    story.append(Spacer(1, 3*mm))

    story.append(Paragraph("Clinical Summary", head_s))
    story.append(Paragraph(rec.clinical_summary or "—", body_s))
    story.append(Spacer(1, 3*mm))

    story.append(Paragraph("Medications Prescribed", head_s))
    meds = [m.strip() for m in (rec.medications or "").split("\n") if m.strip()]
    if meds:
        for m in meds:
            story.append(Paragraph(f"• {m}", body_s))
    else:
        story.append(Paragraph("None prescribed.", body_s))
    story.append(Spacer(1, 3*mm))

    story.append(Paragraph("TCA / Follow-up Plan", head_s))
    story.append(Paragraph(rec.tca_plan or "—", body_s))

    # ── Footer ────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 10*mm))
    story.append(HRFlowable(width=W, thickness=0.5, color=colors.HexColor("#e2e8f0"), spaceAfter=3*mm))
    now_myt = datetime.datetime.now(tz=_MYT)
    story.append(Paragraph(
        f"Generated by BedSwift · {now_myt.strftime('%d %b %Y %H:%M')} MYT · "
        "This document is computer-generated and does not require a signature.",
        footer_s,
    ))

    doc.build(story)
    buf.seek(0)
    return buf.read()


@app.get("/api/discharge-records/{record_id}/pdf")
async def download_discharge_pdf(record_id: int, request: Request):
    user = _user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    role     = user.get("role")
    username = user.get("username")

    with Session(engine) as session:
        rec = session.get(DischargeRecord, record_id)
        if not rec:
            raise HTTPException(status_code=404, detail="Record not found")
        if role == "doctor" and rec.created_by_username != username:
            raise HTTPException(status_code=403, detail="Forbidden — not your record")
        if role not in ("doctor", "admin"):
            raise HTTPException(status_code=403, detail="Forbidden")

        patient = session.query(Patient).filter(Patient.patient_id == rec.patient_id).first()
        pdf_bytes = _build_pdf(rec, patient)

    filename = f"discharge_{rec.patient_id}_{record_id}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/reset")
async def reset_demo(request: Request):
    """
    Wipe all patients + discharge records and restore the 26 default beds.
    Admin only.
    """
    from fastapi import HTTPException
    current_user = _user(request)
    if not current_user or current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    with Session(engine) as session:
        session.query(DischargeRecord).delete()
        session.query(Patient).delete()
        session.commit()
    reseed_beds()
    return {
        "success": True,
        "message": "Demo reset: 26 beds restored, patients and discharge records cleared.",
    }


@app.get("/discharge-portal", response_class=HTMLResponse)
async def serve_discharge_portal(request: Request):
    user = _user(request)
    if not user:
        return _redirect_login()
    if user["role"] not in ("doctor", "admin"):
        return RedirectResponse(url="/ward", status_code=303)
    return templates.TemplateResponse(request=request, name="discharge.html", context={"user": user})


@app.get("/pharmacy", response_class=HTMLResponse)
async def serve_pharmacy(request: Request):
    user = _user(request)
    if not user:
        return _redirect_login()
    if user["role"] not in ("pharmacy", "admin"):
        return RedirectResponse(url="/ward", status_code=303)
    return templates.TemplateResponse(request=request, name="pharmacy.html", context={"user": user})


@app.get("/history", response_class=HTMLResponse)
async def serve_history(request: Request):
    user = _user(request)
    if not user:
        return _redirect_login()
    if user["role"] not in ("doctor", "admin", "nurse"):
        return RedirectResponse(url="/ward", status_code=303)
    return templates.TemplateResponse(request=request, name="history.html", context={"user": user})


class DraftRequest(BaseModel):
    """Lightweight request for AI draft generation — no DB writes."""
    clinical_notes: str
    patient_id:     str = ""


class DischargeRequest(BaseModel):
    patient_id:    str
    bed_number:    str
    mo_name:       str
    department:    str
    clinical_notes: str = ""   # used when Gemini must re-run
    patient_phone: str = ""
    nok_phone:     str = ""
    # Human-in-the-Loop: pre-edited fields forwarded from the review step.
    # When non-empty, Gemini is skipped and the bed is released immediately.
    edited_summary:     str        = ""
    edited_medications: list[str]  = []
    edited_tca:         str        = ""


@app.post("/api/draft-discharge")
async def draft_discharge(request: Request, payload: DraftRequest):
    """
    Step 1 of the Human-in-the-Loop discharge flow.
    Runs Gemini to produce a draft — no DB writes, no bed changes.
    Returns {clinical_summary, medications, tca_plan} for the doctor to review.
    """
    current_user = _user(request)
    if not current_user or current_user.get("role") not in ("doctor", "admin"):
        return {"success": False, "error": "Only doctors and administrators can draft discharges."}

    if not os.getenv("GOOGLE_API_KEY"):
        return {
            "success": False,
            "error": "GOOGLE_API_KEY is not set on the server. Add it to your .env to enable Gemini drafting.",
        }

    if not payload.clinical_notes.strip():
        return {"success": False, "error": "Clinical notes cannot be empty."}

    _SCRIBE_SYSTEM_D = SystemMessage(content=(
        "You are an expert Medical Scribe. Transform the doctor's raw dictation into a polished "
        "clinical document. STRICT RULES:\n"
        "1. NEVER copy-paste — rewrite entirely in formal third-person clinical language.\n"
        "2. Structure: Presenting Complaint → History → Examination → Diagnosis → Management.\n"
        "3. Use correct medical abbreviations (SOB, BP, PR, SpO2, ECG, etc.).\n"
        "4. Keep clinical_summary to 3–6 concise sentences.\n"
        "5. Extract medications and TCA plan faithfully; do not invent details."
    ))
    notes = payload.clinical_notes.strip()
    try:
        # Use a slim schema (no bed_number) — Gemini structured output is much more reliable.
        structured_llm = _gemini.with_structured_output(DischargeDraftLite)
        messages = [
            _SCRIBE_SYSTEM_D,
            HumanMessage(content=notes),
        ]
        draft: DischargeDraftLite = await structured_llm.ainvoke(messages)
    except Exception as exc:
        # Include exception text so operators can diagnose (quota, auth, schema, etc.)
        err = str(exc).strip() or repr(exc)
        return {"success": False, "error": f"AI draft generation failed: {err}"}

    return {
        "success":          True,
        "clinical_summary": draft.clinical_summary,
        "medications":      draft.medications or [],
        "tca_plan":         draft.tca_plan or "",
    }


# ── Orchestrator Agent — simulated hospital logistics ────────────────────────

def _notify_pharmacy(medications: list[str], patient_name: str) -> None:
    """Mock: route e-Prescription to the hospital pharmacy system."""
    med_list = ", ".join(medications) if medications else "None"
    print(f"[AGENT ✅] e-Prescription dispatched → Pharmacy")
    print(f"           Patient : {patient_name}")
    print(f"           Drugs   : {med_list}")

def _notify_kin(nok_phone: str, patient_name: str, ward: str) -> None:
    """Mock: send SMS to next-of-kin via hospital comms gateway."""
    if not nok_phone:
        print(f"[AGENT ⚠️ ] NOK SMS skipped — no phone number on record for {patient_name}")
        return
    print(f"[AGENT ✅] SMS sent → Next-of-Kin ({nok_phone})")
    print(f"           Message : '{patient_name} has been discharged from {ward}. "
          f"Please collect their belongings at the Ward Nursing Station.'")

# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/process-discharge")
async def process_discharge_api(request: Request, payload: DischargeRequest):
    """
    Step 2 of the Human-in-the-Loop discharge flow.
    When 'edited_summary' is provided the doctor has reviewed the AI draft:
      – Gemini is skipped; the edited fields are used directly.
      – Record is saved with discharge_status = "Discharged".
      – Bed is immediately set to Empty and patient row deleted.
    Legacy path (no edited fields): runs Gemini and saves as Ready for Bed Release.
    mo_name and created_by_username are authoritative from the session, not the form.
    """
    # ── Override identity fields from session ───────────────────────────────
    current_user = _user(request)
    if not current_user or current_user.get("role") not in ("doctor", "admin"):
        return {"success": False, "error": "Only doctors and administrators can process discharges."}
    session_mo_name  = current_user.get("full_name", payload.mo_name) if current_user else payload.mo_name
    session_username = current_user.get("username")                   if current_user else None

    hitl_mode = bool(payload.edited_summary.strip())  # Human-in-the-Loop: doctor reviewed draft

    if hitl_mode:
        # Doctor has already reviewed the AI draft — use their edits directly.
        clinical_summary = payload.edited_summary.strip()
        medications_list = [m.strip() for m in payload.edited_medications if m.strip()]
        tca_plan         = payload.edited_tca.strip()
        final_bed        = payload.bed_number.strip()
    else:
        # Legacy path: run Gemini on the raw notes.
        if not payload.clinical_notes.strip():
            return {"success": False, "error": "Clinical notes cannot be empty."}
        _SCRIBE_SYSTEM = SystemMessage(content=(
            "You are an expert Medical Scribe. Transform the doctor's raw dictation into a polished clinical document.\n"
            "STRICT RULES: 1) Never copy-paste — rewrite entirely. 2) Third-person clinical language. "
            "3) Structure: Presenting Complaint → History → Examination → Diagnosis → Management. "
            "4) Use medical abbreviations. 5) 3–6 concise sentences. 6) Do not invent data.\n"
            "For bed_number, medications, tca_plan: extract faithfully."
        ))
        try:
            structured_llm = _gemini.with_structured_output(DischargeDraft)
            draft: DischargeDraft = await structured_llm.ainvoke([
                _SCRIBE_SYSTEM,
                HumanMessage(content=payload.clinical_notes.strip()),
            ])
        except Exception as exc:
            return {"success": False, "error": f"AI extraction failed: {exc}"}

        clinical_summary = draft.clinical_summary
        medications_list = draft.medications or []
        tca_plan         = draft.tca_plan or ""
        final_bed        = payload.bed_number.strip() or draft.bed_number.strip()

    medications_text = "\n".join(medications_list)
    nok_phone        = payload.nok_phone.strip() or ""

    # ── TiDB writes ─────────────────────────────────────────────────────────
    ward      = "Unknown"
    record_id = None
    try:
        with Session(engine) as session:
            bed = session.get(Bed, final_bed)
            if bed:
                ward = bed.ward

            # Snapshot the Patient row NOW — it will be deleted on finalise.
            pt = session.query(Patient).filter(
                Patient.patient_id == payload.patient_id.strip()
            ).first()

            now = datetime.datetime.utcnow()

            # HITL path: discharge is complete — release bed and delete patient atomically.
            patient_name_snap = getattr(pt, "name", None) or payload.patient_id
            if hitl_mode:
                if bed:
                    bed.status = "Empty"
                if pt:
                    session.delete(pt)
                discharge_status = "Discharged"
            else:
                discharge_status = "Ready for Bed Release"

            record = DischargeRecord(
                patient_id          = payload.patient_id.strip() or "Unknown",
                bed_id              = final_bed,
                clinical_summary    = clinical_summary,
                medications         = medications_text,
                tca_plan            = tca_plan,
                mo_name             = session_mo_name,
                department          = payload.department.strip(),
                created_by_username = session_username,
                discharged_at       = now,
                discharge_status    = discharge_status,
                pharmacy_status     = "Auto-Routed",
                updated_at          = now,
                # Patient identity snapshot (survives patient row deletion)
                pt_name             = getattr(pt, "name",              None),
                pt_ic               = getattr(pt, "ic_number",         None),
                pt_dob              = getattr(pt, "date_of_birth",     None),
                pt_age              = getattr(pt, "age",               None),
                pt_phone            = payload.patient_phone.strip() or getattr(pt, "patient_phone", None),
                pt_nok_phone        = nok_phone or getattr(pt, "nok_phone", None),
                pt_triage_priority  = getattr(pt, "triage_priority",   None),
                pt_admitted_at      = getattr(pt, "admitted_at",       None),
                pt_chief_complaint  = getattr(pt, "admission_notes",   None),
                pt_ai_summary       = getattr(pt, "ai_triage_summary", None),
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            record_id = record.id
    except Exception as exc:
        return {"success": False, "error": f"Database write failed: {exc}"}

    # ── Orchestrator Agent actions (run after DB commit) ────────────────────
    agent_log = {"pharmacy": False, "sms": False}
    if hitl_mode:
        try:
            _notify_pharmacy(medications_list, patient_name_snap)
            agent_log["pharmacy"] = True
        except Exception:
            pass
        try:
            _notify_kin(nok_phone, patient_name_snap, ward)
            agent_log["sms"] = bool(nok_phone)
        except Exception:
            pass
    # ────────────────────────────────────────────────────────────────────────

    return {
        "success":          True,
        "hitl":             hitl_mode,
        "record_id":        record_id,
        "patient_id":       payload.patient_id,
        "patient_name":     patient_name_snap,
        "bed_id":           final_bed,
        "ward":             ward,
        "clinical_summary": clinical_summary,
        "medications":      medications_list,
        "tca_plan":         tca_plan,
        "nok_phone":        nok_phone,
        "discharge_status": discharge_status,
        "pharmacy_status":  "Auto-Routed",
        "agent_log":        agent_log,
    }


# ── Patient Portal — Pre-Arrival Triage ──────────────────────────────────────

class PreArrivalRequest(BaseModel):
    ref_id:             str
    patient_name:       str = ""
    ic_number:          str = ""
    patient_phone:      str = ""
    symptoms:           str
    ai_summary:         str = ""
    admission_required: bool = False
    available_beds:     int | None = None


@app.post("/api/pre-arrival")
async def save_pre_arrival(payload: PreArrivalRequest):
    """Called by patient.html when 'Notify Hospital' is clicked. No auth required."""
    if not payload.ref_id.strip() or not payload.symptoms.strip():
        raise HTTPException(status_code=400, detail="ref_id and symptoms are required.")

    with Session(engine) as session:
        # Prevent duplicate ref IDs
        existing = session.query(PreArrivalTriage).filter(
            PreArrivalTriage.ref_id == payload.ref_id
        ).first()
        if existing:
            return {"success": True, "ref_id": payload.ref_id, "note": "already_saved"}

        record = PreArrivalTriage(
            ref_id             = payload.ref_id,
            patient_name       = payload.patient_name.strip()  or None,
            ic_number          = payload.ic_number.strip()     or None,
            patient_phone      = payload.patient_phone.strip() or None,
            symptoms           = payload.symptoms.strip(),
            ai_summary         = payload.ai_summary.strip()    or None,
            admission_required = "true" if payload.admission_required else "false",
            available_beds     = payload.available_beds,
            status             = "Pending",
            created_at         = datetime.datetime.utcnow(),
        )
        session.add(record)
        session.commit()

    return {"success": True, "ref_id": payload.ref_id}


@app.get("/api/lookup-reference/{ref_id}")
async def lookup_reference(ref_id: str, request: Request):
    """
    Nurse looks up a patient's pre-arrival record by their Reference ID.
    Returns enough data to auto-fill the ED Triage form.
    Requires nurse / admin / doctor session.
    """
    user = _user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if user.get("role") not in ("nurse", "admin", "doctor"):
        raise HTTPException(status_code=403, detail="Forbidden")

    with Session(engine) as session:
        rec = session.query(PreArrivalTriage).filter(
            PreArrivalTriage.ref_id == ref_id.upper().strip()
        ).first()
        if not rec:
            raise HTTPException(status_code=404, detail="Reference ID not found.")

        # Record whether this is the first time it has been claimed
        was_already_claimed = rec.status == "Claimed"

        # Mark as claimed on first access so subsequent duplicate lookups are detectable
        if not was_already_claimed:
            rec.status     = "Claimed"
            rec.claimed_by = user.get("username")
            session.commit()

        return {
            "ref_id":             rec.ref_id,
            "patient_name":       rec.patient_name       or "",
            "ic_number":          rec.ic_number          or "",
            "patient_phone":      rec.patient_phone      or "",
            "symptoms":           rec.symptoms           or "",
            "ai_summary":         rec.ai_summary         or "",
            "admission_required": rec.admission_required == "true",
            "available_beds":     rec.available_beds,
            "status":             rec.status,
            # True ONLY if nurse has previously looked this record up
            "already_claimed":    was_already_claimed,
            "created_at":         rec.created_at.strftime("%d %b %Y, %I:%M %p") if rec.created_at else "—",
        }


@app.post("/api/triage", response_model=TriageResponse)
async def triage(payload: SymptomRequest):
    """
    Accept patient symptoms, run Groq triage, and optionally query TiDB for
    live bed availability.
    """
    symptoms = payload.symptoms.strip()
    if not symptoms:
        return TriageResponse(
            admission_required=False,
            ai_summary="No symptoms were provided. Please describe how you feel.",
        )

    # --- AI triage via Groq ---
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return TriageResponse(
            admission_required=False,
            ai_summary="Server configuration error: GROQ_API_KEY is not set.",
        )

    client = AsyncGroq(api_key=api_key)

    system_prompt = (
        "You are an experienced triage nurse at a busy hospital. "
        "A patient will describe their symptoms. "
        "Assess whether they require hospital admission.\n\n"
        "Rules:\n"
        "1. The very first line of your response must be EXACTLY one of:\n"
        "   'ADMISSION REQUIRED' or 'ADMISSION NOT REQUIRED'\n"
        "2. Then write 2-4 concise sentences explaining the likely condition "
        "and your reasoning.\n"
        "3. Do not ask follow-up questions or add disclaimers."
    )

    chat = await client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Patient symptoms: {symptoms}"},
        ],
        temperature=0.3,
        max_tokens=300,
    )

    ai_response = chat.choices[0].message.content.strip()
    first_line = ai_response.split("\n")[0].upper()
    admission_required = (
        "ADMISSION REQUIRED" in first_line and "NOT" not in first_line
    )

    # --- Bed availability from TiDB (only when admission is needed) ---
    available_beds: int | None = None
    total_beds: int | None = None

    if admission_required:
        with Session(engine) as db_session:
            available_beds = (
                db_session.query(Bed)
                .filter(Bed.status.in_(["Empty", "Clearing"]))
                .count()
            )
            total_beds = db_session.query(Bed).count()

    return TriageResponse(
        admission_required=admission_required,
        ai_summary=ai_response,
        available_beds=available_beds,
        total_beds=total_beds,
    )
