# LangGraph Multi-Agent Katmanı — Öğretici Rehber

> Bu doküman bir **öğrenme rehberidir**: vizyondaki **Adım 3 (Multi-Agent)**
> katmanının `src/agents/` içine nasıl oturduğunu, hangi dosyada ne olması
> gerektiğini, `StateGraph` / conditional edge kavramlarını ve bu adımın
> `schemas/` ile `core/` katmanlarına getirdiği eklemeleri sektör standardıyla
> anlatır. Kod parçaları **örnektir** (illustrative) — imzayı/şekli göstermek
> içindir, kopyalanacak implementasyon değildir.
>
> İlgili: [../architecture.md](../architecture.md) ·
> [../local_notes/VIZYON 1.md](../local_notes/VIZYON%201.md)

---

## 0. Bir bakışta: nerede ne var?

```
src/
├─ api/routers/
│  └─ chat.py          # (YENİ) ince router: graph'ı çağır + SSE stream
├─ agents/             # ── "langchain alanı" — Adım 3'ün kalbi ──
│  ├─ state.py         # (YENİ) AgentState — paylaşılan tek doğruluk kaynağı
│  ├─ graph.py         # (YENİ) StateGraph: düğümler + (koşullu) kenarlar
│  ├─ nodes/           # (YENİ) her ajan bir fonksiyon
│  │  ├─ researcher.py
│  │  ├─ analyst.py
│  │  └─ auditor.py
│  ├─ tools.py         # (YENİ) MCP tool → LangChain tool köprüsü
│  ├─ checkpointer.py  # (YENİ) state persistence (önce in-memory, sonra Redis)
│  ├─ prompts/         # (VAR) her ajanın system prompt'u ayrı .md
│  └─ sql_agent.py     # (VAR) eski elle-yazılmış tek ajan — referans/legacy
├─ schemas/
│  └─ chat.py          # (YENİ) API DTO'ları: request + SSE event'leri + citation
└─ core/
   ├─ config.py        # (GENİŞLET) recursion limit, redis_url, LLM provider
   └─ exceptions.py    # (GENİŞLET) AgentError ailesi
```

Altın kural (bağımlılık yönü) hiç değişmez:

```
api → agents → rag → adapters → core
```

`agents` alt katmanları kullanır; `rag` asla `agents`'i import etmez.

---

## 1. Şu an neredeyiz?

`src/agents/sql_agent.py` **LangGraph kullanmıyor.** O, elle yazılmış bir
döngü: LLM'e MCP tool'larını verir, `for _ in range(agent_max_steps)` içinde
tool seçtirir, sonucu geri besler. Bu **tek ajanlık** bir akış — vizyonun
"junior" versiyonu.

> VIZYON 1, Adım 3: *"Lineer akışlar junior işidir; biz döngüsel (cyclical)
> yapı kuruyoruz."*

`sql_agent.py`'yi silmiyoruz — referans olarak duruyor (özellikle
`_openai_tools()` ve tracing deseni LangGraph'e taşınacak fikirler içeriyor).

---

## 2. LangGraph'in zihinsel modeli (önce bunu oturt)

LangGraph üç kavramdan ibarettir:

1. **State** — ortada paylaşılan bir veri kabı. Ajanlar **birbirini doğrudan
   çağırmaz**; hep state üzerinden konuşur. Bir düğüm state'i okur, üstüne ekler,
   güncel parçayı döndürür.
2. **Node (düğüm)** — bir fonksiyon. İmza hep aynı: `state al → state'in
   güncellenmiş parçasını döndür`.
3. **Edge (kenar)** — düğümler arası ok. İki çeşit:
   - **Normal edge:** "A bitince hep B'ye git."
   - **Conditional edge:** "A bitince bir karar fonksiyonu çalışsın, dönen
     etikete göre B'ye **veya** C'ye **veya** END'e git." → **döngü buradan doğar.**

Lineer chain ile farkı tam burada: conditional edge bir düğümü kendinden önceki
bir düğüme geri bağlayabilir (cycle). Auditor'ın Researcher'a geri dönmesi
ancak böyle mümkün.

---

## 3. `state.py` — paylaşılan durum (her şeyin temeli)

State, ajanlar arası **tek iletişim kanalıdır**. Senin akışın
(Researcher → Analyst → Auditor) için taşıması gerekenler:

