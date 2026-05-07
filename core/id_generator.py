import datetime
from sqlalchemy.orm import Session

from core.database import Patient, PreArrivalTriage


def _extract_sequence(value: str, prefix: str) -> int | None:
    if not value or not value.startswith(prefix):
        return None
    suffix = value[len(prefix):]
    if len(suffix) != 4 or not suffix.isdigit():
        return None
    return int(suffix)


def generate_patient_id(db_session: Session) -> str:
    """
    Generate IDs in enterprise format: HKL-YYYYNNNN.
    Example: HKL-20260001, HKL-20260002, ...

    Uses both live patient IDs and pre-arrival reference IDs as sources so
    pending pre-arrivals don't collide with admitted patients.
    """
    year = datetime.datetime.now().year
    prefix = f"HKL-{year}"

    last_patient = (
        db_session.query(Patient.patient_id)
        .filter(Patient.patient_id.like(f"{prefix}%"))
        .order_by(Patient.patient_id.desc())
        .first()
    )
    last_prearrival = (
        db_session.query(PreArrivalTriage.ref_id)
        .filter(PreArrivalTriage.ref_id.like(f"{prefix}%"))
        .order_by(PreArrivalTriage.ref_id.desc())
        .first()
    )

    candidates: list[int] = []
    if last_patient and last_patient[0]:
        seq = _extract_sequence(last_patient[0], prefix)
        if seq is not None:
            candidates.append(seq)
    if last_prearrival and last_prearrival[0]:
        seq = _extract_sequence(last_prearrival[0], prefix)
        if seq is not None:
            candidates.append(seq)

    next_seq = (max(candidates) + 1) if candidates else 1
    return f"{prefix}{next_seq:04d}"
