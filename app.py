import base64
import chainlit as cl
from dotenv import load_dotenv
import io
import os
import json
import asyncio
from datetime import datetime
from reporting.pdf_generator import generate_discharge_summary_pdf

# MUST load before importing LangChain/Graph components
load_dotenv()

# Set up Google Cloud Speech-to-Text
from google.cloud import speech
from google.oauth2 import service_account

# Load your service account key
credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON") # Use a simpler JSON filename in your folder
client = speech.SpeechClient.from_service_account_json(credentials_path)

# LangChain/Graph imports
from workflow.graph import app_graph
from agents.dispatcher import dispatcher_agent
from core.state import BedFlowState # Ensure State is updated to hold a transcription

# Real-time state management for the Dashboard
# This is a mock simple real-time database. A true system would poll a Redis/SQL DB.
from core.state import real_time_dash

# Clinical State to hold processed data for report generation
@cl.on_chat_start
async def start():
    cl.user_session.set("log_view", "hide")
    
    # 🏥 SIMULATE MO LOGIN & CONTEXT
    # In reality, this comes from the hospital's Active Directory
    hospital_context = {
        "mo_name": "Dr. Umi Sania bt Mohamad Zaki",
        "department": "Department of General Surgery",
        "hospital": "Hospital Tanah Merah",
        "ward_assigned": "Surgical Ward 4"
    }
    cl.user_session.set("hospital_context", hospital_context)
    
    welcome_msg = f"""
🎙️ **BedSwift: Autonomous Ward Clerk**
*System Online | User: {hospital_context['mo_name']} | {hospital_context['department']}*

Tap the microphone on your mobile keyboard to dictate your 30-second discharge summary, or upload a photo of the BHT.
"""
    await cl.Message(content=welcome_msg).send()

    
@cl.on_audio_chunk
async def on_audio_chunk(chunk):
    # This function is triggered for every audio chunk (about 20ms)
    pass
    
@cl.on_audio_start
async def on_audio_start():
    # Start of the transcription process
    audio_config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=16000,
        language_code="en-US",
    )
    streaming_config = speech.StreamingRecognitionConfig(
        config=audio_config, interim_results=True
    )
    cl.user_session.set("speech_requests", asyncio.Queue())
    
    # Send the first streaming configuration message
    requests_queue = cl.user_session.get("speech_requests")
    requests_queue.put_nowait(speech.StreamingRecognizeRequest(streaming_config=streaming_config))

@cl.on_audio_end
async def on_audio_end(audio_bytes: bytes):
    # This function processes the final complete audio stream.
    requests_queue = cl.user_session.get("speech_requests")
    requests_queue.put_nowait(None) # Signal end of stream

    # Send the combined audio bytes to Google Speech for final transcription
    audio_content = speech.RecognitionAudio(content=audio_bytes)
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=16000,
        language_code="en-US",
    )
    response = client.recognize(config=config, audio=audio_content)

    final_transcription = ""
    for result in response.results:
        final_transcription += result.alternatives[0].transcript + " "

    # Proceed to process the transcription as if it were text input
    await process_dictation_input(final_transcription.strip(), [])

@cl.on_message
async def main(message: cl.Message):
    # This handles text and file input (BHT photo)
    # The microphone logic is handled by on_audio callbacks.
    if message.content:
        await process_dictation_input(message.content, message.elements)
    elif message.elements:
        # User uploaded only a file
        await process_dictation_input("", message.elements)

