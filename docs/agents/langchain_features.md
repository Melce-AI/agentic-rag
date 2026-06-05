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

### 0.1 Tam spesifikasyon (Agent Skills spec — referans)

Yukarısı kavramdı; aşağısı **resmi format** (kurmak isteyince birebir bu kurallara
uyacaksın).

**Dizin yapısı** — bir skill, en azından bir `SKILL.md` içeren bir klasördür:

```
skill-name/
├── SKILL.md          # Zorunlu: metadata + talimatlar
├── scripts/          # Opsiyonel: çalıştırılabilir kod
├── references/       # Opsiyonel: detaylı dokümantasyon
├── assets/           # Opsiyonel: template, görsel, veri dosyası
└── ...               # Ek dosya/klasörler
```

**Frontmatter alanları (kısıtlarıyla):**

| Alan | Zorunlu | Kısıt |
|------|---------|-------|
| `name` | Evet | Max 64 karakter; sadece küçük harf + rakam + tire; başta/sonda tire olamaz; ardışık `--` olamaz; **klasör adıyla eşleşmeli** |
| `description` | Evet | Max 1024 karakter, boş olamaz; "ne yapar **ve ne zaman** kullanılır" + ajanın eşleştireceği anahtar kelimeler |
| `license` | Hayır | Lisans adı veya pakete dahil lisans dosyası referansı (kısa tut) |
| `compatibility` | Hayır | Max 500 karakter; ortam gereksinimleri (hedef ürün, sistem paketleri, ağ erişimi). Çoğu skill'e gerekmez |
| `metadata` | Hayır | Serbest string→string map; anahtar adlarını çakışmayı önlemek için özgün tut |
| `allowed-tools` | Hayır | Önceden onaylı tool'lar, boşlukla ayrık string (**deneysel**, ajan implementasyonuna göre değişir) |

`name` örnekleri: ✅ `pdf-processing`, `data-analysis` · ❌ `PDF-Processing`
(büyük harf), `-pdf` (tire ile başlıyor), `pdf--processing` (ardışık tire).

`description` — iyi vs kötü:
- ✅ *"Extracts text and tables from PDF files, fills PDF forms, and merges PDFs.
  Use when working with PDF documents or when the user mentions PDFs, forms, or
  document extraction."*
- ❌ *"Helps with PDFs."* (ne zaman aktifleşeceği belirsiz → ajan seçemez)

`allowed-tools` örneği: `Bash(git:*) Bash(jq:*) Read`

**Gövde (body):** Frontmatter'dan sonraki markdown serbesttir. Önerilen bölümler:
adım adım talimatlar, girdi/çıktı örnekleri, sık uç durumlar (edge cases). Ajan
skill'i aktive edince **tüm gövdeyi** yükler → uzun içeriği ayrı dosyalara böl.

**Opsiyonel klasörler:**
- `scripts/` — ajanın çalıştırabileceği kod (Python/Bash/JS); kendi kendine
  yeten, hata mesajlı, uç durumları ele alan.
- `references/` — gerektiğinde okunan detaylı dokümantasyon (`REFERENCE.md`,
  `FORMS.md`, alana özel `finance.md` vb.). Küçük tut → daha az context.
- `assets/` — statik kaynaklar (template, görsel, lookup tablosu, şema).

**Progressive disclosure — token bütçeleri (somut sayılar):**

