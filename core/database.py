"""
TiDB database layer for BedSwift.
Provides SQLAlchemy ORM models for Beds, Patients, and Discharge_Records,
plus helpers to initialise the schema and seed default bed data.
"""

import os
import hashlib
import datetime
from dotenv import load_dotenv
from sqlalchemy import (
    create_engine,
    Column,
    String,
    Integer,
    DateTime,
    Text,
    inspect,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Session

load_dotenv()

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise EnvironmentError(
        "DATABASE_URL is not set. "
        "Add it to your .env file:\n"
        "  DATABASE_URL=mysql+pymysql://<user>:<password>@<host>:<port>/<db>?ssl_verify_cert=true&ssl_verify_identity=true"
    )

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,   # reconnect automatically if the connection drops
    pool_recycle=3600,    # recycle connections every hour
    echo=False,           # set True to log raw SQL for debugging
)

# ---------------------------------------------------------------------------
# ORM base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Bed(Base):
    __tablename__ = "Beds"

    bed_id = Column(String(50), primary_key=True, nullable=False)
    ward   = Column(String(100), nullable=False)
    status = Column(String(50), nullable=False, default="Empty")

    def __repr__(self) -> str:
        return f"<Bed {self.bed_id!r} ward={self.ward!r} status={self.status!r}>"


class Patient(Base):
    __tablename__ = "Patients"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(String(100), unique=True, nullable=False)
    name       = Column(String(200))
    bed_id     = Column(String(50))                    # logical FK to Beds.bed_id
    admitted_at = Column(DateTime, default=datetime.datetime.utcnow)
    notes      = Column(Text)
    # Doctor assignment (set at admission)
    assigned_doctor_username = Column(String(100), nullable=True)
    assigned_doctor_name     = Column(String(200), nullable=True)
    department               = Column(String(100), nullable=True)
    # Contact info (collected at admission)
    patient_phone            = Column(String(50),  nullable=True)
    nok_phone                = Column(String(50),  nullable=True)
    # Demographics
    ic_number                = Column(String(100), nullable=True)   # IC / Passport
    date_of_birth            = Column(String(20),  nullable=True)  # stored as YYYY-MM-DD
    age                      = Column(Integer,      nullable=True)
    # Triage context (saved at admission for doctor review at discharge)
    triage_priority          = Column(String(50),  nullable=True)
    admission_notes          = Column(Text,         nullable=True)  # raw nurse/patient text
    ai_triage_summary        = Column(Text,         nullable=True)  # AI-processed triage output

    def __repr__(self) -> str:
        return f"<Patient {self.patient_id!r} bed={self.bed_id!r}>"


class DischargeRecord(Base):
    __tablename__ = "Discharge_Records"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    patient_id       = Column(String(100), nullable=False)
    bed_id           = Column(String(50))
    clinical_summary = Column(Text)
    medications      = Column(Text)          # stored as newline-separated list
    tca_plan         = Column(Text)
    mo_name              = Column(String(200))
    department           = Column(String(100))
    report_url           = Column(String(500), nullable=True)
    created_by_username  = Column(String(100), nullable=True)  # reliable ownership key
    discharged_at        = Column(DateTime, default=datetime.datetime.utcnow)
    # Discharge workflow statuses (added via safe migration)
    discharge_status = Column(String(100), default="Ready for Bed Release")
    pharmacy_status  = Column(String(100), default="Auto-Routed")
    payment_status   = Column(String(100), default="Pending")
    updated_at       = Column(DateTime, default=datetime.datetime.utcnow)
    # Patient snapshot — captured at discharge creation so PDF survives patient row deletion
    pt_name             = Column(String(200), nullable=True)
    pt_ic               = Column(String(100), nullable=True)
    pt_dob              = Column(String(20),  nullable=True)
    pt_age              = Column(Integer,     nullable=True)
    pt_phone            = Column(String(50),  nullable=True)
    pt_nok_phone        = Column(String(50),  nullable=True)
    pt_triage_priority  = Column(String(50),  nullable=True)
    pt_admitted_at      = Column(DateTime,    nullable=True)
    pt_chief_complaint  = Column(Text,        nullable=True)  # admission_notes snapshot
    pt_ai_summary       = Column(Text,        nullable=True)  # ai_triage_summary snapshot

    def __repr__(self) -> str:
        return f"<DischargeRecord patient={self.patient_id!r} bed={self.bed_id!r}>"


