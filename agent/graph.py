from langgraph.graph import StateGraph, END

from investigators.kubernetes import kubernetes_investigator
from investigators.logs import log_investigator
from investigators.metrics import metrics_investigator
from investigators.registry import registry_investigator

from agent.analysis import root_cause


graph = StateGraph(dict)

graph.add_node("kubernetes", kubernetes_investigator)
graph.add_node("logs", log_investigator)
graph.add_node("metrics", metrics_investigator)
graph.add_node("registry", registry_investigator)
graph.add_node("analysis", root_cause)

graph.set_entry_point("kubernetes")

graph.add_edge("kubernetes", "logs")
graph.add_edge("logs", "metrics")
graph.add_edge("metrics", "registry")
graph.add_edge("registry", "analysis")

graph.add_edge("analysis", END)

agent = graph.compile()