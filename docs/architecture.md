# Mimari Yaklaşım — Agentic RAG

Bu doküman, projenin hedef mimarisini ve klasör yapısı kararlarını tanımlar.
Referans vizyon: [local_notes/VIZYON 1.md](local_notes/VIZYON%201.md)

Mevcut yapı doğru yolda (modüler `src/`, çoklu docker-compose, merkezi
config/logging). Soru şu: vizyondaki **multi-agent + MCP + evals** katmanlarını
bu iskelete nasıl oturturuz?

## 1. Sistem (Runtime) Mimarisi — Servis Topolojisi

```
┌─────────────┐     ┌──────────────────────────────────────┐
│  Frontend   │────▶│         FastAPI (Core API)             │
│ Streamlit/  │ SSE │  /chat /documents /search /health      │
│  Next.js    │◀────│  + Request-ID + Exception + Logging    │
└─────────────┘     └──────────────┬─────────────────────────┘
       ▲ HITL onay                 │ orchestrate
       │                  ┌─────────▼──────────────┐
       │                  │  Operator (ReAct agent) │  (stateful)
       │                  │  ├ knowledge_base_qa ───┼─▶ RAG loop
       │                  │  ├ sql_query / logs     │   (Researcher→
       │                  │  └ sql_execute (HITL) ──┼    Analyst→Auditor)
       │                  └──┬──────────┬───────────┘
       │           MCP tools │          │ checkpoint
       │              ┌──────▼───┐  ┌───▼────┐
       └─ approve ────│MCP Server│  │ Redis  │ (state/checkpoint)
                      │ SQL+File │  └────────┘
                      └────┬─────┘
        ┌──────────┬───────┴────────┬──────────────┐
   ┌────▼───┐ ┌────▼────┐    ┌──────▼─────┐  ┌──────▼──────┐
   │ Qdrant │ │Postgres │    │Embed/Rerank│  │   Phoenix   │
   │(hybrid)│ │  (SQL)  │    │  service   │  │ (tracing)   │
   └────────┘ └─────────┘    └────────────┘  └─────────────┘
```

Her kutu = bir `docker-compose include`'u (zaten kullanılan pattern).
Yeni eklenecekler: `redis`, `postgres`, `mcp-server`, opsiyonel `phoenix`.

## 2. Kod (Katman) Mimarisi — Önerilen `src/` Yapısı

Temel ilke: **dışarıdan içeriye bağımlılık** (router → service → domain →
adapter). Router asla doğrudan Qdrant'a dokunmaz; service katmanından geçer.

```
src/
├─ api/
│  └─ routers/        # SADECE HTTP: validate, çağır, dön. İş mantığı YOK
│     ├─ documents.py # ingest endpoint
│     ├─ search.py    # retrieval endpoint
│     ├─ chat.py      # agent çalıştırma + SSE streaming
│     └─ health.py    # qdrant_manager.health_check'i buraya bağla
│
├─ rag/               # ── ADIM 1: Advanced RAG ──
│  ├─ chunking.py     # heading-aware splitter
│  ├─ embeddings.py   # dense (fastembed) + sparse (BM25)
│  ├─ ingest.py       # parse→chunk→embed→upsert orchestration
│  ├─ retriever.py    # hybrid query + RRF fusion
│  └─ reranker.py     # BGE cross-encoder, top20→top5
│
├─ agents/            # ── ADIM 3: Multi-Agent ──
│  ├─ graph.py        # LangGraph StateGraph tanımı (düğüm + kenarlar)
│  ├─ state.py        # AgentState (TypedDict/Pydantic) — tek doğruluk kaynağı
│  ├─ nodes/          # researcher.py, analyst.py, auditor.py
│  ├─ checkpointer.py # Redis saver
│  └─ tools.py        # MCP client → LangChain tool bridge
│
├─ mcp_server/        # ── ADIM 2: MCP ──
│  ├─ server.py       # mcp[cli] FastMCP instance
│  └─ tools/          # sql_query.py (read-only guard), read_logs.py
│
├─ evals/             # ── ADIM 5: Evals ──
│  ├─ datasets/       # altın soru-cevap setleri
│  └─ ragas_runner.py # faithfulness, context precision
│
├─ adapters/          # dış sistem adaptörleri burada izole
│  └─ vector_store/
│     └─ qdrant.py       # QdrantManager: lifecycle + hybrid query/upsert/delete
├─ observability/     # logging, tracing, metrics setup
│
├─ schemas/           # Pydantic DTO'lar (request/response/domain)
├─ core/              # config, exceptions (mevcut ✅)
└─ app.py             # composition root: wiring + lifespan
```