```python
# ÖRNEK — şekli gösterir, son hali değil
from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    question: str                          # kullanıcının sorusu (girdi)
    messages: Annotated[list, add_messages]  # akıl yürütme/tool geçmişi
    retrieved_docs: list                   # Researcher'ın bulduğu kaynaklar
    draft_answer: str                      # Analyst'ın taslağı
    audit_verdict: dict                    # Auditor kararı: faithful mı?
    revision_count: int                    # döngü sayacı — sonsuz loop koruması
    final_answer: str                      # END'e giderken doldurulur
```

Öğrenilecek noktalar:

- **Reducer kavramı:** `Annotated[list, add_messages]` demek, "iki düğüm aynı
  anda `messages`'a yazarsa LangGraph bunları **birleştirsin**, üzerine yazmasın"
  demektir. Reducer olmayan alanlar (örn. `draft_answer`) son yazan kazanır
  (overwrite). Bu, LangGraph'in en sık yanlış anlaşılan ama en kritik konusu.
- **`revision_count` neden şart?** Auditor sonsuza kadar "yetersiz, geri dön"
  diyebilir. Bu sayaç + bir limit, mevcut `agent_max_steps`'in
  ([config.py](../../src/core/config.py)) graph karşılığıdır.

**Standart (önemli ayrım):** `AgentState`, graph'ın **iç (internal)** durumudur.
Bu **API DTO'su değildir.** Dışarıya (HTTP) bambaşka bir model döneceksin
(bkz. bölüm 8, `schemas/chat.py`). Sektör standardı: *internal state ile public
contract'ı asla aynı tipe bağlama* — iç state değişince API kırılmasın.

### 3.1 Derinlemesine: Reducer kavramı (LangGraph'in en kritik konusu)

Bu LangGraph'e özgü ve en sık yanlış anlaşılan konudur. Yavaş gidelim.

**Problem:** Her düğüm state'in **bir parçasını** döndürür. Peki dönen parça
mevcut state ile **nasıl birleşir?** İki olasılık var:

- **Üzerine yaz (overwrite):** yeni değer eskisini siler.
- **Birleştir (append/merge):** yeni değer eskisine eklenir.

**Reducer = bu birleştirme kuralını belirleyen fonksiyondur.** Her state alanı
için "bu alana yeni veri gelince ne yapayım?" sorusunun cevabıdır.

**Varsayılan: overwrite.** Bir alana reducer vermezsen LangGraph üzerine yazar
(son yazan kazanır):

```python
draft_answer: str        # reducer YOK → overwrite (Analyst yeni taslak yazınca eski gider — doğru)
```

**Append gereken yer: `messages`.** `messages` için overwrite felaket olur:
Researcher 2 mesaj ekledi, Analyst 1 mesaj daha ekleyecek — overwrite olsaydı
Analyst'ın dönüşü Researcher'ın mesajlarını **silerdi**. `add_messages` bunu çözer:

```python
from langgraph.graph.message import add_messages
messages: Annotated[list, add_messages]   # reducer VAR → ekle, üzerine yazma
```

`Annotated[list, add_messages]` şunu der: *"bu alan list, yeni veri gelince
`add_messages` ile birleştir."* `add_messages` sadece append değil, akıllıdır:
yeni mesajları sona ekler, aynı `id`'li mesaj gelirse o tek mesajı günceller,
LangChain mesaj tiplerini (`HumanMessage`/`AIMessage`/`ToolMessage`) düzgün işler.

**Neden bu kadar kritik? İki sebep:**

1. **Paralel düğümler.** İki düğüm aynı anda `messages`'a yazarsa, reducer
   olmadan biri diğerini ezer; `add_messages` ile ikisi de birikir. Reducer,
   **eşzamanlı yazımların** nasıl harmanlanacağının kuralıdır.
2. **Döngü.** Auditor→Researcher döngüsünde graph aynı düğümlerden defalarca
   geçer. Mesajlar birikmeli ki ajan önceki denemeleri görüp kendini düzeltsin.
   Overwrite olsaydı her döngüde hafıza sıfırlanırdı.

**Tasarım disiplini — alan alan karar ver.** State tasarlarken her alan için
sor: *"Yeni veri gelince eskisi silinsin mi, eklensin mi?"*

| Alan | Davranış | Reducer |
|------|----------|---------|
| `question` | hiç değişmez (girdi) | yok |
| `messages` | birikmeli | `add_messages` |
| `draft_answer` | son taslak kazanır | yok (overwrite) |
| `retrieved_docs` | duruma göre — biriksin mi, taze mi? | senin kararın |
| `revision_count` | her döngüde +1 | toplama reducer'ı veya düğümde elle artır |