async def process_dictation_input(text_content: str, message_elements: list):
    # 1. Retrieve the active draft from memory (if one exists)
    active_draft = cl.user_session.get("processed_clinical_data")
    
    # 2. Build the Smart Instruction for the AI
    if active_draft:
        # If we have a draft, tell the AI we are EDITING it
        instruction = f"""
        You are a Clinical Scribe. You must UPDATE the current draft based on the doctor's new revision instructions.
        
        CURRENT DRAFT TO UPDATE:
        Bed: {active_draft.get('bed_number')}
        Summary: {active_draft.get('clinical_summary')}
        Meds: {active_draft.get('medications')}
        TCA: {active_draft.get('tca_plan')}
        
        DOCTOR'S REVISION: {text_content}
        
        Please rewrite and return the FULL updated clinical discharge data. Do not lose the previous information unless the doctor explicitly changed it.
        """
    else:
        # Brand new dictation
        instruction = f"Extract clinical discharge data from the following input: {text_content}"

    # 3. Build the Payload
    gemini_payload = [{"type": "text", "text": instruction}]
    
    # Handle files/images
    if message_elements:
        for element in message_elements:
            if "image" in element.mime:
                with open(element.path, "rb") as f:
                    b64_image = base64.b64encode(f.read()).decode("utf-8")
                    gemini_payload.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{element.mime};base64,{b64_image}"}
                    })

    # 4. Initialize State with the true voice/multimodal input
    # Grab the logged-in user details
    context = cl.user_session.get("hospital_context")

    state_to_process = {
        "patient_id": active_draft.get('patient_id') if active_draft else "AUTO-ASSIGN",
        "bed_number": active_draft.get('bed_number') if active_draft else "",
        "raw_input": gemini_payload, 
        "clinical_summary": "",
        "medications": [],
        "tca_plan": "",
        "actions_completed": [],
        "report_generated_url": "",
        # NEW: Add the context to the state!
        "mo_name": context["mo_name"],
        "department": context["department"]
    }
    
    # 5. Run AI Brain Workflow
    result = await app_graph.ainvoke(state_to_process)
    
    # Save processed data back to memory so it can be edited again if needed!
    cl.user_session.set("processed_clinical_data", result)
    
    # 6. Display the results clearly
    await display_clean_clinical_draft(result)

async def display_clean_clinical_draft(result: dict):
    # Only show the clean clinical data and the action buttons
    meds_str = "\n".join([f"- {m}" for m in result['medications']]) if result['medications'] else "- No medications listed."
    msg_content = f"""
### 🏥 MoH Discharge Summary Draft | {result['bed_number']}
*(Processed by Clinical Scribe Agent)*

**Clinical Summary:**
{result['clinical_summary']}

**Take-Away Medications:**
{meds_str}

**TCA Plan:**
{result['tca_plan']}
"""
    # Button configuration (using the JSON fix)
    actions = [cl.Action(name="approve_discharge", payload={"action": "trigger_dispatcher"}, label="✅ Approve & Activate Logistics")]
    
    # Send clean message, and hide developer view details
    await cl.Message(content=msg_content, actions=actions).send()

@cl.action_callback("approve_discharge")
async def on_approve(action: cl.Action):
    # This is the 1-click approval that activates the logistics system
    await action.remove()
    state = cl.user_session.get("processed_clinical_data")
    
    # 1. Run the Logistics Dispatcher Agent (The Act Phase)
    dispatcher_result = await dispatcher_agent(state)
    
    # 2. Generate the PDF/Word Report for the MO
    pdf_filename = generate_discharge_summary_pdf(state)
    
    # Update real-time state for dashboard
    real_time_dash[state['bed_number']] = 'Clearing'
    

    # Wipe the memory clean so the MO is ready for the next patient!
    cl.user_session.set("processed_clinical_data", None) 
    
    
    # 3. Present the clean autonomous output
    action_log = "\n".join(dispatcher_result['actions_completed'])
    final_output = f"""
### ✅ Autonomous Activation Complete

{action_log}

---
📄 **MoH Discharge Report (PDF) is now ready.**
"""
    # ACTUALLY send the physical file to the chat UI
    elements = [
        cl.File(
            name=f"MoH_Discharge_{state['bed_number']}.pdf",
            path=pdf_filename,
            display="inline",
        )
    ]
    
    await cl.Message(content=final_output, elements=elements).send()
    
