# ÖRNEK — agents/graph.py
from langgraph.graph import StateGraph, START, END
from src.agents.state import AgentState

def build_graph(checkpointer=None):
    g = StateGraph(AgentState)

    # 1) düğümleri kaydet
    g.add_node("researcher", researcher)
    g.add_node("analyst", analyst)
    g.add_node("auditor", auditor)

    # 2) normal (sabit) kenarlar
    g.add_edge(START, "researcher")
    g.add_edge("researcher", "analyst")
    g.add_edge("analyst", "auditor")

    # 3) CONDITIONAL EDGE — döngünün doğduğu yer
    g.add_conditional_edges(
        "auditor",          # bu düğümden sonra
        route_after_audit,  # karar fonksiyonu çalışır
        {                   # dönen etiket → gidilecek düğüm
            "revise": "researcher",   # halüsinasyon var → geri dön (CYCLE)
            "finish": END,            # faithful → bitir
        },
    )
    return g.compile(checkpointer=checkpointer)