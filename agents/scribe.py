import chainlit as cl
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from core.state import BedFlowState
from core.schemas import DischargeDraft

# Gemini 1.5 Flash is highly optimized for fast multimodal extraction
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)

@cl.step(type="tool", name="Scribe Agent")
async def scribe_agent(state: BedFlowState):
    structured_llm = llm.with_structured_output(DischargeDraft)
    
    # We construct a HumanMessage containing both text and any uploaded images
    message = HumanMessage(content=state["raw_input"])
    
    # Invoke the model
    result = await structured_llm.ainvoke([message])
    
    return {
        "bed_number": result.bed_number,
        "clinical_summary": result.clinical_summary,
        "medications": result.medications,
        "tca_plan": result.tca_plan
    }