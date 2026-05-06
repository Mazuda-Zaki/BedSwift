import os
import chainlit as cl
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from datetime import datetime

def generate_discharge_summary_pdf(data: dict) -> str:
    """Generates an official MoH formatted Discharge Summary PDF."""
    
    bed = data.get('bed_number', 'Not Specified')
    patient_id = data.get('patient_id', 'PT-NEW-MO-Dictated') # Replace with true Patient Name later
    
    # Create the filename with patient info and timestamp
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    filename = f"MoH-Discharge-{patient_id.replace(' ','_')}-{timestamp}.pdf"
    
    # Save the file to the app's local user session data folder (cl.user_session.get("report_folder"))
    # For simulation, we'll save to a temp folder and set the URL to a mock value.
    file_path = os.path.join(os.getcwd(), filename)
    
    # Create the PDF Canvas
    c = canvas.Canvas(file_path, pagesize=A4)
    width, height = A4
    
    # Official MoH Header
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(width/2.0, height - 50, "MALAYSIA MINISTRY OF HEALTH")
    c.drawCentredString(width/2.0, height - 70, "HOSPITAL KLUSTER KELANTAN UTARA")
    
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(width/2.0, height - 100, "DISCHARGE SUMMARY REPORT")
    
    # Patient Data Section
    c.setFont("Helvetica", 12)
    c.drawString(50, height - 140, f"Patient Name/ID: {patient_id}")
    c.drawString(50, height - 160, f"Bed Number: {bed}")
    c.drawString(width - 250, height - 140, f"Report Date: {datetime.now().strftime('%Y-%m-%d')}")
    
    c.line(50, height - 180, width - 50, height - 180) # Separator Line
    
    # Clinical Data Sections
    current_y = height - 200
    sections = [
        ("Clinical Summary", data.get('clinical_summary', 'Not Dictated')),
        ("Medications (Discharge List)", data.get('medications', 'No Medications Listed')),
        ("TCA Plan (Follow-up)", data.get('tca_plan', 'None Specified'))
    ]
    
    for title, content in sections:
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, current_y, f"{title}:")
        current_y -= 20 # Move down for content
        
        c.setFont("Helvetica", 11)
        # Handle medications as a list...
        if isinstance(content, list):
            for med in content:
                # Add medication with bullet
                c.drawString(70, current_y, med)
                current_y -= 15
        else:
            # Handle long paragraphs by simple wrapping logic
            text = content
            lines = [text[i:i+80] for i in range(0, len(text), 80)] # Wrap at ~80 characters
            for line in lines:
                c.drawString(70, current_y, line)
                current_y -= 15
        
        current_y -= 20 # Add space before next section
        
        # Check for bottom of page... a true report generator needs complex wrapping.
        if current_y < 100:
            c.showPage() # Add a new page
            c.setFont("Helvetica", 11)
            current_y = height - 50 # Reset Y

    # Final Clinical Outcome Section
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, 100, "Final Clinical Outcome: Discharged (Medically Fit)")
    
    # MO Signature Block (Where the Responsibility is finalized)
    c.drawString(width - 250, 70, "Clinician's Signature (Required)")
    c.line(width - 250, 50, width - 50, 50)
    c.setFont("Helvetica", 10)
    c.drawString(width - 250, 40, "Medical Officer / Attending Physician")
    
    c.save() # Finalize the PDF file
    
    # Simulating a stored file URL
    # In a deployed app, this would be a URL pointing to the file stored in S3/Azure Blob.
    mock_url = f"https://stored-reports.malaysia-moh.gov.my/{filename}"
    cl.user_session.set("report_generated_url", mock_url)
    
    return file_path