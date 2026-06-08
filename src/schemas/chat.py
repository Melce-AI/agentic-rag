from pydantic import BaseModel, Field
# ÖRNEK — schemas/chat.py
class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    tenant_id: str = Field(..., min_length=1)   # search.py ile tutarlı
    thread_id: str | None = None                # devam eden konuşma için

class Citation(BaseModel):                       # her cümlenin kaynağı (Adım 4)
    document_id: str
    source_name: str
    heading_path: list[str]
    snippet: str

class ChatAnswer(BaseModel):
    answer: str
    citations: list[Citation]

# SSE event'leri — streaming trace için (Adım 4)
class TraceEvent(BaseModel):
    type: str          # "tool_call" | "tool_result" | "token" | "approval_required" | "final"
    node: str | None   # hangi düğümden geldi
    data: dict