| Katman | Ne yüklenir | Bütçe |
|--------|-------------|-------|
| 1. Metadata | `name` + `description` (başlangıçta, **tüm** skill'ler için) | ~100 token |
| 2. Instructions | `SKILL.md` gövdesi (skill aktive olunca) | önerilen < 5000 token |
| 3. Resources | `scripts/`, `references/`, `assets/` dosyaları | sadece gerektiğinde |

Pratik kural: `SKILL.md`'yi **500 satırın altında** tut; detayı ayrı dosyalara taşı.

**Dosya referansları:** Skill kökünden **göreli yol** kullan, **bir seviye
derinlikte** tut (derin zincir kurma):

```markdown
See [the reference guide](references/REFERENCE.md) for details.
Run the extraction script: scripts/extract.py
```

**Doğrulama (validation):** `skills-ref` referans kütüphanesiyle frontmatter ve
isim kurallarını kontrol et:

```bash
skills-ref validate ./my-skill
```

> **Bu repoya bağ:** Bu spec'in `name` + `description` + progressive disclosure
> kuralları, bu projedeki **memory** sistemiyle (`MEMORY.md` indeksi + frontmatter'lı
> tek-konu dosyalar) ve Claude Code skill'leriyle birebir aynı felsefedir:
> *önce hafif metadata, gerekince ağır içerik.* Sentinel'e bir skill yazarsan
> (örn. `sql-audit-report/SKILL.md`), `description`'a denetim anahtar kelimelerini
> koy ki Auditor doğru anda aktive etsin.

Kaynaklar:
[Skills — LangChain Docs](https://docs.langchain.com/oss/python/deepagents/skills) ·
[Using skills with Deep Agents — LangChain Blog](https://www.langchain.com/blog/using-skills-with-deep-agents) ·
[Agent Skills Specification — agentskills.io](https://agentskills.io/llms.txt)

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

### 5.1 Deep Agents "harness" — üretim çatısı (`create_deep_agent`)

**Harness nedir:** Modelin **etrafındaki iskele**. `create_agent` sana ham bir
döngü verir; **Deep Agents** ise uzun süre çalışan, güvenilir ajanlar için
gereken üretim yeteneklerini hazır paketler. `create_deep_agent(...)` ile gelir
ve **dört kategoriden** oluşur (+ harness profiles):

```python
from deepagents import create_deep_agent
agent = create_deep_agent(
    model="anthropic:claude-sonnet-4-6",
    tools=[...],
    skills=["/skills/"],
    interrupt_on={"sql_query": True},   # HITL
    memory=["AGENTS.md"],
)
```

**1) Execution environment (yürütme ortamı) — ajan nerede iş yapar:**

| Katman | Ne sağlar | Bağ |
|--------|-----------|-----|
| **Tools** | domain eylemleri (DB, API, fonksiyon) | bölüm 4 — senin MCP tool'ların |
| **Virtual filesystem** | `ls`/`read_file`/`write_file`/`edit_file`/`glob`/`grep` (+ multimodal okuma) | skill/memory/context bunun üstünde çalışır |
| **Filesystem permissions** | hangi path okunur/yazılır — deklaratif, ilk-eşleşen kazanır | `.env`/credential koru, subagent'a dar yetki |
| **Code execution** | sandbox (`execute` shell) veya interpreter (`eval`, QuickJS JS) | deterministik hesap/araç çağrısı |

**2) Context management (bağlam yönetimi) — ajan ne bilir, ne hatırlar:**

| Katman | Davranış |
|--------|----------|
| **Skills** | progressive disclosure — sadece gerekince yüklenir (bkz. bölüm 0) |
| **Memory** | `AGENTS.md` dosyaları — **her zaman** yüklenir (skill'in tersi: progressive değil) |
| **Summarization + offloading** | konuşma/uzun tool sonuçları otomatik sıkıştırılır → context taşmaz |
| **Prompt caching** | sistem prompt'unun statik kısımları (talimat, memory, skill) cache'lenir → Anthropic'te **varsayılan açık**, gecikme+maliyet düşer |

> **Kritik ayrım — Skill vs Memory:** İkisi de dosya tabanlı ama zıt yüklenir.
> **Memory** (`AGENTS.md`) = "her zaman geçerli kurallar" → baştan yüklenir.
> **Skill** (`SKILL.md`) = "duruma özel prosedür" → sadece gerekince. Bu repodaki
> `AGENTS.md` zaten tam bu "memory" rolünde; Deep Agents bunu standart kabul
> ediyor (agents.md spec).

**3) Delegation (yetki devri) — büyük işi böl:**

| Katman | Ne yapar |
|--------|----------|
| **Task planning** | `write_todos` tool'u — yapılacakları statülerle (`pending`/`in_progress`/`completed`) izler |
| **Subagents** | `task` tool'u ile **geçici çocuk ajan** doğurur: kendi context'i, kendi tool'ları, paralel çalışır, sonunda **tek bir rapor** döner |

Subagent'ın değeri: ağır işi **izole** eder (ana ajanın context'ini kirletmez) →
token verimliliği + paralellik + uzmanlaşma. Senin Researcher/Analyst/Auditor
ayrımının Deep Agents karşılığı bir nevi budur.

**4) Steering (yönlendirme) — insan kontrolü:**
`interrupt_on={"tool_adı": True}` ile kritik tool çağrısında durur, insan onayı
bekler. Bu, bölüm 6.6'da uçtan uca anlattığım **HITL**'in Deep Agents'taki hazır
arayüzüdür (altında yine `interrupt()` + checkpointer).

