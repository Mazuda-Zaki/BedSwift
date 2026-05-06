from langgraph.graph import StateGraph, END
from core.state import BedFlowState
from agents.scribe import scribe_agent

def build_graph():
    workflow = StateGraph(BedFlowState)
    workflow.add_node("scribe", scribe_agent)
    workflow.set_entry_point("scribe")
    workflow.add_edge("scribe", END)
    return workflow.compile()

app_graph = build_graph()