class PreArrivalTriage(Base):
    """Self-service patient triage submitted via the Patient Portal (/patient)."""
    __tablename__ = "Pre_Arrival_Triage"

    id                 = Column(Integer,      primary_key=True, autoincrement=True)
    ref_id             = Column(String(20),   unique=True, nullable=False, index=True)
    patient_name       = Column(String(200),  nullable=True)
    ic_number          = Column(String(100),  nullable=True)
    patient_phone      = Column(String(50),   nullable=True)
    symptoms           = Column(Text,         nullable=False)
    ai_summary         = Column(Text,         nullable=True)
    admission_required = Column(String(10),   nullable=True, default="false")
    available_beds     = Column(Integer,      nullable=True)
    status             = Column(String(30),   nullable=False, default="Pending")  # Pending | Claimed
    claimed_by         = Column(String(100),  nullable=True)   # nurse username who claimed it
    attachment_path    = Column(String(500),  nullable=True)   # relative path under static/uploads/
    created_at         = Column(DateTime,     default=datetime.datetime.utcnow)

    def __repr__(self) -> str:
        return f"<PreArrivalTriage ref={self.ref_id!r} ic={self.ic_number!r}>"


class User(Base):
    __tablename__ = "Users"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    username      = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(64), nullable=False)
    role          = Column(String(50), nullable=False, default="nurse")
    full_name     = Column(String(200))

    def __repr__(self) -> str:
        return f"<User {self.username!r} role={self.role!r}>"


# ---------------------------------------------------------------------------
# Default seed data (mirrors data/hospital_beds.csv)
# ---------------------------------------------------------------------------

DEFAULT_BEDS = [
    # ── Surgical Ward (6 beds) ──────────────────────────────────────────────
    {"bed_id": "S1",   "ward": "Surgical",                  "status": "Occupied"},
    {"bed_id": "S2",   "ward": "Surgical",                  "status": "Occupied"},
    {"bed_id": "S3",   "ward": "Surgical",                  "status": "Occupied"},
    {"bed_id": "S4",   "ward": "Surgical",                  "status": "Occupied"},
    {"bed_id": "S5",   "ward": "Surgical",                  "status": "Occupied"},
    {"bed_id": "S6",   "ward": "Surgical",                  "status": "Clearing"},
    # ── Medical Ward (6 beds) ───────────────────────────────────────────────
    {"bed_id": "M1",   "ward": "Medical",                   "status": "Occupied"},
    {"bed_id": "M2",   "ward": "Medical",                   "status": "Occupied"},
    {"bed_id": "M3",   "ward": "Medical",                   "status": "Occupied"},
    {"bed_id": "M4",   "ward": "Medical",                   "status": "Occupied"},
    {"bed_id": "M5",   "ward": "Medical",                   "status": "Occupied"},
    {"bed_id": "M6",   "ward": "Medical",                   "status": "Empty"},
    # ── Orthopaedic Ward (4 beds) ───────────────────────────────────────────
    {"bed_id": "O1",   "ward": "Orthopaedic",               "status": "Occupied"},
    {"bed_id": "O2",   "ward": "Orthopaedic",               "status": "Occupied"},
    {"bed_id": "O3",   "ward": "Orthopaedic",               "status": "Occupied"},
    {"bed_id": "O4",   "ward": "Orthopaedic",               "status": "Empty"},
    # ── Paediatric Ward (4 beds) ─────────────────────────────────────────────
    {"bed_id": "P1",   "ward": "Paediatric",                "status": "Occupied"},
    {"bed_id": "P2",   "ward": "Paediatric",                "status": "Occupied"},
    {"bed_id": "P3",   "ward": "Paediatric",                "status": "Occupied"},
    {"bed_id": "P4",   "ward": "Paediatric",                "status": "Empty"},
    # ── ICU (3 beds) ────────────────────────────────────────────────────────
    {"bed_id": "ICU1", "ward": "ICU",                       "status": "Occupied"},
    {"bed_id": "ICU2", "ward": "ICU",                       "status": "Occupied"},
    {"bed_id": "ICU3", "ward": "ICU",                       "status": "Occupied"},
    # ── Obstetrics & Gynaecology (3 beds) ──────────────────────────────────
    {"bed_id": "OG1",  "ward": "Obstetrics & Gynaecology",  "status": "Occupied"},
    {"bed_id": "OG2",  "ward": "Obstetrics & Gynaecology",  "status": "Occupied"},
    {"bed_id": "OG3",  "ward": "Obstetrics & Gynaecology",  "status": "Empty"},
]


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


DEFAULT_USERS = [
    {"username": "azura.h@hkl.moh.gov.my",       "password": "Hkl@Nrs2026!",  "role": "nurse",    "full_name": "Nurse Azura Binti Hamid"},
    {"username": "dr.ahmad.r@hkl.moh.gov.my",    "password": "Hkl@Med2026!",  "role": "doctor",   "full_name": "Dr. Ahmad Razali"},
    {"username": "admin.ops@hkl.moh.gov.my",     "password": "Hkl@Ops2026!",  "role": "admin",    "full_name": "System Administrator"},
    {"username": "pharmacy1", "password": "pharmacy123", "role": "pharmacy", "full_name": "Pharmacy Counter"},
]


def _hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def verify_password(plain: str, hashed: str) -> bool:
    return _hash(plain) == hashed


def get_user(username: str) -> dict | None:
    with Session(engine) as session:
        u = session.query(User).filter(User.username == username).first()
        if u is None:
            return None
        return {"username": u.username, "role": u.role, "full_name": u.full_name}