`revision_count` iyi bir düşünme egzersizi: ister düğümde `+1` döndürürsün
(overwrite), ister bir toplama reducer'ı (`lambda a, b: a + b`) koyarsın — ama
**bilinçli** seç. Reducer'ı anlamanın özü bu: *her alanın birleşme kuralını sen
tasarlarsın.*

---

## 4. `tools.py` — MCP → LangChain köprüsü

Ajanlar "LangChain tool" formatı bekler; araçların ise MCP server'da
([../../src/mcp_server/tools/](../../src/mcp_server/tools/)). Bu dosya çeviriyi yapar.

`sql_agent.py` içindeki `_openai_tools()` zaten bu işin OpenAI sürümü. LangChain
tarafında `langchain-mcp-adapters` paketi MCP server'a bağlanıp tool'ları
otomatik LangChain tool'una çevirir.

```python
# ÖRNEK
from langchain_mcp_adapters.client import MultiServerMCPClient
# client.get_tools() → LangChain tool listesi → düğümler/ToolNode kullanır
```

**Standart:** Düğümler DB'ye **asla doğrudan** dokunmaz; hep bu köprüden geçer.
Böylece read-only SQL guard ([../mcp/sql_tool_design.md](../mcp/sql_tool_design.md))
ve güvenlik MCP katmanında kalır. (AGENTS.md: *"Let routers/agents call DBs or
MCP tools directly → never."*)

---

## 5. `nodes/` — ajanların kendisi

Her ajan **bir fonksiyon**. Tek sorumluluk ilkesi: Researcher cevap yazmaz,
Auditor veri çekmez.

```python
# ÖRNEK — nodes/researcher.py
async def researcher(state: AgentState) -> dict:
    # state["question"]'ı oku, MCP tool'larını çağır (tools.py üzerinden)
    return {"retrieved_docs": docs, "messages": [...]}
```

| Düğüm | Görevi | Kullandığı |
|-------|--------|-----------|
| `researcher.py` | Veriyi bulur | MCP tool'ları (`rag_search`, `sql_query`) |
| `analyst.py` | Context'ten cevap/grafik üretir | LLM |
| `auditor.py` | Cevabı kaynakla karşılaştırır (self-reflection) | LLM |

**Standart:**
- LLM çağrısı düğümde yapılır ama **prompt buraya hardcode edilmez.** Her ajanın
  system prompt'u `agents/prompts/*.md` içinde (mevcut
  [sql_agent_system.md](../../src/agents/prompts/sql_agent_system.md) deseni).
- Prompt'lar **İngilizce** (AGENTS.md kuralı).
- Her düğüm bir OpenTelemetry span'i olsun (mevcut `sql_agent.py`'deki `@traced`
  / span deseni) ki Phoenix'te reasoning ağacı görünsün.

---

## 6. `graph.py` — düğümleri bağlayan harita (StateGraph + conditional edge)

İşin kalbi. Burada `StateGraph` kurar, düğümleri ekler, kenarları çizersin.

```python
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
```

Karar fonksiyonu (router) — saf bir fonksiyon, sadece state'e bakıp **etiket**
döndürür, iş yapmaz:

```python
# ÖRNEK
def route_after_audit(state: AgentState) -> str:
    if state["audit_verdict"]["faithful"]:
        return "finish"
    if state["revision_count"] >= MAX_REVISIONS:   # güvenlik freni
        return "finish"
    return "revise"
```

Öğrenilecek noktalar:

- **`START` / `END`** LangGraph'in özel sentinel düğümleridir: girişi ve çıkışı
  işaretler.