**Neden böyle?**
- `rag/`, `agents/`, `mcp_server/` ayrı paketler → her vizyon adımı bağımsız
  test edilebilir/değiştirilebilir.
- Router'lar ince kalır → mevcut `documents.py`'daki gibi iş mantığının router'a
  sızması önlenir.
- `adapters/` adapter izolasyonu → yarın Qdrant yerine başka DB gelirse sadece bu
  katman değişir.

**Bağımlılık yönü (kural):** bağımlılık tek yöne akar; alt katman üst katmanı
import etmez.

```
api  ─┐
mcp  ─┼─▶ agents ─▶ rag ─▶ adapters ─▶ core
      (agents, rag'i import eder; rag asla agents'i import etmez)
```

> Not: `mcp_server` mantıken `api` gibi ikinci bir **giriş kapısıdır** — `agents`
> onu bir client olarak çağırır. Düz yapıda `src/` altında dursa da, rolü bir
> "service" değil entrypoint'tir.

## 3. Kritik Mimari Kararlar

| Karar                  | Öneri                                          | Gerekçe |
|------------------------|------------------------------------------------|---------|
| Agent orkestrasyonu    | Üstte tek **Operator** (`create_agent` ReAct); RAG döngüsü `knowledge_base_qa` tool'u olarak sarılı | Operator önce okuyup anlayıp sonra aksiyon alabilir (router'ın read/write'ı baştan sabitlemesi akışı hapsederdi). RAG'in kendi Researcher→Analyst→Auditor döngüsü tool içinde korunur. Bkz. `docs/agents/hitl_operator_plan.md` |
| State / persistence    | Redis checkpointer                             | Vizyon Adım 3: çökerse kaldığı yerden devam; HITL interrupt/resume için de zorunlu |
| Human-in-the-Loop      | `HumanInTheLoopMiddleware(interrupt_on={"sql_execute": True})` + SSE `approval_required` event | Gate tam `sql_execute` tool-call sınırında → "onaylanan = çalışan". Pause otomatik, resume harici: `/chat/approve` `/chat/reject` → `Command(resume={"decisions": [...]})` |
| MCP tool güvenliği     | `sql_query` read-only (sentinel_ro); `sql_execute` write (sentinel_rw + `ensure_write_safe`) sadece HITL onayıyla | İki katmanlı savunma; Vizyon: "sadece yetkili tool'larla" |
| Streaming              | FastAPI SSE (`StreamingResponse`)              | Tool-call trace'i frontend'e akıt (Adım 4) |
| Embedding              | Ayrı `embeddings.py` servisi, model adı config'de | 384-dim ayar mevcut; model değişimi tek yerden |
| Dependency injection   | FastAPI `Depends` + `app.py` wiring            | Singleton `qdrant_manager` yerine test edilebilir DI'a doğru evril |

## 4. Tipik İstek Akışı (chat)

```
Kullanıcı sorusu
  → /chat (veya /chat/stream — SSE açılır)
  → Operator (ReAct) niyeti anlar, tool seçer:
       ├─ Doküman sorusu → knowledge_base_qa
       │     → RAG döngüsü: Researcher → Analyst → Auditor (faithful? değilse loop) → Finalizer
       │     → grounded yanıt + citations (artifact üzerinden API'ye taşınır)
       ├─ Veri sorusu → sql_query / list_tables / describe_table (read-only)
       ├─ Log sorusu → read_logs
       └─ Değişiklik → önce SELECT ile etkilenecek satır önizlemesi (affected-rows preview),
             sonra sql_execute → HumanInTheLoopMiddleware PAUSE
             → /chat/approve|reject → resume
                  ├─ approve → yazma çalışır → sonuç yanıtı
                  └─ reject  → yazma atlanır → model bilgilendirilir
```

## 5. Kararların Gerekçesi (Neden bu yapı?)

Bu bölüm, ileride "neden böyle yapmıştık?" sorusuna cevap olması için tutulur.

### 5.1 Düz (flat) yapı vs `services/` çatısı — **düz seçildi**

İki seçenek değerlendirildi:

- **A) Düz:** `src/rag/`, `src/agents/`, `src/mcp_server/` doğrudan `src/` altında.
- **B) Gruplu:** `src/services/rag/`, `src/services/agents/`, `src/services/mcp/`.

**Düz yapı (A) seçildi.** Gerekçeler:
- Her yetenek (`rag`, `agents`, `mcp_server`) **first-class** görünür; vizyonun
  5 adımıyla klasörler birebir eşleşir → projeyi açan biri yapıdan yol haritasını
  okuyabilir.
- Import yolları kısa ve net: `src.rag.retriever` vs `src.services.rag.retriever`.
- `services/` kolayca "her şeyin atıldığı çöp klasöre" dönüşür; bu da yapının
  taşıdığı bilgiyi yok eder. Asıl önemli olan klasör adı değil, **katman ayrımı**
  (bkz. 5.2) — onu zaten bağımlılık kuralıyla koruyoruz.
- `mcp_server` zaten bir "service" değil **entrypoint**; onu `services/` içine
  koymak yanıltıcı olurdu (bkz. 5.3).

> Bu, küçük/orta ölçekte geçerli bir tercih. Paket sayısı çok artarsa (10+),
> ileride `services/` çatısına geçiş yeniden değerlendirilebilir.

### 5.2 Katman ayrımı klasör adından önemli

Üç modül **aynı tür şey değil**; bunu unutmamak gerekir:

| Modül         | Gerçekte ne?                                          | Katman             |
|---------------|-------------------------------------------------------|--------------------|
| `api/`        | HTTP giriş kapısı (REST + SSE)                        | interface          |
| `mcp_server/` | MCP giriş kapısı — kendi process'i olan, tool sunan   | interface / adapter|
| `agents/`     | Orkestrasyon (rag + mcp'yi *kullanır*)               | application        |
| `rag/`        | Domain yeteneği (saf iş mantığı)                      | service / domain   |
| `adapters/`   | Adapter — dış sistem detayları burada izole           | infrastructure     |
| `observability/` | Logging, tracing, metrics setup                    | cross-cutting      |
| `core/`       | Config, exceptions                                    | foundation         |

Kural: bağımlılık tek yöne akar (bkz. bölüm 2). `rag` bir gün `agents`'i import
etmeye başlarsa — klasör adı ne olursa olsun — mimari bozulmuş demektir.

### 5.3 `mcp_server` neden service değil entrypoint?

`mcp_server`, `api` gibi **ikinci bir giriş kapısıdır**: kendi process'inde koşar,
dışarıya tool sunar. `agents` onu bir *client* olarak çağırır. Yani mantıken
`rag`/`agents` ile aynı seviyede bir "service" değildir. Düz yapıda `src/` altında
dursa bile rolü entrypoint olarak konumlandırılmalı — bu, vizyondaki "MCP üzerinden
güvenli erişim" anlatısıyla da birebir örtüşür.

### 5.4 Diğer kritik kararların gerekçeleri

Runtime ve teknoloji seçimlerinin gerekçeleri için bkz. **bölüm 3 (Kritik Mimari
Kararlar)** — her satırda "neden" sütunu mevcut.

## 6. Uygulama Sırası

Bu mimari tek seferde değil, vizyon adımlarına paralel kurulur:

1. `rag/` — gerçek ingest + hybrid retrieval + rerank (Adım 1'i bitir)
2. `mcp_server/` — SQL ve dosya tool'ları (Adım 2)
3. `agents/graph.py` — LangGraph döngüsü + Redis checkpoint (Adım 3)
4. `api/chat.py` SSE + citations + HITL — frontend (Adım 4)
5. `evals/` + GitHub Actions CI gate — Faithfulness < 0.85 → merge blok (Adım 5)

## 7. Observability and Adapter Naming

Two naming updates were selected during the OpenTelemetry groundwork:

- `src/observability/` owns cross-cutting visibility concerns: structured logging,
  logging config, OpenTelemetry setup, and future metrics helpers. `core/` stays
  focused on foundation primitives such as config and exceptions.
- `src/adapters/vector_store/qdrant.py` replaces the previous storage module.
  The Qdrant code is not just a passive storage location; it is an external-system
  adapter that manages collection lifecycle, payload indexes, hybrid query, upsert,
  delete, and health checks. The class name remains `QdrantManager` because that
  behavior is broader than a simple client.

Updated dependency direction:

```text
api/mcp -> agents -> rag -> adapters -> core
observability is cross-cutting and is wired at the application boundary.
```