def _safe_add_columns() -> None:
    """
    Safely add new columns to existing tables using ALTER TABLE.
    Runs only if the column does not already exist — no data loss.
    """
    migrations = {
        "Pre_Arrival_Triage": [
            ("attachment_path", "VARCHAR(500)"),
        ],
        "Patients": [
            ("assigned_doctor_username", "VARCHAR(100)"),
            ("assigned_doctor_name",     "VARCHAR(200)"),
            ("department",               "VARCHAR(100)"),
            ("patient_phone",            "VARCHAR(50)"),
            ("nok_phone",                "VARCHAR(50)"),
            ("ic_number",                "VARCHAR(100)"),
            ("date_of_birth",            "VARCHAR(20)"),
            ("age",                      "INT"),
            ("triage_priority",          "VARCHAR(50)"),
            ("admission_notes",          "TEXT"),
            ("ai_triage_summary",        "TEXT"),
        ],
        "Discharge_Records": [
            ("created_by_username",  "VARCHAR(100)"),
            ("discharge_status",     "VARCHAR(100)"),
            ("pharmacy_status",      "VARCHAR(100)"),
            ("payment_status",       "VARCHAR(100)"),
            ("updated_at",           "DATETIME"),
            ("pt_name",              "VARCHAR(200)"),
            ("pt_ic",                "VARCHAR(100)"),
            ("pt_dob",               "VARCHAR(20)"),
            ("pt_age",               "INT"),
            ("pt_phone",             "VARCHAR(50)"),
            ("pt_nok_phone",         "VARCHAR(50)"),
            ("pt_triage_priority",   "VARCHAR(50)"),
            ("pt_admitted_at",       "DATETIME"),
            ("pt_chief_complaint",   "TEXT"),
            ("pt_ai_summary",        "TEXT"),
        ],
    }
    with engine.connect() as conn:
        for table, columns in migrations.items():
            try:
                existing = {
                    row[0]
                    for row in conn.execute(text(f"SHOW COLUMNS FROM `{table}`"))
                }
            except Exception:
                continue  # table may not exist yet; create_all handles that
            for col_name, col_type in columns:
                if col_name not in existing:
                    conn.execute(
                        text(f"ALTER TABLE `{table}` ADD COLUMN `{col_name}` {col_type}")
                    )
                    print(f"[database] Added column {table}.{col_name}")
        conn.commit()


def init_db(seed: bool = True) -> None:
    """
    Create all tables that do not yet exist and optionally seed defaults.

    Call once at application startup:
        from core.database import init_db
        init_db()
    """
    Base.metadata.create_all(bind=engine)
    _safe_add_columns()

    if seed:
        _seed_beds()
        _seed_users()


def _seed_beds() -> None:
    """Insert the default beds only if the Beds table is currently empty."""
    with Session(engine) as session:
        if session.query(Bed).count() == 0:
            session.add_all([Bed(**row) for row in DEFAULT_BEDS])
            session.commit()
            print(f"[database] Seeded {len(DEFAULT_BEDS)} default beds.")
        else:
            print("[database] Beds table already populated — skipping seed.")


def _seed_users() -> None:
    """Upsert each default user — inserts missing ones, leaves existing ones untouched."""
    with Session(engine) as session:
        added = 0
        for u in DEFAULT_USERS:
            if not session.query(User).filter(User.username == u["username"]).first():
                session.add(User(
                    username=u["username"],
                    password_hash=_hash(u["password"]),
                    role=u["role"],
                    full_name=u["full_name"],
                ))
                added += 1
        if added:
            session.commit()
            print(f"[database] Added {added} missing user(s).")


def reseed_beds() -> None:
    """
    Drop all existing beds and replace with DEFAULT_BEDS.
    Use this once when the ward structure changes.

    Usage:
        python -c "from core.database import reseed_beds; reseed_beds()"
    """
    with Session(engine) as session:
        deleted = session.query(Bed).delete()
        session.add_all([Bed(**row) for row in DEFAULT_BEDS])
        session.commit()
        print(f"[database] Reseeded: removed {deleted} old beds, inserted {len(DEFAULT_BEDS)} beds.")


def update_bed_status(bed_id: str, new_status: str) -> bool:
    """
    Update the status of a single bed by its bed_id.

    Returns True if a row was updated, False if the bed was not found.

    Example:
        from core.database import update_bed_status
        update_bed_status("Bed 3", "Clearing")
    """
    with Session(engine) as session:
        bed = session.get(Bed, bed_id)
        if bed is None:
            return False
        bed.status = new_status
        session.commit()
        return True


def get_all_beds() -> list[dict]:
    """Return all beds as a list of plain dicts (safe to pass to UI layers)."""
    with Session(engine) as session:
        return [
            {"bed_id": b.bed_id, "ward": b.ward, "status": b.status}
            for b in session.query(Bed).all()
        ]