- **conditional edge'in 3 parçası:** (kaynak düğüm, karar fonksiyonu, etiket→hedef
  haritası). Karar fonksiyonu **asla** state'i değiştirmez — sadece nereye
  gidileceğini söyler. (Mutasyon düğümde olur, yönlendirme edge'de.)
- **`recursion_limit`:** LangGraph'in kendi global güvenlik freni vardır; graph
  çağrılırken `config={"recursion_limit": N}` verilir. Senin `revision_count`'un
  *iş mantığı* freni, `recursion_limit` ise *altyapı* frenidir — ikisi farklı
  katman, ikisi de olmalı.

Bu graph tam olarak [architecture.md](../architecture.md) bölüm 4'teki akıştır:

```
Researcher → Analyst → Auditor
                          ├─ faithful değil → Researcher'a geri (loop)
                          └─ faithful       → END
```

---

## 7. `checkpointer.py` — state persistence

Graph her adımda state'i kaydeder ("checkpoint"). Bu iki şeyi açar:

1. **Devam edebilirlik:** sistem çökerse kaldığı yerden devam (VIZYON Adım 3).
2. **Human-in-the-Loop:** graph `interrupt()` ile durur, state checkpoint'te
   bekler, kullanıcı onaylayınca `Command(resume=...)` ile devam eder
   (architecture.md, kritik SQL onayı).

**Standart / sıralama:**
- **Önce in-memory ile başla** (`MemorySaver`) — graph'ı çalıştırmak için Redis
  şart değil.
- Redis **yeni altyapı** demektir; AGENTS.md "Ask first before adding a new
  database" diyor → eklemeden önce sor, sonra `infra/redis/docker-compose.yml`
  include'u olarak ekle.
- Her run bir `thread_id` ile izlenir (checkpointer'ın anahtarı). Bu `thread_id`
  genelde request_id veya konuşma id'sidir.

---

## 8. `schemas/` — buraya ne eklenecek? (API contract)

> Senin sorun: "şema alanına eklenecek bir şey var mı?" — **Evet, var ve şart.**

Mevcut `schemas/` ([response.py](../../src/schemas/response.py),
[search.py](../../src/schemas/search.py)) sağlam bir desen kurmuş:
`SuccessResponse[DataT]` zarfı + endpoint'e özel data modelleri. Aynı deseni
takip eden yeni bir dosya gerekir: **`schemas/chat.py`**.

İçinde olması gerekenler:

```python
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
```

**Neden ayrı `chat.py` (ve neden `AgentState`'i kullanmıyoruz)?**

- **Internal state ≠ public contract.** `AgentState` graph'ın iç çalışma kabı;
  değişirse API kullanıcısını ilgilendirmemeli. DTO'lar API'nin sözleşmesidir.
  Bu, **anti-corruption layer** / DTO ayrımıdır — endüstri standardı.
- **Streaming farklı bir model ister.** `/chat` SSE ile çalışacak; tek bir
  `response_model` yerine bir **event akışı** dönersin. Her event'in tipi olur
  (`tool_call`, `token`, `approval_required`, `final`). Bunları tek tip
  (discriminated union benzeri `type` alanı) ile modellemek standarttır.
- **Citations first-class.** Vizyon "her cümlenin yanına kaynak" istiyor; bu
  ancak `Citation` bir şema tipi olursa frontend'e taşınabilir.

**Standart:** Mevcut `SuccessResponse[ChatAnswer]` zarfını koru (non-streaming
varyant için); SSE event'leri zarfsız ham akar ama yine tipli olur. `tenant_id`
isimlendirmesini `search.py` ile birebir tut (tutarlılık).

---

## 9. `core/` — buraya ne eklenecek?

> Senin sorun: "core falan, eklenecek bir şey var mı?" — **Evet, iki dosyada.**

### 9.1 `core/config.py` (genişlet)

Mevcut config'de LangChain alanları **zaten konmuş** ama kullanılmıyor:
`openai_api_key`, `langchain_api_key`, `langchain_tracing_v2`,
`langchain_project` ([config.py:17-21](../../src/core/config.py)). Yani proje
LangChain'i bekliyor. Eklemen gerekenler:

- **Gerçek bir LLM sağlayıcısı.** Şu an `llm_provider` = huggingface/ollama
  (tool-calling için). Graph'ta üretim kalitesi istiyorsan buraya bir
  "chat model" ayarı (örn. OpenAI/Anthropic model adı) gelir — model adı **config'de**,
  kodda değil (architecture.md kararı: "model değişimi tek yerden").
- **`agent_recursion_limit: int`** — graph'ın altyapı freni (bölüm 6).
- **`agent_max_revisions: int`** — Auditor→Researcher döngü limiti (iş mantığı freni).
- **`redis_url: str | None`** — checkpointer Redis'e geçince.

**Standart:** Her yeni ayar **ortam değişkeni** olarak okunur (asla hardcode),
ve `.env.example` + docs güncellenir (AGENTS.md kuralı). Secret'lar `SecretStr`
ile (mevcut `hf_token`, `qdrant_api_key` deseni).

### 9.2 `core/exceptions.py` (genişlet)

Mevcut yapı **örnek alınası**: `AppException` tabanı + alan-bazlı aileler
(`RagError`, `SqlStoreError`, `VectorStoreError`) + her birinin merkezi handler'a
([exception_handlers.py](../../src/core/exception_handlers.py)) düşmesi. Agent
katmanı kendi ailesini ekler:

```python
# ÖRNEK — core/exceptions.py'ye eklenecek desen
class AgentError(AppException):                # taban: AGT_00 / 500
    ...

class AgentExecutionError(AgentError):        # graph bir düğümde patladı → 500
    ...

class AgentRecursionError(AgentError):        # recursion_limit aşıldı → 500
    ...

class ApprovalRequired(AgentError):           # HITL: kritik aksiyon onay bekliyor
    # bu bir HATA değil, bir DURUM — 202/409 gibi; loglanır ama "warning" değil
    ...
```

**Neden bu desen (sektör standardı)?**

- **Domain exception → HTTP eşlemesi tek yerde.** Düğümler `AgentError` fırlatır;
  `app_exception_handler` bunu otomatik standart JSON hata zarfına (`success:
  false`, `code`, `request_id`) çevirir. Router içinde `try/except` dağıtmazsın.
- **Hata kodu taksonomisi.** Mevcut kodlar `DOC_*`, `RAG_*`, `SQL_*`, `VEC_*`.
  Aynı disiplinle `AGT_*` ekle. Bu, log'larda ve frontend'de hatayı sınıflamayı
  sağlar — enterprise standardı.
- **`SqlGuardError` zaten örnek:** "bu bir internal failure değil, kasıtlı
  güvenlik reddi" notu var (403). HITL için aynı felsefe: `ApprovalRequired`
  bir çökme değil, bir **kontrol akışı durumu** — onu da öyle modelle.

**Standart:** Merkezi logging, request-id ve global exception handling'i bozma
(AGENTS.md). Yeni exception'lar mutlaka `AppException`'dan türesin ki handler
zinciri onları yakalasın.

---

## 10. Bağımlılıklar (`pyproject.toml`)

Şu an sadece `langchain-text-splitters` var (o da chunking için). Eklenecekler:
`langgraph`, `langchain-core`, muhtemelen `langchain-mcp-adapters`, ileride
`langgraph-checkpoint-redis`.

**Standart:** AGENTS.md → dependency eklemeden **önce sor**; `uv add ...` ile
ekle, `uv.lock`'u **elle düzenleme**.

---

## 11. Kurulum sırası (yol haritası)

1. `uv add langgraph langchain-core` + config'e gerçek LLM ayarı.
2. **`state.py`** — `AgentState`'i tasarla (her şey buna dayanır).
3. **`tools.py`** — MCP→LangChain köprüsü (`sql_agent.py`'deki mantığı taşı).
4. **`nodes/researcher.py`** tek başına çalışsın.
5. **`graph.py`** — önce `researcher → END`, `MemorySaver`. Çalıştır, gör.
6. `analyst.py` + `auditor.py` + **conditional edge** (döngü). İşin kalbi.
7. **`schemas/chat.py`** + **`api/routers/chat.py`** — SSE stream (Adım 4).
8. **`core/`**: `AgentError` ailesi + config limitleri; sonra Redis + `interrupt()`.
9. **`tests/agents/`** — LLM/MCP mock'lu: döngü kuruluyor mu? limit kesiyor mu?

**Test standardı:** AGENTS.md → "Mock LLM, Qdrant, MCP, Phoenix in tests."
Özellikle test et: (a) Auditor "revise" deyince Researcher'a dönüyor mu,
(b) `max_revisions` loop'u kesiyor mu, (c) `route_after_audit` saf mı (state'i
değiştirmiyor mu).

---

## 12. Özet zihin haritası

| Katman | Dosya | Sorumluluk | Anahtar standart |
|--------|-------|-----------|------------------|
| application | `agents/state.py` | paylaşılan durum + reducer'lar | internal state, DTO değil |
| application | `agents/graph.py` | StateGraph + conditional edge (döngü) | yönlendirme edge'de, mutasyon düğümde |
| application | `agents/nodes/*` | her ajan bir saf fonksiyon | tek sorumluluk; prompt .md'de |
| application | `agents/tools.py` | MCP→LangChain köprüsü | DB'ye asla doğrudan dokunma |
| application | `agents/checkpointer.py` | persistence + HITL | önce in-memory, sonra Redis (sor) |
| interface | `api/routers/chat.py` | ince router + SSE | mantık YOK, sadece graph'ı çağır |
| schema | `schemas/chat.py` | API DTO + SSE event + citation | public contract ≠ AgentState |
| foundation | `core/config.py` | limitler, LLM, redis_url | env'den oku, .env.example güncelle |
| foundation | `core/exceptions.py` | `AgentError` ailesi | AppException'dan türet, AGT_* kodları |
```

