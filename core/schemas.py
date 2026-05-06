from pydantic import BaseModel, Field


class DischargeDraftLite(BaseModel):
    """Structured output for AI draft only (no bed extraction — avoids Gemini noise)."""
    clinical_summary: str = Field(
        description=(
            "Professional third-person clinical narrative from doctor dictation; "
            "Presenting Complaint → History → Examination → Diagnosis → Management; 3–6 sentences."
        )
    )
    medications: list[str] = Field(description="Discharge medications as a list; empty if none.")
    tca_plan: str = Field(description="Follow-up / TCA plan text; 'None' if not specified.")


class DischargeDraft(BaseModel):
    bed_number: str = Field(description="The exact bed number (e.g., 'Bed 5'). If not found, output 'Unknown'.")
    clinical_summary: str = Field(
        description=(
            "A professional, third-person clinical narrative rewritten from the doctor's raw dictation. "
            "Must follow the structure: Presenting Complaint → History → Examination → Diagnosis → Management. "
            "3-6 sentences. Use formal medical language and abbreviations. NEVER copy-paste the raw input."
        )
    )
    medications: list[str] = Field(description="List of discharge medications. Empty list if none.")
    tca_plan: str = Field(description="Follow-up instructions (TCA). Output 'None' if not specified.")