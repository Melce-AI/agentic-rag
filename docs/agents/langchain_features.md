# LangChain Feature Rehberi — Kavramlar, Standartlar, Örnekler

> Bu doküman LangChain'in (v1.x dönemi) ana feature'larını **öğretici** olarak
> anlatır: her özelliğin "nedir / nerede / nasıl / sektör standardı" dört
> sorusuyla, detaylı örneklerle. Kod blokları **örnektir** (illustrative) —
> kavramı ve API'nin şeklini göstermek içindir.
>
> Kardeş doküman: [langgraph_guide.md](langgraph_guide.md) (StateGraph, state,
> reducer, conditional edge — düşük seviye graph). Bu doküman ise LangChain'in
> **yüksek seviye** soyutlamalarını (`create_agent`, middleware, tools) anlatır.
>
> ⚠️ **Sürüm notu:** LangChain'in API yüzeyi sürümle değişir (özellikle 0.x →
> 1.0 büyük bir kırılmaydı). Aşağıdaki **kavramlar kalıcıdır**; tam imzayı her
> zaman kurduğun sürümün dokümanıyla doğrula. `uv add langchain` ile gelen
> sürümü `uv pip show langchain` ile kontrol et.

---

## 0. Skills (Deep Agents)

**Skill nedir:** Bir alan uzmanlığını (workflow, en iyi pratikler, script,
template) bir **klasörde** paketleyen yapı. Klasörde bir `SKILL.md` dosyası +
yardımcı dosyalar bulunur. Fikir: tüm talimatları system prompt'a **baştan**
yüklemek yerine, ajan **sadece gerektiğinde** ilgili rehberi okusun → token
tasarrufu.

**`SKILL.md` yapısı:**

```yaml
---
name: skill-name              # zorunlu, klasör adıyla eşleşir
description: Ne yapar ve NE ZAMAN aktifleşir (zorunlu, max 1024 karakter)
license: ...                  # opsiyonel
compatibility: ...            # opsiyonel (ortam gereksinimleri)
metadata:                     # opsiyonel; interpreter skill'de entrypoint burada
  entrypoint: scripts/index.ts
allowed-tools: [...]          # opsiyonel; önceden onaylı tool'lar
---
# Buradan sonrası ajana talimatlar (markdown gövde)
```

**Progressive disclosure — 3 katman (prompt'un tüm skilleri okumamasını sağlayan
mekanizma tam burası):**

1. **Discovery (keşif):** Başlangıçta `SkillsMiddleware` skill klasörlerini
   tarar, **sadece frontmatter'ı** (name + description) parse eder ve system
   prompt'a enjekte eder. Yani prompt'a giren şey sadece bir-iki satırlık özet.
2. **Read (okuma):** Ajan, bir skill'in göreve uyduğuna karar verince **tüm
   `SKILL.md` içeriğini** `read_file` ile okur — o ana kadar gövde context'e
   girmemiştir.
3. **Execute (çalıştırma):** Ajan talimatları izler, atıfta bulunulan ek
   dosyaları (script, referans) yükler.

Sonuç: 50+ skill olsa bile context şişmez; çünkü ağır içerik sadece ilgili olan
için yüklenir.

**Kritik içgörü — Skills aslında bir MIDDLEWARE'dir:** LangChain bunu
`SkillsMiddleware` ile gerçekler. Yani "skill" sihirli yeni bir tür değil;
**bölüm 6'daki middleware deseninin** bir uygulamasıdır (her tur prompt'a skill
keşfi enjekte eden, gerektiğinde dosya okutan bir politika). Bu yüzden bu iki
kavram birbirine bağlı.

**Skill vs Tool — aynı şey değil, biri diğerini dışlamaz:**

| | **Skill** | **Tool** |
|--|-----------|----------|
| Ne sunar | **Talimat + bağlam** (nasıl yapılır bilgisi) | **Çalıştırılabilir eylem** (fonksiyon) |
| Yükleme | İlgili olunca okunur (progressive) | Her turda context'te hazır |
| Format | Klasör + `SKILL.md` | Ajana bağlı fonksiyon |
| Analoji | "uzmanlık el kitabı" | "düğmeye bas, iş yapılsın" |