**Harness profiles:** Model başına yapılandırmayı (`HarnessProfile`) yeniden
kullanılabilir paket yapar. Bir provider/model seçilince otomatik uygulanır →
modeli değiştirince `create_deep_agent` çağrını **değiştirmezsin**. (Provider
soyutlaması felsefesinin — bölüm 2 — harness seviyesindeki hali.)

**`create_agent` vs `create_deep_agent` — hangisi?**

| İhtiyaç | Kullan |
|---------|--------|
| Basit "düşün→tool→cevapla" döngüsü | `create_agent` |
| Dosya sistemi, subagent, skill, plan, sandbox isteyen uzun görev | `create_deep_agent` |
| Tam özel döngü/çok-ajan yönlendirme (Auditor↔Researcher) | ham `StateGraph` |

**Senin projene değer katacak parçalar:** `interrupt_on` (kritik SQL onayı —
Adım 4), `skills` (denetim prosedürleri), `write_todos` (çok adımlı denetim
planı), prompt caching (maliyet). Subagent/sandbox ise muhtemelen şimdilik
**gereğinden fazla** — `StateGraph`'le kuracağın 3-ajan döngüsü senin ölçeğin
için yeterli. Deep Agents'ı "ne zaman lazım olursa o zaman" diye akılda tut.

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

### 6.3 Hazır (built-in) middleware'ler — tam katalog

Sektör standardı: yaygın ihtiyaçlar için **hazır** middleware kullan, yeniden
yazma. Hepsi `langchain.agents.middleware` altında, provider-agnostik:

| Middleware | İşi | Önemli parametre |
|-----------|-----|------------------|
| `SummarizationMiddleware` | token sınırına yaklaşınca geçmişi özetle | `trigger`, `keep` |
| `HumanInTheLoopMiddleware` | kritik tool çağrısında dur, onay/düzenle/reddet | `interrupt_on` (+ **checkpointer şart**) |
| `ModelCallLimitMiddleware` | model çağrısı sayısını sınırla | `thread_limit`, `run_limit`, `exit_behavior` |
| `ToolCallLimitMiddleware` | tool çağrısı sayısını sınırla (global veya tool-bazlı) | `tool_name`, `thread_limit`, `run_limit` |
| `ModelFallbackMiddleware` | birincil model patlarsa yedeğe geç | sıralı model listesi |
| `PIIMiddleware` | kişisel veriyi yakala/maskele | `strategy`, `apply_to_input/output` |
| `TodoListMiddleware` | ajana `write_todos` planlama tool'u ver | `system_prompt` |
| `LLMToolSelectorMiddleware` | ana modelden önce ilgili tool alt kümesini seç | `max_tools`, `always_include` |
| `ToolRetryMiddleware` | başarısız tool çağrısını exponential backoff'la tekrarla | `max_retries`, `backoff_factor` |
| `ModelRetryMiddleware` | başarısız model çağrısını tekrarla | `max_retries`, `on_failure` |
| `LLMToolEmulator` | gerçek tool yerine LLM ile sahte cevap (**test**) | `tools` (hangileri taklit) |
| `ContextEditingMiddleware` | eski tool çıktılarını temizle (context yönetimi) | `ClearToolUsesEdit(trigger, keep)` |
| `ShellToolMiddleware` | kalıcı shell oturumu sun (güvenlik politikası ile) | execution policy |
| `FileSearchMiddleware` | dosya üzerinde Glob/Grep arama tool'ları | — |
| `FilesystemMiddleware` | ajana dosya sistemi (context/uzun-vade hafıza) | — |
| `SubAgentMiddleware` | subagent doğurma yeteneği (`task` tool'u) | — |

```python
from langchain.agents.middleware import HumanInTheLoopMiddleware, SummarizationMiddleware
from langgraph.checkpoint.memory import InMemorySaver

agent = create_agent(
    model="openai:gpt-4o-mini",
    tools=lc_tools,
    checkpointer=InMemorySaver(),              # HITL için ŞART
    middleware=[
        SummarizationMiddleware(model="openai:gpt-4o-mini",
                                trigger=("tokens", 4000), keep=("messages", 20)),
        HumanInTheLoopMiddleware(interrupt_on={
            "sql_query": {"allowed_decisions": ["approve", "edit", "reject"]},
        }),
    ],
)
```

**Senin projene doğrudan değecek olanlar:**
- `HumanInTheLoopMiddleware` → vizyonun "DELETE/UPDATE'te Onayla/Reddet" (Adım 4).
  Dikkat: tool **adıyla** eşleşir (`@tool` fonksiyon adı) ve **checkpointer ister**
  (altında `interrupt()` + persistence — bkz. langgraph_guide bölüm 7).
  `allowed_decisions` ile sadece onay değil **düzenleme/red** de mümkün.
- `ToolCallLimitMiddleware` / `ModelCallLimitMiddleware` → mevcut `agent_max_steps`
  korumanın hazır, daha zengin karşılığı (`exit_behavior`: `continue`/`error`/`end`).
- `PIIMiddleware` → denetim verisinde kişisel veri maskeleme (enterprise/uyumluluk).
- `SummarizationMiddleware` / `ContextEditingMiddleware` → uzun denetim
  konuşmalarında context'i token sınırında tutar.
- `LLMToolEmulator` → **test** standardı: gerçek MCP/DB'ye dokunmadan ajanı dene
  (AGENTS.md "mock LLM, MCP, Qdrant in tests" kuralının doğal aracı).

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

**4 karar tipi (insan ne diyebilir?):**

| Karar | Ne olur | Örnek |
|-------|---------|-------|
| ✅ `approve` | Tool olduğu gibi çalışır | SQL'i onayla |
| ✏️ `edit` | Argümanlar **değiştirilip** çalışır | `DELETE`'i daha dar `WHERE` ile düzelt |
| ❌ `reject` | Tool çalışmaz; gerekçe konuşmaya eklenir | Silmeyi reddet, sebebini yaz |
| 💬 `respond` | Tool atlanır; insanın mesajı **tool sonucu** olur | `ask_user` tarzı tool'a doğrudan cevap |

⚠️ **Önemli ayrım:** `reject` ≠ `respond`. Yan etkili bir tool'u reddetmek için
**`reject`** kullan; `respond` "insan tool'un yerine geçti, cevabı bu" demektir
(model bunu **başarılı** sonuç sanar). Edit yaparken küçük değişiklik yap — büyük
değişiklik modeli yeniden düşünmeye itip tool'u tekrar çağırtabilir.

**Doğru resume API'si (v2):** Karar bir **liste**'dir (her duraklayan eyleme bir
karar, **aynı sırada**):

```python
result = agent.invoke(inputs, config={"configurable": {"thread_id": tid}}, version="v2")
result.interrupts          # incelenecek eylemler (action_requests + review_configs)

agent.invoke(
    Command(resume={"decisions": [{"type": "approve"}]}),   # veya reject/edit/respond
    config={"configurable": {"thread_id": tid}}, version="v2",
)
```

**Koşullu interrupt (`when`) — senin SQL senaryon için TAM isabet:** Her çağrıda
değil, sadece argümanlar bir koşulu sağladığında duraksın. LangChain'in resmi
örneği neredeyse senin `ensure_read_only()` mantığın:

```python
def is_write_query(request: ToolCallRequest) -> bool:
    query = request.tool_call["args"].get("query", "")
    return not query.lstrip().upper().startswith("SELECT")   # SELECT değilse duraklat

HumanInTheLoopMiddleware(interrupt_on={
    "execute_sql": {"allowed_decisions": ["approve", "reject"], "when": is_write_query},
})
```

Yani salt-okunur `SELECT`'ler **akıcı** geçer, yazma denemeleri **insana** düşer.
(Gereksinim: `langchain>=1.3.3`.) Bu, senin "DELETE/UPDATE'te onay" vizyonunu
middleware seviyesinde, tool'u değiştirmeden kurar.

### 6.7 Middleware ayrı bir runtime DEĞİL — `StateGraph`'e gömülür (senin için kritik)

Bu, senin mimarini doğrudan ilgilendiren en önemli içgörü:

> **Middleware'ler, `create_agent`'ın döndürdüğü derlenmiş LangGraph'in
> *içinde* çalışır.** Yani ayrı bir katman/runtime değildir. Sonuç: bir
> `create_agent` (middleware'iyle birlikte) **bütün haliyle** daha büyük bir
> `StateGraph`'e bir **node** (veya subgraph) olarak konabilir — ve tüm
> middleware kancaları orada da çalışmaya devam eder.

Resmi örnek (bir ajanı düğüm olarak gömme):

```python
from langchain.agents import AgentState, create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langgraph.graph import START, StateGraph

email_agent = create_agent(
    model="claude-sonnet-4-6",
    tools=[read_email, send_email],
    middleware=[HumanInTheLoopMiddleware(interrupt_on={"send_email": True})],
)

graph = (
    StateGraph(AgentState)
    .add_node("classify", classify_node)
    .add_node("email_agent", email_agent)        # ← ajan, bir DÜĞÜM
    .add_edge(START, "classify")
    .add_conditional_edges("classify", route)     # önce sınıflandır, sonra yönlendir
    .compile()
)
```

`email_agent` düğümü çalışınca HITL interrupt'ı, summarization, PII, retry —
hepsi **o düğümle birlikte** taşınır.

**Bu senin projen için ne demek?** İki seviyeyi karıştırma derdin biten yer:
- **Üst seviye orkestrasyon** (Researcher → Analyst → Auditor, koşullu döngü) →
  senin elle kurduğun `StateGraph` ([langgraph_guide.md](langgraph_guide.md) bölüm 6).
- **Tek tek ajanlar** → her biri bir `create_agent` (kendi tool'ları +
  middleware'iyle), üst graph'a **node** olarak girer.

Yani "Researcher'a HITL/limit/PII ekleyeyim" demek = Researcher'ı bir
`create_agent` yapıp ilgili middleware'i ona vermek; üst graph'ın döngü mantığı
hiç değişmez. Bu desen "loop until done"dan fazlasını isteyen topolojiler için
(önce sınıflandır-sonra-yönlendir, paralel fan-out, deterministik adımlarla
ajanları birbirine dikme) **tam senin Adım 3 ihtiyacın**.

> Subgraph olarak gömerken checkpointer kapsamı (per-invocation vs per-thread)
> ayrı bir konudur — HITL'de doğru thread'e devam için önemli; LangGraph
> "use subgraphs" dokümanına bak.

### 6.8 Guardrails — güvenlik/uyumluluk kontrolleri

**Guardrail = ajanın akışında stratejik noktalarda içerik doğrulayan/filtreleyen
kontrol.** İki yaklaşım var:

| Tür | Nasıl | Artı / Eksi |
|-----|-------|-------------|
| **Deterministik** | regex, keyword, açık kural | Hızlı, ucuz, öngörülebilir; ince ihlalleri kaçırabilir |
| **Model-tabanlı** | bir LLM/sınıflandırıcı değerlendirir | Anlamsal incelikleri yakalar; yavaş, pahalı |

İkisi de **middleware ile** kurulur — `before_agent` (girişte bir kez) veya
`after_agent` (çıkışta bir kez) kancalarıyla. Kritik mekanizma: bir kancanın
`can_jump_to=["end"]` ile akışı **erken kesmesi** (`jump_to: "end"`):

```python
@before_agent(can_jump_to=["end"])
def content_filter(state, runtime):
    text = state["messages"][0].content.lower()
    if any(k in text for k in BANNED):
        return {"messages": [{"role": "assistant", "content": "Reddedildi."}],
                "jump_to": "end"}      # ajan hiç çalışmadan dur
    return None
```

`after_agent` ise model-tabanlı bir son kontrol için ideal (örn. "bu cevap güvenli
mi?" diye küçük bir modele sor, değilse cevabı değiştir).

**Katmanlı savunma (sektör standardı):** guardrail'leri **sıralı** middleware
listesi olarak diz — sıra = uygulanış sırası:

```python
middleware=[
    ContentFilterMiddleware(...),                 # 1) girişte deterministik filtre
    PIIMiddleware("email", apply_to_input=True),  # 2) model öncesi PII
    HumanInTheLoopMiddleware(interrupt_on={...}),  # 3) kritik tool'da onay
    SafetyGuardrailMiddleware(),                  # 4) çıkışta model-tabanlı kontrol
]
```

**Senin projene bağ:** Sentinel bir denetim sistemi → guardrail'ler doğal yeri.
SQL guard'ın zaten deterministik bir guardrail; üstüne `PIIMiddleware` (denetim
verisinde kişisel veri) + `after_agent` faithfulness/güvenlik kontrolü
eklenebilir. Not: HITL ve PII de birer guardrail'dir — yani bunlar ayrı kavramlar
değil, hepsi guardrail şemsiyesi altında.

### 6.9 Context engineering — "ajan neden güvenilmez?" sorusunun cevabı

Bu, middleware'in **var oluş amacını** çerçeveleyen üst kavram. LangChain'in
tezi: ajanlar çoğunlukla model yetersiz olduğu için değil, **modele doğru bağlam
verilmediği** için başarısız olur. Context engineering = "doğru bilgiyi + tool'u
+ formatta modele vermek." Middleware bunun **mekanizmasıdır**.

**Üç bağlam türü (neyi kontrol edersin):**

| Tür | Ne | Kanca |
|-----|-----|-------|
| **Model context** | model çağrısına ne girer (prompt, mesajlar, tool'lar, format) | `dynamic_prompt`, `wrap_model_call` |
| **Tool context** | tool'lar neye erişir / ne üretir | tool'un state/store erişimi |
| **Life-cycle context** | model↔tool **arasında** ne olur (özet, guardrail, log) | `before/after_*` |

**Üç veri kaynağı (bağlam nereden gelir) — çok önemli ayrım:**

| Kaynak | Diğer adı | Kapsam | Örnek |
|--------|-----------|--------|-------|
| **Runtime Context** | statik config | konuşma boyu | user_id, API key, DB bağlantısı, **yetkiler** |
| **State** | kısa-vade hafıza | konuşma boyu | mesajlar, tool sonuçları, yüklenen dosyalar |
| **Store** | uzun-vade hafıza | **konuşmalar arası** | kullanıcı tercihleri, çıkarılmış içgörüler |

> **State vs Store — karıştırma:** *State* tek konuşmanın çalışma belleği (senin
> `AgentState`, [langgraph_guide.md](langgraph_guide.md) bölüm 3). *Store* ise
> konuşmalar **arası** kalıcı bilgi (kullanıcı tercihi vb.). İkisi farklı ömür.

**Dinamik prompt örneği** — prompt'u state/yetkiye göre uyarlamak (statik string
değil):

```python
@dynamic_prompt
def context_aware_prompt(request: ModelRequest) -> str:
    base = "You are a careful data analyst."
    if request.runtime.context.user_role == "viewer":
        base += "\nYou have read-only access. Guide users to read operations only."
    return base
```

**Senin projene bağ:** Bu, RBAC vizyonunla (VIZYON 2'deki metadata/RBAC) doğrudan
örtüşür: kullanıcının rolü **Runtime Context**'ten gelir, `dynamic_prompt` ona
göre ajanı "salt-okunur" moda sokar. Denetim geçmişi/tercihler **Store**'a,
o anki konuşma **State**'e (senin `AgentState`) gider. Bu üçlüyü ayrı tutmak,
güvenilir ajanın temelidir.

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