Yani: **Tool** "fatura sil" eylemini *çalıştırır*; **Skill** "fatura iadesi
prosedürü şöyle işler, şu tool'ları şu sırayla kullan" diye *anlatır*. Birçok
gerçek senaryoda ikisi birlikte: skill talimatı verir, tool eylemi yapar.

**Interpreter skills:** Bir code interpreter ortamında ajana **import
edilebilir, test edilmiş kod modülleri** sunan özel skill türü. Ajan mantığı her
seferinde üretmek yerine deterministik yardımcıları import eder. Frontmatter'a
`metadata.entrypoint` eklenerek açılır.

**Hangi paket / nasıl açılır:**

```python
from deepagents import create_deep_agent
agent = create_deep_agent(
    model="openai:...",
    skills=["/skills/"],          # skill klasörlerinin yolu
    # arka planda SkillsMiddleware devreye girer
)
```

Skills, çekirdek `create_agent`'ın değil **`deepagents`** kütüphanesinin
(LangGraph üstüne kurulu) bir özelliğidir; `SkillsMiddleware` ile çalışır.
Ayrı bir `langchain-skills` deposu da vardır.

**Anthropic ile ilişki:** Bu desen Anthropic'in "Agent Skills" spesifikasyonuyla
**aynı** (SKILL.md + frontmatter + progressive disclosure). Bu repodaki
`AGENTS.md`'de gördüğün Claude Code "skills" de aynı fikrin bir uygulamasıdır.
LangChain Deep Agents bu açık deseni benimsemiştir — yani "Claude'un skill'i" ve
"LangChain'in skill'i" **aynı standardın** iki uygulamasıdır, rakip iki kavram
değil.

**Senin projene oturması:** Sentinel'in akışında bir skill, örneğin
"SQL denetim raporu nasıl hazırlanır" prosedürünü (`describe_table` → güvenli
`SELECT` deseni → bulguları raporlama) bir `SKILL.md` olarak paketleyebilir;
Researcher/Analyst bu skill'i sadece denetim görevinde okur. Tool'ların (MCP)
*eylemi*, skill *prosedürü* sağlar.

> **Zihinsel eşleme:** LangChain dünyasında *eylem = tool*,
> *prosedür/uzmanlık = skill*, *her tura uygulanan politika = middleware*
> (skill'in kendisi de bir middleware ile gelir), *orkestrasyon = graph/agent*.

Kaynaklar:
[Skills — LangChain Docs](https://docs.langchain.com/oss/python/deepagents/skills) ·
[Using skills with Deep Agents — LangChain Blog](https://www.langchain.com/blog/using-skills-with-deep-agents)

---

## 1. Ekosistem haritası: hangi paket ne işe yarar?

LangChain tek paket değil, bir paket ailesidir. Karıştırmamak için:

| Paket | Sorumluluk | Örnek içerik |
|-------|-----------|--------------|
| `langchain-core` | Temel soyutlamalar (taban) | `BaseMessage`, `BaseChatModel`, `tool`, Runnable |
| `langchain` | Yüksek seviye yapılar | `create_agent`, middleware, agent |
| `langgraph` | Düşük seviye orkestrasyon | `StateGraph`, checkpointer, conditional edge |
| `langchain-openai`, `langchain-anthropic`, `langchain-ollama` | Sağlayıcı entegrasyonları | `ChatOpenAI`, `ChatAnthropic` |
| `langchain-mcp-adapters` | MCP tool'larını LangChain tool'una çevirir | `MultiServerMCPClient` |
| `langsmith` | İzleme / değerlendirme (observability) | tracing, eval |

**Standart / sektör pratiği:**
- **Çekirdeğe (`langchain-core`) bağımlı kal, somut sağlayıcıya değil.** Kodun
  `BaseChatModel` ile konuşsun; `ChatOpenAI`'yi sadece kurulum (wiring) anında
  tanı. Bu, [langgraph_guide.md](langgraph_guide.md) bölüm 1'deki provider
  soyutlamasının LangChain karşılığıdır.
- **`create_agent` aslında `langgraph` üstünde kuruludur.** Yani yüksek seviye
  (LangChain agent) ile düşük seviye (LangGraph graph) **aynı motorun** iki
  katmanıdır. Basit işte `create_agent`, özel döngü/çok-ajan gerekince
  `StateGraph`'e inersin.

---

## 2. Chat Models — ajanın beyni

**Nedir:** Bir LLM'i tek tip arayüzle saran nesne. Sağlayıcı farkını gizler.

**Nerede:** Düğümlerin/agent'ın içinde, ama **seçim config'den** gelir.

```python
# init_chat_model: provider'ı string ile seç — kod provider-agnostik kalır
from langchain.chat_models import init_chat_model

model = init_chat_model("openai:gpt-4o-mini", temperature=0)
# veya "anthropic:claude-...", "ollama:llama3.1:8b"

resp = model.invoke("Merhaba")          # tek çağrı
resp = model.bind_tools([my_tool])      # tool-calling yeteneği ekle
```

**Sektör standardı:**
- **Model adını config'e koy** (kodda string sabitleme). Bu repo bunu zaten kural
  yapmış: `core/config.py` + architecture.md "model değişimi tek yerden".
- **Sıcaklık (temperature) ajan tipiyle eşleşsin:** araç çağıran / denetleyen
  ajanlarda `0` (deterministik); üretken/yaratıcı görevde daha yüksek.
- **`.bind_tools()`** modele "şu araçları çağırabilirsin" der; modelin
  döndürdüğü `tool_calls`'ı sen (veya agent loop) çalıştırır.

---

## 3. Messages — konuşmanın yapı taşı

**Nedir:** LangChain her şeyi **mesaj listesi** olarak modeller. Tipler:

| Tip | Anlamı |
|-----|--------|
| `SystemMessage` | sistem talimatı (rol/kural) |
| `HumanMessage` | kullanıcı girdisi |
| `AIMessage` | modelin cevabı (içinde `tool_calls` olabilir) |
| `ToolMessage` | bir tool'un sonucu (modele geri beslenir) |

```python
from langchain_core.messages import SystemMessage, HumanMessage

messages = [
    SystemMessage("You are a careful data analyst."),
    HumanMessage("En çok ciro yapan 3 ürün?"),
]
ai = model.invoke(messages)     # -> AIMessage; .tool_calls dolabilir
```

**Sektör standardı / bağ:**
- Bu liste, LangGraph state'indeki `messages` alanıdır — ve tam da bu yüzden
  `add_messages` **reducer**'ı gerekir (bkz. [langgraph_guide.md](langgraph_guide.md)
  bölüm 3.1): mesajlar üzerine yazılmaz, **birikir**.
- Modern modeller "content blocks" (metin + görsel + düşünce) destekler; `.content`
  her zaman düz string olmayabilir — tipini kontrol et.

---

## 4. Tools — çalıştırılabilir eylemin birimi

**Nedir:** Modelin çağırabileceği bir fonksiyon. Adı + açıklaması + parametre
şeması (signature) modele verilir; model "bunu şu argümanlarla çağır" der, sen
çalıştırırsın.

```python
from langchain_core.tools import tool

@tool
def get_revenue(product_id: str) -> float:
    """Return total revenue for a product. Use for sales questions."""
    ...
    return value
```

**Kritik detaylar (sektör standardı):**
- **Docstring = modelin gözüdür.** Model tool'u ne zaman/nasıl çağıracağını
  **açıklamadan** anlar. Belirsiz docstring = yanlış tool seçimi. Bu yüzden
  docstring net, eylem-odaklı ve "ne zaman kullan" bilgisini içermeli.
- **Tip ipuçları (type hints) şemaya dönüşür.** `product_id: str` modele "string
  ver" der. Pydantic ile daha zengin şema verebilirsin.
- **Az ve net tool > çok ve karışık tool.** Model 20 benzer tool arasında
  şaşırır. Gerekirse `LLMToolSelectorMiddleware` ile çağrı başına tool alt
  kümesi seç (bkz. bölüm 6).

**Senin projende:** Tool'ların MCP server'da yaşıyor
([../../src/mcp_server/tools/](../../src/mcp_server/tools/)). Bunları LangChain
tool'una `langchain-mcp-adapters` çevirir:

```python
from langchain_mcp_adapters.client import MultiServerMCPClient

client = MultiServerMCPClient({"sentinel": {...}})
lc_tools = await client.get_tools()     # MCP tool -> LangChain tool listesi
```

Yani "ajana yeni bir eylem ekle" = MCP'ye yeni tool ekle + köprüden geçir.
Güvenlik (read-only SQL guard) MCP katmanında kalır. (Tool = *eylem*; bir
prosedürü *anlatmak* istiyorsan o bir **skill**'dir, bkz. bölüm 0.)

---

## 5. `create_agent` — v1'in standart ajanı

**Nedir:** "model + tools + döngü"yü tek satırda kuran yüksek seviye fabrika.
Arka planda bir LangGraph graph'ı (ReAct tarzı döngü: model → tool → model …)
derler.

```python
from langchain.agents import create_agent

agent = create_agent(
    model="openai:gpt-4o-mini",
    tools=lc_tools,
    system_prompt="You are a careful data analyst...",
    # middleware=[...], response_format=..., checkpointer=...
)
result = agent.invoke({"messages": [HumanMessage("...")]})
```

**Ne zaman `create_agent`, ne zaman ham `StateGraph`?**

| Durum | Kullan |
|-------|--------|
| Tek ajan, "düşün → tool çağır → cevapla" döngüsü | `create_agent` |
| Çok ajan, özel yönlendirme, döngüsel denetim (Researcher↔Auditor) | `StateGraph` (langgraph_guide) |
| `create_agent` + araya davranış enjekte | `create_agent` + **middleware** |

**Senin projen için:** Vizyon Adım 3 çok-ajanlı **döngüsel** akış istiyor
(Auditor → Researcher geri dönüş). Bu, `create_agent`'ın tek-ajan döngüsünden
**daha geniştir** → ana orkestrasyonu `StateGraph` ile kurarsın. Ama tek tek
düğümleri (örn. Researcher) bir `create_agent` olarak gömebilirsin. İkisi aynı
motor olduğu için iç içe geçer.

---

## 6. Middleware — derinlemesine (bu dokümanın merkezi)

### 6.1 Nedir, neden var?

**Middleware = agent'ın çalışma döngüsünün belirli noktalarına takılan, yeniden
kullanılabilir davranış parçasıdır.** Web framework'lerindeki middleware ile
**birebir aynı fikir**: istek işlenirken araya girip öncesinde/sonrasında bir şey
yapan katman.

Bir agent döngüsü şöyle akar:

```
[before_agent]
   ↓
 ┌──────────────────────────────────────────┐
 │ [before_model] → MODEL ÇAĞRISI → [after_model] │  ← her tur tekrarlanır
 │        ↑                              ↓          │
 │   (tool sonucu)              [tool çağrıları]    │
 │        └──── [wrap_tool_call] ◀─────┘            │
 └──────────────────────────────────────────┘
   ↓
[after_agent]
```

Middleware bu **kanca (hook) noktalarına** kod takmandır. Amaç: ajanın çekirdek
mantığını (graph'ı) kirletmeden **kesişen kaygıları** (cross-cutting concerns)
eklemek — tıpkı logging/auth middleware'inin route handler'ı kirletmemesi gibi.

> Bu, bu projenin DNA'sıyla birebir uyumlu: FastAPI tarafında zaten request-id
> **middleware**'in ([../../src/app.py](../../src/app.py)) ve merkezi exception
> handler'ların var. Agent middleware, aynı disiplinin LangChain tarafı.

### 6.2 Kanca (hook) noktaları

| Hook | Ne zaman çalışır | Tipik kullanım |
|------|------------------|----------------|
| `before_agent` | run başında, bir kez | girdi doğrulama, kurulum |
| `before_model` | her LLM çağrısından önce | prompt'a bağlam ekle, mesajları buda |
| `wrap_model_call` | LLM çağrısını **sarar** (öncesi+sonrası+retry) | model fallback, retry, sıcaklık ayarı |
| `after_model` | her LLM cevabından sonra | çıktı doğrulama, guardrail, PII maskeleme |
| `wrap_tool_call` | tool çağrısını **sarar** | tool retry, sonuç dönüştürme, yetki |
| `after_agent` | run sonunda, bir kez | son loglama, temizlik |

İki stil var:
- **Node-style** (`before_model`/`after_model`): state'i okur, kısmi güncelleme döndürür.
- **Wrap-style** (`wrap_model_call`/`wrap_tool_call`): çağrıyı sarar; `handler`'ı
  sen çağırırsın, böylece **öncesini, sonrasını ve hata/retry'ı** kontrol edersin.

### 6.3 Hazır (built-in) middleware'ler — tekerleği yeniden icat etme

Sektör standardı: yaygın ihtiyaçlar için **hazır** middleware kullan:

| Middleware | İşi | Hangi vizyon adımı |
|-----------|-----|--------------------|
| `SummarizationMiddleware` | konuşma uzayınca geçmişi özetle (context taşmasın) | uzun chat |
| `HumanInTheLoopMiddleware` | kritik tool çağrısında dur, insan onayı bekle | **Adım 4 (HITL)** |
| `PIIMiddleware` / PII redaction | çıktıdaki kişisel veriyi maskele | güvenlik |
| `LLMToolSelectorMiddleware` | çağrı başına ilgili tool alt kümesini seç | çok tool'lu ajan |
| `ModelFallbackMiddleware` | birincil model patlarsa yedeğe geç | dayanıklılık |
| `ModelCallLimitMiddleware` / `ToolCallLimitMiddleware` | çağrı sayısını sınırla | maliyet/runaway koruma |

```python
from langchain.agents.middleware import HumanInTheLoopMiddleware, SummarizationMiddleware

agent = create_agent(
    model="openai:gpt-4o-mini",
    tools=lc_tools,
    middleware=[
        SummarizationMiddleware(model="openai:gpt-4o-mini"),
        HumanInTheLoopMiddleware(interrupt_on={"sql_query": True}),  # kritik SQL'de dur
    ],
)
```

> **Bağ:** `HumanInTheLoopMiddleware` tam olarak vizyonun "DELETE/UPDATE'te
> Onayla/Reddet butonu" (Adım 4) ihtiyacını karşılar — ve altında LangGraph
> `interrupt()` + checkpointer çalışır (bkz. langgraph_guide bölüm 7).
> `ToolCallLimitMiddleware` ise senin mevcut `agent_max_steps` korumanın
> hazır karşılığı.

### 6.4 Özel (custom) middleware — örnek

Diyelim her LLM çağrısından önce kullanıcının dilini system prompt'a enjekte
etmek, ve her tool çağrısını OpenTelemetry span'iyle sarmak istiyorsun:

```python
from langchain.agents.middleware import before_model, wrap_tool_call

@before_model
def inject_language(state) -> dict | None:
    # state'teki mesajlara bakıp prompt'a dil notu ekle
    return {"messages": [SystemMessage("Answer in the user's language.")]}

@wrap_tool_call
def trace_tools(request, handler):
    with tracer.start_as_current_span(f"tool.{request.tool.name}"):
        return handler(request)        # gerçek tool çağrısı; öncesi/sonrası senin
```

**Sektör standardı / ne zaman yazılır:**
- Hazır middleware ihtiyacı karşılıyorsa **yazma**, kullan.
- Davranış birden çok ajanda tekrar ediyorsa → middleware'e çıkar (DRY).
- Tek bir ajana özel, tek seferlik mantık → düğümün içinde kalsın, middleware
  yapma (gereksiz soyutlama).
- Middleware **idempotent ve yan-etkisiz olmaya** yakın olsun; sıralama önemli
  (liste sırası uygulanış sırasıdır — auth/limit middleware'leri başa koy).

### 6.5 Middleware vs node — karıştırma

| | Node (düğüm) | Middleware |
|--|-------------|------------|
| Ne | İş akışının bir adımı (Researcher) | Her adıma uygulanan **politika** |
| Sayı | Akışta sabit yerde | Döngünün her turunda tekrar |
| Örnek | "veriyi getir" | "her model çağrısından önce prompt'a bağlam ekle" |
| Analoji | Controller/handler | HTTP middleware |

### 6.6 Uçtan uca örnek: kritik SQL onayı (HITL) — 5 katman

Vizyon Adım 4'ün kalbi: *"Ajan `DELETE`/`UPDATE` çalıştıracaksa arayüzde
Onayla/Reddet butonu çıksın."* Bu **tek bir feature değil**, beş katmanın
birlikte çalışmasıdır. Tek tek izleyelim — bu örnek tüm dokümanı birbirine bağlar.

**Akışın resmi:**

```
1) Agent      Researcher bir tool çağırmak istiyor: sql_query("DELETE ...")
                 │
2) Middleware HumanInTheLoopMiddleware araya girer: "bu kritik" → interrupt()
                 │  (graph DURUR, state checkpointer'a yazılır)
3) API/SSE    router interrupt'ı yakalar → "approval_required" event'i akıtır
                 │
4) Frontend   Onayla/Reddet butonu gösterir; kullanıcı tıklar
                 │
5) API        Command(resume=karar) ile graph KALDIĞI YERDEN devam eder
                 │  onaylandıysa tool çalışır / reddedildiyse atlanır
              cevap stream edilir
```

**Katman 1 — Tool ve "kritik" tanımı.**
Hangi tool'un onay gerektireceğini middleware'e söylersin. `sql_query` yazma
içeriyorsa kritik. (Senin iki-katmanlı güvenliğin hâlâ geçerli: read-only rol +
`ensure_read_only()` yazıyı zaten **reddeder**; HITL bunun *üstünde* bir politika
katmanıdır — örn. ileride yazma yetkili bir tool eklersen onay şartı.)

**Katman 2 — Middleware `interrupt()` çağırır.**

```python
from langchain.agents.middleware import HumanInTheLoopMiddleware

agent = create_agent(
    model=..., tools=lc_tools,
    middleware=[HumanInTheLoopMiddleware(interrupt_on={"sql_query": True})],
    checkpointer=saver,         # ← ŞART: interrupt için state'i bir yere yazmalı
)
```

Burada öğrenilecek **en kritik nokta:** `interrupt()` bir exception fırlatıp
işi öldürmez — graph'ı **duraklatır** ve o ana kadarki state'i **checkpointer'a
kaydeder**. Bu yüzden checkpointer olmadan HITL **çalışmaz** (state'i nereye
saklayacak?). Bağ: [langgraph_guide.md](langgraph_guide.md) bölüm 7.

**Katman 3 — API interrupt'ı SSE event'ine çevirir.**
Graph'ı `astream` ile sürerken, akışta bir `__interrupt__` sinyali gelir.
Router bunu bir **trace event**'ine çevirir (DTO: `schemas/chat.py` →
`TraceEvent(type="approval_required", ...)`, bkz. langgraph_guide bölüm 8):

```python
async for chunk in agent.astream(inputs, config={"configurable": {"thread_id": tid}}):
    if "__interrupt__" in chunk:
        yield sse(TraceEvent(type="approval_required",
                             data={"tool": "sql_query", "sql": "...", "thread_id": tid}))
        return    # akış burada durur; karar ayrı bir istekle gelecek
    else:
        yield sse(...)   # normal trace/token event'leri
```

Standart: router yine **ince** kalır — kararı o vermez, sadece interrupt'ı
dışarı bildirir ve kullanıcı kararını içeri taşır.

**Katman 4 — Frontend butonu.**
Frontend `approval_required` event'ini görünce SQL'i + Onayla/Reddet butonunu
gösterir. Kullanıcı tıklayınca **ayrı bir endpoint'e** (örn. `POST /chat/resume`)
`{thread_id, decision}` gönderir. `thread_id` kritik: graph'ın **hangi duraklamış
konuşmaya** devam edeceğini bu söyler.

**Katman 5 — `Command(resume=...)` ile devam.**

```python
from langgraph.types import Command

# /chat/resume handler'ı:
async for chunk in agent.astream(
        Command(resume={"decision": decision}),         # "approve" | "reject"
        config={"configurable": {"thread_id": tid}}):   # AYNI thread_id
    yield sse(...)
```

`Command(resume=...)` graph'ı **tam kaldığı yerden** uyandırır (checkpointer'dan
state'i okuyarak). Onaylandıysa duraklatılan tool çalışır; reddedildiyse middleware
o tool'u atlar ve modele "reddedildi" bilgisini geri besler.

**Neden böyle tasarlanır? (sektör standardı)**
- **İnsan onayı = state'in kalıcı olması demektir.** Kullanıcı 2 dakika sonra
  tıklayabilir; süreç bellekte tutulamaz, checkpointer'a yazılmalı. Bu yüzden
  HITL ve persistence **ayrılmaz ikilidir.**
- **İki ayrı HTTP isteği, tek mantıksal konuşma.** Onay senkron bir blok değil;
  `thread_id` ile iki istek aynı graph örneğine bağlanır. (Senkron bekletmek —
  long-polling/bağlantıyı açık tutmak — ölçeklenmez; durdur-kaydet-devam et deseni
  enterprise standardıdır.)
- **Karar bir kontrol akışı durumudur, hata değil.** Bunu `core/exceptions.py`'de
  `ApprovalRequired` ile modellemek (langgraph_guide bölüm 9.2) — `SqlGuardError`
  felsefesiyle aynı: "çökme değil, kasıtlı bir duraklama."
- **Güvenlik katmanlıdır:** read-only rol (DB) + `ensure_read_only()` (tool) +
  HITL (politika). HITL en dış halka; alttaki ikisini **değiştirmez**, üstüne
  ekler.

---

## 7. Structured Output — modelden tipli veri al

**Nedir:** Modelin serbest metin yerine **şemaya uygun** (Pydantic) çıktı
vermesini zorlamak.

```python
from pydantic import BaseModel

class AuditVerdict(BaseModel):
    faithful: bool
    reason: str

agent = create_agent(model=..., tools=..., response_format=AuditVerdict)
# veya model.with_structured_output(AuditVerdict)
```

**Sektör standardı / bağ:** Senin **Auditor** ajanın tam buna muhtaç — "faithful
mı?" kararı serbest metin değil, **tipli** (`{faithful: bool, reason: str}`)
olmalı ki `route_after_audit` conditional edge'i (langgraph_guide bölüm 6)
güvenle dallanabilsin. Serbest metni parse etmeye çalışmak kırılgandır; structured
output endüstri standardıdır.

---

## 8. Memory / Persistence — checkpointer

**Nedir:** Agent state'ini adımlar arası kaydetme. `create_agent(checkpointer=...)`
veya `graph.compile(checkpointer=...)`. Her konuşma bir `thread_id` ile izlenir.

```python
agent = create_agent(model=..., tools=..., checkpointer=saver)
agent.invoke({"messages": [...]}, config={"configurable": {"thread_id": "user-42"}})
```

Detay [langgraph_guide.md](langgraph_guide.md) bölüm 7'de: önce in-memory
(`MemorySaver`), sonra Redis; HITL'i mümkün kılan da budur.

---

## 9. Streaming — kullanıcı "ne düşündüğünü" görsün

**Nedir:** Agent'ı adım adım akıtmak. `.stream()` / `.astream()` farklı modlar
sunar:

| Mod | Ne akıtır |
|-----|-----------|
| `values` | her adımdan sonra **tüm state** |
| `updates` | sadece o adımın **değişikliği** (hangi düğüm ne ekledi) |
| `messages` | token token LLM çıktısı |

```python
async for chunk in agent.astream(inputs, stream_mode="updates"):
    ...   # FastAPI SSE event'ine çevir
```

**Sektör standardı / bağ:** Vizyon Adım 4 "Step-by-Step Trace" istiyor →
`stream_mode="updates"` (hangi tool çağrıldı, ne döndü) frontend trace'ine,
`"messages"` ise cevabı token token yazmaya gider. Bu akışı FastAPI
`StreamingResponse` (SSE) ile dışarı verirsin — DTO'ların `schemas/chat.py`
içindeki `TraceEvent` (bkz. langgraph_guide bölüm 8).

---

## 10. Observability — LangSmith / tracing

**Nedir:** Her LLM çağrısını, tool çağrısını, gecikmeyi ve maliyeti izleme.
LangChain LangSmith'e ortam değişkenleriyle otomatik bağlanır.

**Senin projende zaten yer ayrılmış:** `core/config.py` içinde
`langchain_api_key`, `langchain_tracing_v2`, `langchain_project` var. Yani
LangSmith'i açmak için kod değil, **env** yeter.

**Standart kararı (önemli):** Bu proje observability'de **Phoenix/OpenTelemetry**
kullanıyor (`src/observability/tracing.py`, `@traced` decorator). LangChain
LangSmith'e meyleder; ama LangChain'i de OpenTelemetry'e bağlamak mümkün. İki
izleme sistemini birden açmadan önce **hangisi kanonik** kararını ver
(architecture.md observability bölümüyle tutarlı kal) — yoksa span'ler ikiye
bölünür.

---

## 11. Hepsini senin projene oturtmak

| LangChain feature | Senin projende karşılığı / nereye |
|-------------------|-----------------------------------|
| Chat model + provider soyutlama | `core/config.py`'den seçim; mevcut `Backend` deseninin yerini alır |
| Tools | MCP tool'ları → `agents/tools.py` köprüsü (`langchain-mcp-adapters`) |
| `create_agent` | tek düğümleri kurmakta (örn. Researcher) |
| `StateGraph` | ana çok-ajan **döngüsel** orkestrasyon (Adım 3) |
| `HumanInTheLoopMiddleware` | kritik SQL onayı (Adım 4 HITL) |
| `SummarizationMiddleware` / limit middleware | uzun chat + `agent_max_steps` koruması |
| Structured output | **Auditor** kararı → conditional edge |
| Streaming | `/chat` SSE trace (Adım 4) |
| Checkpointer | `agents/checkpointer.py` (in-memory → Redis) |
| Observability | mevcut Phoenix/OTel ile **tek kanonik** sistemde birleştir |

**Kurulum sırası önerisi (feature bazında):**
1. `init_chat_model` ile gerçek bir model + config (provider soyutlaması).
2. `langchain-mcp-adapters` ile tool köprüsü (`agents/tools.py`).
3. Tek düğümü `create_agent` ile çalıştır, gör.
4. `StateGraph`'e geç (çok ajan + döngü) — langgraph_guide.
5. Middleware ekle: önce `ToolCallLimit`, sonra `HumanInTheLoop`.
6. Structured output ile Auditor'ı sağlamlaştır.
7. Streaming + SSE (Adım 4).
8. Observability'i tek sisteme bağla.

---

## 12. Özet — kavram → bir cümle

- **Skill:** prosedür/uzmanlık (`SKILL.md` + progressive disclosure, `SkillsMiddleware`).
- **Tool:** çalıştırılabilir eylem. Docstring = modelin gözü.
- **Chat model:** beyin; provider config'den, kod agnostik.
- **Messages + reducer:** konuşma birikir, üzerine yazılmaz (`add_messages`).
- **`create_agent`:** tek-ajan döngüsünü tek satırda kurar (LangGraph üstünde).
- **Middleware:** her tura uygulanan politika; HTTP middleware ile aynı fikir.
  Kesişen kaygıları graph'ı kirletmeden ekler.
- **Structured output:** tipli karar → güvenli dallanma (Auditor).
- **Checkpointer:** state'i kaydet → devam + HITL.
- **Streaming:** kullanıcı süreci görsün (trace).
- **Observability:** her çağrıyı izle; tek kanonik sistemde topla.
