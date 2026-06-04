# OpenTelemetry + OpenInference + Phoenix ile LLM Tracing Dokümanı

## 1. Amaç

Bu dokümanın amacı, AI/LLM tabanlı uygulamalarda tracing mantığını, OpenTelemetry ve OpenInference’ın rollerini, Phoenix üzerinde trace görüntüleme akışını ve production-ready observability best practice’lerini açıklamaktır.

Bu yapı özellikle şu tip sistemlerde kullanılır:

* RAG pipeline’ları
* LangChain / LangGraph / LlamaIndex uygulamaları
* Agentic AI sistemleri
* Tool-calling kullanan LLM servisleri
* Prompt orchestration akışları
* Eval ve debugging odaklı LLM uygulamaları
* Çok adımlı backend + LLM pipeline’ları

Temel hedef şudur:

> Bir kullanıcı isteği geldiğinde sistemin hangi adımlardan geçtiğini, hangi LLM çağrılarının yapıldığını, hangi retrieval sonuçlarının kullanıldığını, hangi tool’ların çağrıldığını, ne kadar süre harcandığını, kaç token tüketildiğini ve nerede hata oluştuğunu uçtan uca izleyebilmek.

---

# 2. Temel Kavramlar

## 2.1 Trace Nedir?

Trace, tek bir request’in veya çalıştırmanın sistem içinde izlediği yolu gösteren üst seviye gözlemlenebilirlik kaydıdır.

Örneğin bir RAG uygulamasında kullanıcı şu soruyu sorsun:

> “Şirket izin politikası nedir?”

Bu tek kullanıcı isteği bir trace olabilir.

Bu trace’in içinde şu adımlar bulunabilir:

1. API request alınır.
2. Kullanıcı kimliği doğrulanır.
3. Query normalize edilir.
4. Embedding oluşturulur.
5. Vector DB’den dokümanlar retrieve edilir.
6. Prompt hazırlanır.
7. LLM çağrılır.
8. Cevap parse edilir.
9. Response kullanıcıya döndürülür.

Bu adımların her biri trace içindeki birer span olabilir.

---

## 2.2 Span Nedir?

Span, trace içindeki tek bir operasyonu temsil eder.

Bir span genellikle şunları içerir:

* Span adı
* Başlangıç zamanı
* Bitiş zamanı
* Süre
* Parent span
* Attribute’lar
* Status
* Event’ler
* Hata bilgisi
* Input / output verisi
* Token kullanımı
* Model bilgisi
* Metadata

Örnek span’ler:

* `POST /chat`
* `retrieve_documents`
* `generate_embedding`
* `llm.chat.completion`
* `call_weather_tool`
* `rerank_documents`
* `agent.plan`
* `parse_structured_output`

---

## 2.3 Parent-Child Span İlişkisi

Trace’lerde span’ler ağaç yapısı oluşturur.

Örnek:

```text
Trace: chat_request
└── Span: POST /api/chat
    ├── Span: authenticate_user
    ├── Span: normalize_query
    ├── Span: retrieve_context
    │   ├── Span: create_embedding
    │   └── Span: vector_db_search
    ├── Span: build_prompt
    ├── Span: llm_call
    └── Span: parse_response
```

Bu yapı sayesinde şu sorular cevaplanabilir:

* Request toplam kaç ms sürdü?
* En yavaş adım hangisi?
* LLM mi yavaş, retriever mı yavaş?
* Hata hangi aşamada oluştu?
* LLM cevabı hangi context ile üretildi?
* Tool call gerçekten çağrıldı mı?
* Agent yanlış branch’e mi gitti?

---

# 3. OpenTelemetry Nedir?

OpenTelemetry, sistemlerden telemetry datası toplamak için kullanılan açık standarttır.

Telemetry data temel olarak üç ana sinyalden oluşur:

1. Traces
2. Metrics
3. Logs

Bu dokümanda odak noktamız traces’tir.

OpenTelemetry şunları sağlar:

* Standart trace modeli
* Standart span yapısı
* Context propagation
* SDK’lar
* Auto-instrumentation
* Exporter’lar
* Collector mimarisi
* Vendor bağımsız telemetry formatı

Yani OpenTelemetry sayesinde trace datanızı tek bir vendor’a kilitlemeden toplayabilirsiniz.

### Context Propagation

Birden fazla servis varsa trace ID’nin servisler arasında taşınması gerekir. OpenTelemetry bunu W3C `traceparent` HTTP header’ı ile yapar.

```text
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
                 ↑ trace_id                          ↑ parent_span_id
```

Gelen bir request bu header’ı taşıyorsa yeni oluşturulan span otomatik olarak o trace’e bağlanır. Bu sayede:

```text
Frontend → API Gateway → RAG Service → LLM Proxy
```

gibi bir zincirde hepsi tek bir trace altında görünür. FastAPIInstrumentor bu header’ı otomatik okur ve yayar.

Örneğin aynı trace datası teorik olarak şu sistemlere gönderilebilir:

* Phoenix
* Jaeger
* Grafana Tempo
* Datadog
* New Relic
* Honeycomb
* OpenTelemetry Collector
* Arize AX

---

# 4. OpenInference Nedir?

OpenTelemetry genel amaçlıdır. HTTP request, DB query, cache operation gibi klasik backend işlemlerini izlemek için çok güçlüdür. Ancak LLM sistemlerinde sadece genel trace modeli yeterli değildir.

Çünkü LLM uygulamalarında şu özel bilgilere ihtiyaç duyulur:

* Prompt
* Completion
* System message
* User message
* Assistant message
* Tool call
* Tool result
* Model adı
* Provider
* Token sayıları
* Prompt template
* Prompt variables
* Retriever query
* Retrieved documents
* Embedding text
* Reranker input/output
* Agent step
* Chain step
* Eval score
* Guardrail sonucu

OpenInference, bu AI-specific bilgileri OpenTelemetry span attribute’ları olarak standartlaştıran semantic convention katmanıdır.

Basitçe:

```text
OpenTelemetry = Trace taşıma ve genel observability standardı
OpenInference = AI/LLM span’lerinin nasıl anlamlandırılacağını belirleyen convention
Phoenix = Bu trace’leri görselleştiren ve analiz eden observability platformu
```

---

# 5. Phoenix Nedir?

Phoenix, LLM observability ve evaluation için kullanılan açık kaynak bir platformdur.

Phoenix ile şunlar yapılabilir:

* LLM trace görüntüleme
* Span bazlı debugging
* Prompt/input/output inceleme
* Retrieval sonuçlarını analiz etme
* Tool call akışını görme
* Agent adımlarını takip etme
* Token kullanımını inceleme
* Latency breakdown görme
* Eval sonuçlarını trace/span üzerine bağlama
* Human feedback veya annotation toplama
* Dataset ve experiment yönetimi

Phoenix özellikle AI sistemlerinde klasik APM tool’larının eksik kaldığı noktaları kapatır.

---

# 6. OpenTelemetry, OpenInference ve Phoenix Birlikte Nasıl Çalışır?

Genel akış:

```text
Application Code
    ↓
OpenTelemetry SDK / Instrumentation
    ↓
OpenInference Semantic Attributes
    ↓
OTLP Exporter
    ↓
Phoenix Collector / Endpoint
    ↓
Phoenix UI
```

Daha açık hali:

1. Uygulamada bir request başlar.
2. OpenTelemetry root span oluşturur.
3. LLM, retriever, tool, chain gibi adımlar için child span’ler oluşturulur.
4. OpenInference bu span’lere AI-specific attribute’lar ekler.
5. Span’ler OTLP formatında Phoenix’e gönderilir.
6. Phoenix trace ağacını görselleştirir.
7. Developer trace üzerinden debugging, latency analizi ve kalite değerlendirmesi yapar.

---

# 7. Span Tipleri ve OpenInference Span Kind Mantığı

OpenInference tarafında span’lerin AI workflow içindeki rolünü belirtmek için span kind kullanılır.

En yaygın span türleri:

| Span Kind   | Ne İçin Kullanılır?                           | Örnek                                          |
| ----------- | --------------------------------------------- | ---------------------------------------------- |
| `CHAIN`     | Birden fazla adımı yöneten zincir/pipeline    | RAG pipeline, summarize chain                  |
| `AGENT`     | Karar veren, plan yapan veya tool seçen agent | LangGraph supervisor, planner agent            |
| `LLM`       | Model çağrısı                                 | OpenAI chat completion, Anthropic message call |
| `TOOL`      | Agent veya LLM tarafından çağrılan araç       | search tool, calculator, SQL tool              |
| `RETRIEVER` | Doküman/context getirme adımı                 | vector search, hybrid search                   |
| `EMBEDDING` | Embedding üretimi                             | text embedding call                            |
| `RERANKER`  | Retrieved dokümanları yeniden sıralama        | cross-encoder rerank                           |
| `EVALUATOR` | Cevap veya trace değerlendirmesi              | LLM-as-judge, relevance score                  |
| `GUARDRAIL` | Güvenlik/policy kontrolü                      | PII check, toxicity check                      |
| `PROMPT`    | Prompt oluşturma veya template render adımı   | Prompt builder, template engine                |
| `UNKNOWN`   | Kind set edilmemiş span (default)             | —                                              |

Not: Projede kullanılan instrumentation paketine göre desteklenen span kind isimleri değişebilir. Ancak mantık aynıdır: her span, AI workflow’daki semantik görevine göre etiketlenmelidir.

---

# 8. Span Türleri Detaylı Açıklama

## 8.1 CHAIN Span

CHAIN span, birden fazla alt adımı kapsayan pipeline veya workflow seviyesindeki span’dir.

Örnek kullanım:

```text
rag_answer_chain
├── embed_query
├── retrieve_documents
├── build_prompt
└── call_llm
```

Ne zaman kullanılır?

* RAG pipeline
* Summarization pipeline
* Multi-step prompt workflow
* Data extraction chain
* Classification chain
* LangChain chain
* LCEL chain

Best practice:

* Chain span’i çok genel ama anlamlı isimlendirilmelidir.
* `rag_pipeline` yerine `answer_question_with_policy_rag` gibi daha açıklayıcı isimler tercih edilebilir.
* Chain input/output saklanmalı ama sensitive data maskelenmelidir.
* Chain span’i child span’leri kapsamalıdır.

---

## 8.2 AGENT Span

AGENT span, karar veren veya tool seçen agent davranışını temsil eder.

Örnek:

```text
customer_support_agent
├── classify_intent
├── retrieve_policy_docs
├── call_refund_tool
└── generate_final_answer
```

Ne zaman kullanılır?

* LangGraph agent node’ları
* Tool-using agent
* Planner/executor mimarisi
* Multi-agent supervisor
* Router agent
* AI coach agent
* ReAct style loop

Best practice:

* Agent span içinde agent’ın hangi kararları verdiği metadata ile takip edilmelidir.
* Tool seçimi ayrı TOOL span olarak açılmalıdır.
* Agent reasoning’i doğrudan saklamak her zaman güvenli olmayabilir; bunun yerine karar sonucu, selected_tool, route_name gibi kontrollü attribute’lar saklanmalıdır.
* Loop’lu agent sistemlerinde her iteration ayrı child span veya event olarak tutulmalıdır.

---

## 8.3 LLM Span

LLM span, doğrudan model çağrısını temsil eder.

Örnek attribute’lar:

```text
openinference.span.kind = LLM
llm.model_name = gpt-4.1-mini
llm.provider = openai
llm.input_messages = [...]
llm.output_messages = [...]
llm.token_count.prompt = 1200
llm.token_count.completion = 300
llm.token_count.total = 1500
llm.invocation_parameters = {"temperature": 0.2, "max_tokens": 800}
```

Ne zaman kullanılır?

* Chat completion
* Text completion
* Structured output generation
* Function/tool calling response
* Classification via LLM
* Summarization via LLM

Best practice:

* Model adı mutlaka kaydedilmelidir.
* Temperature, max_tokens, top_p gibi invocation parameter’lar saklanmalıdır.
* Token kullanımı kaydedilmelidir.
* Prompt template ve variable’lar ayrı tutulmalıdır.
* Raw prompt saklanacaksa privacy stratejisi uygulanmalıdır.
* Hata durumunda provider error code kaydedilmelidir.

---

## 8.4 TOOL Span

TOOL span, LLM veya agent tarafından çağrılan araçları temsil eder.

Örnek tool’lar:

* Web search
* SQL query
* Calculator
* Weather API
* CRM lookup
* Internal HR API
* File search
* Vector DB query
* Calendar API

Örnek yapı:

```text
agent
└── tool:get_employee_profile
    ├── input: {"employee_id": "123"}
    └── output: {"department": "Engineering"}
```

Best practice:

* Tool adı net olmalıdır: `tool:get_weather`, `tool:query_postgres`, `tool:search_policy_docs`.
* Tool input/output schema’sı mümkünse structured tutulmalıdır.
* Secret, token, password, API key asla span attribute olarak yazılmamalıdır.
* External API latency ayrı takip edilmelidir.
* Tool failure durumunda status error yapılmalıdır.

---

## 8.5 RETRIEVER Span

RETRIEVER span, RAG sistemlerinde context getirme işlemini temsil eder.

Örnek:

```text
retrieve_policy_documents
├── query: "annual leave policy"
├── top_k: 5
├── retrieved_documents: [...]
└── scores: [...]
```

Ne zaman kullanılır?

* Vector search
* Hybrid search
* BM25 retrieval
* Metadata-filtered retrieval
* Knowledge base lookup
* File/document search

Best practice:

* Query kaydedilmelidir.
* top_k, filters, namespace, index adı gibi bilgiler kaydedilmelidir.
* Retrieved document id, score, title, source gibi bilgiler saklanmalıdır.
* Çok büyük document content’leri span’e komple yazılmamalıdır.
* Chunk id ve source metadata saklamak genelde daha sağlıklıdır.
* Retrieval kalitesi için relevance eval’ları trace ile ilişkilendirilebilir.

---

## 8.6 EMBEDDING Span

EMBEDDING span, text veya multimodal input için embedding oluşturma işlemini temsil eder.

Örnek:

```text
generate_query_embedding
├── model: text-embedding-3-small
├── input: "leave policy"
└── vector_dimension: 1536
```

Best practice:

* Embedding model adı kaydedilmelidir.
* Input text hassassa maskelenmelidir.
* Embedding vector’lerini span’e yazmak genelde önerilmez; payload şişer ve privacy riski artar.
* Batch size ve input count takip edilmelidir.
* Embedding latency RAG performansı için ayrıca izlenmelidir.

---

## 8.7 RERANKER Span

RERANKER span, retrieve edilen dokümanların yeniden sıralandığı adımı temsil eder.

Örnek:

```text
rerank_documents
├── model: bge-reranker-large
├── input_document_count: 20
├── output_document_count: 5
└── scores: [...]
```

Best practice:

* Reranker öncesi ve sonrası document id listesi saklanabilir.
* Skorlar saklanabilir ama uzun content saklanmamalıdır.
* Reranker latency ayrıca izlenmelidir.
* Retrieval ve reranking score’ları ayrı tutulmalıdır.

---

## 8.8 EVALUATOR Span

EVALUATOR span, sistem çıktılarının değerlendirilmesini temsil eder.

Örnek evaluator’lar:

* Relevance
* Groundedness
* Hallucination
* Answer correctness
* Style adherence
* Safety
* Toxicity
* Tool-use correctness
* JSON schema validity
* LLM-as-judge score

Best practice:

* Eval input, output, score ve explanation ayrı attribute’lar olarak tutulmalıdır.
* Eval prompt versiyonu kaydedilmelidir.
* LLM-as-judge kullanılıyorsa judge model adı kaydedilmelidir.
* Eval span’leri production request’in parçasıysa latency maliyeti dikkate alınmalıdır.
* Offline eval ile online trace eval ayrımı yapılmalıdır.

---

## 8.9 PROMPT Span

PROMPT span, prompt şablonlarının render edildiği veya dinamik olarak oluşturulduğu adımları temsil eder.

Örnek kullanım:

```text
build_rag_prompt
├── template: "rag-answer-v3"
├── variables: {context: [...], question: "..."}
└── rendered_prompt: "..."
```

Ne zaman kullanılır?

* Prompt template engine adımları
* Jinja / Mustache render
* Few-shot example selection
* Dynamic instruction builder
* System prompt assembly

Best practice:

* Template versiyonu kaydedilmelidir: `llm.prompt_template.version`.
* Template variable'ları saklanabilir ama değerler hassas içeriyorsa maskelenmelidir.
* Render edilmiş tam prompt genelde loglanmamalıdır; sadece template referansı ve variable isimleri yeterlidir.
* Prompt boyutu izlenmelidir — şişen prompt doğrudan token maliyetini artırır.

---

## 8.10 GUARDRAIL Span

GUARDRAIL span, güvenlik veya policy kontrolü yapan adımları temsil eder.

Örnek:

* PII detection
* Toxicity detection
* Jailbreak detection
* Prompt injection detection
* Sensitive topic classifier
* Output policy check
* Data access control check

Best practice:

* Guardrail sonucu açık saklanmalıdır: `passed`, `blocked`, `modified`, `flagged`.
* Hassas içeriğin kendisi değil, sınıflandırma sonucu saklanmalıdır.
* Block reason veya policy id tutulmalıdır.
* Guardrail’ler hem input hem output tarafında izlenebilir.

---

# 9. Attribute Mantığı

Span attribute’ları trace debugging’in en önemli kısmıdır.

Attribute’lar şu soruları cevaplamalıdır:

* Bu span ne yaptı?
* Hangi model/tool/index kullanıldı?
* Hangi input ile çalıştı?
* Ne output verdi?
* Kaç ms sürdü?
* Kaç token kullandı?
* Hangi kullanıcı/session/request ile ilişkili?
* Hangi prompt versiyonu kullanıldı?
* Hangi environment’ta çalıştı?
* Hata olduysa neden oldu?

Örnek attribute kategorileri:

## 9.1 Kimlik ve Context Attribute’ları

```text
service.name = ai-backend
deployment.environment = production
session.id = abc-123
user.id = user-789
request.id = req-456
conversation.id = conv-111
```

## 9.2 LLM Attribute’ları

```text
llm.model_name = gpt-4.1-mini
llm.provider = openai
llm.invocation_parameters = {"temperature": 0.2}
llm.token_count.prompt = 1000
llm.token_count.completion = 250
llm.token_count.total = 1250
```

## 9.3 Prompt Attribute’ları

```text
llm.prompt_template.template = "Answer the question using the context: {context}"
llm.prompt_template.version = "rag-answer-v3"
llm.prompt_template.variables = {"language": "tr", "tone": "formal"}
```

## 9.4 Retrieval Attribute’ları

```text
retrieval.query = "annual leave policy"
retrieval.top_k = 5
retrieval.index_name = "company-policy-index"
retrieval.filters = {"department": "engineering"}
```

## 9.5 Metadata Attribute’ları

```text
metadata = {
  "feature": "hr-policy-chat",
  "experiment": "reranker-v2",
  "tenant_id": "company-a",
  "app_version": "1.4.2"
}
```

---

# 10. Span Naming Best Practice

Span isimleri kısa ama anlamlı olmalıdır.

Kötü örnekler:

```text
call
process
run
execute
llm
chain
step1
```

İyi örnekler:

```text
POST /api/chat
rag.answer_question
retriever.search_policy_docs
embedding.create_query_embedding
llm.generate_final_answer
tool.query_employee_profile
agent.route_to_specialist
guardrail.check_prompt_injection
eval.score_groundedness
```

Önerilen pattern:

```text
<component>.<operation>
```

Örnek:

```text
retriever.search
llm.generate
agent.route
tool.execute
guardrail.check
eval.score
```

Daha domain-specific örnek:

```text
policy_rag.retrieve_documents
policy_rag.generate_answer
ai_coach.route_agent
ai_coach.evaluate_response_quality
```

---

# 11. Trace Tasarımı Nasıl Olmalı?

İyi bir trace şunları göstermelidir:

1. Request nereden başladı?
2. Hangi ana pipeline çalıştı?
3. Hangi LLM çağrıları yapıldı?
4. Hangi prompt template kullanıldı?
5. Hangi retrieval sonuçları kullanıldı?
6. Hangi tool’lar çağrıldı?
7. Hangi adım ne kadar sürdü?
8. Hangi adım hata verdi?
9. Token/cost nerede oluştu?
10. Final output neydi?

Örnek iyi trace yapısı:

```text
Trace: POST /api/chat
└── chain:policy_rag.answer_question
    ├── guardrail:check_input_safety
    ├── chain:prepare_query
    │   └── llm:rewrite_user_query
    ├── retriever:search_policy_docs
    │   ├── embedding:create_query_embedding
    │   └── vector_db:search
    ├── reranker:rerank_policy_docs
    ├── llm:generate_grounded_answer
    ├── guardrail:check_output_safety
    └── eval:score_groundedness
```

---

# 12. Auto-Instrumentation vs Manual Instrumentation

## 12.1 Auto-Instrumentation

Auto-instrumentation, framework/provider çağrılarını otomatik trace eder.

Örneğin:

* OpenAI çağrılarını otomatik yakalama
* LangChain chain’lerini otomatik trace etme
* LlamaIndex retriever çağrılarını otomatik izleme
* Anthropic veya Bedrock çağrılarını otomatik span’e dönüştürme

Avantajları:

* Hızlı kurulum
* Daha az boilerplate
* Standart attribute’lar
* Framework entegrasyonu kolay

Dezavantajları:

* Domain-specific business step’leri kaçırabilir
* Span isimleri her zaman ideal olmayabilir
* Gereksiz fazla span üretilebilir
* Sensitive data kontrolü ayrıca yapılmalıdır

## 12.2 Manual Instrumentation

Manual instrumentation, kodda kendiniz span açmanızdır.

Örnek:

```python
with tracer.start_as_current_span("policy_rag.retrieve_documents") as span:
    span.set_attribute("retrieval.top_k", 5)
    docs = retriever.get_relevant_documents(query)
    span.set_attribute("retrieval.document_count", len(docs))
```

Avantajları:

* Domain mantığını daha iyi yansıtır
* Kritik business adımları görünür olur
* Daha temiz trace ağacı oluşturulabilir
* Metadata kontrolü daha güçlüdür

Dezavantajları:

* Daha fazla kod
* Standardizasyon disiplini gerekir
* Yanlış parent-child ilişkisi kurulabilir
* Her ekip farklı isimlendirme yaparsa trace okunabilirliği düşer

## 12.3 En İyi Yaklaşım

Genelde en iyi yaklaşım hibrittir:

```text
Auto-instrumentation = LLM/provider/framework çağrılarını otomatik yakala
Manual instrumentation = Business-critical pipeline adımlarını elle span’le
```

Örnek:

```text
Manual span: rag.answer_question
  Auto span: OpenAI embedding call
  Manual span: vector_db.search
  Auto span: OpenAI chat completion
```

---

# 13. Phoenix Üzerinde Ne İzlenmeli?

Phoenix UI’da özellikle şu noktalar incelenmelidir:

## 13.1 Latency Breakdown

Şunlara bakılır:

* Toplam trace süresi
* En yavaş span
* LLM latency
* Retriever latency
* Tool latency
* Reranker latency
* Guardrail latency

Amaç:

* Bottleneck bulmak
* Gereksiz LLM çağrılarını tespit etmek
* Slow tool/API dependency görmek
* RAG pipeline performansını optimize etmek

---

## 13.2 Token Usage

Takip edilmesi gerekenler:

* Prompt tokens
* Completion tokens
* Total tokens
* Cached tokens
* Reasoning tokens
* Token usage per model
* Token usage per feature
* Token usage per tenant/user/session

Amaç:

* Maliyet kontrolü
* Prompt şişmesini tespit etmek
* Gereksiz context kullanımını azaltmak
* Model seçimini optimize etmek

---

## 13.3 Retrieval Quality

RAG sistemlerinde Phoenix üzerinde şu bilgiler incelenmelidir:

* Query
* Retrieved documents
* Document scores
* Source metadata
* Chunk ids
* Top-k sonuçlar
* Kullanılan context
* Final answer ilişkisi

Amaç:

* Yanlış doküman mı çekiliyor?
* Doğru doküman var ama LLM kullanmıyor mu?
* Chunking stratejisi zayıf mı?
* Metadata filter yanlış mı?
* Reranker gerçekten iyileştiriyor mu?

---

## 13.4 Tool Calling

Agentic sistemlerde şu sorular incelenir:

* Agent doğru tool’u seçti mi?
* Tool input doğru mu?
* Tool output beklenen formatta mı?
* Tool hata verdi mi?
* Tool sonucu LLM tarafından doğru kullanıldı mı?
* Gereksiz tool call var mı?

---

## 13.5 Prompt Debugging

İzlenmesi gerekenler:

* Hangi prompt template kullanıldı?
* Prompt version neydi?
* Prompt variables doğru mu?
* System message doğru set edilmiş mi?
* Context prompt’a doğru yerleşmiş mi?
* Output format instruction yeterli mi?
* Structured output schema ile uyumlu mu?

---

# 14. Production Best Practice’ler

## 14.1 Her Request İçin Root Span Olmalı

Uygulamada her kullanıcı isteği için root span oluşturulmalıdır.

Örnek:

```text
POST /api/chat
POST /api/evaluate
POST /api/generate-report
```

Root span altında tüm LLM, retriever, tool ve chain span’leri görünmelidir.

---

## 14.2 Session ve User ID Eklenmeli

Debugging için session ve user context çok önemlidir.

Örnek:

```text
session.id = conversation-123
user.id = user-456
```

Ancak privacy için gerçek email, telefon, isim gibi PII bilgileri doğrudan span’e yazılmamalıdır.

İyi örnek:

```text
user.id = hashed_user_456
```

Kötü örnek:

```text
user.email = melis@example.com
```

---

## 14.3 Prompt Version Mutlaka Takip Edilmeli

LLM davranışını anlamak için sadece output’a bakmak yetmez. Hangi prompt versiyonunun çalıştığını bilmek gerekir.

Önerilen attribute’lar:

```text
llm.prompt_template.version = "answer-v3"
llm.prompt_template.template = "..."
llm.prompt_template.variables = {...}
```

Bu sayede şu sorular cevaplanabilir:

* Yeni prompt versiyonu kaliteyi artırdı mı?
* Hangi versiyonda hallucination arttı?
* Hangi prompt daha fazla token tüketiyor?
* Regression hangi prompt değişikliğinden sonra başladı?

---

## 14.4 Sensitive Data Masking Kullanılmalı

LLM trace’leri çok hassas olabilir. Şunlar trace’e yazılmadan önce düşünülmelidir:

* Kullanıcı mesajları
* Sistem prompt’ları
* Internal policy dokümanları
* Müşteri verileri
* Sağlık verileri
* Finansal bilgiler
* API key / token / secret
* Embedding input text
* Tool output’ları

Best practice:

* Production ortamında masking policy tanımla.
* Input/output logging seviyesini environment’a göre değiştir.
* Development’ta detaylı trace, production’da kontrollü trace kullan.
* PII redaction uygula.
* Embedding vector’lerini saklama.
* Gereksiz büyük payload’ları trace’e yazma.

---

## 14.5 Attribute Boyutlarını Kontrol Et

Span attribute’larına çok büyük text, JSON veya base64 image koymak sorun yaratır.

Riskler:

* Phoenix UI yavaşlar
* OTLP payload büyür
* Network maliyeti artar
* Collector performansı düşer
* Sensitive data riski artar
* Trace okunabilirliği azalır

Öneri:

* Büyük doküman içeriği yerine `document_id`, `chunk_id`, `source`, `score` sakla.
* Tam content gerekiyorsa sadece ilk N karakteri sakla.
* Base64 image saklanacaksa sampling/masking uygula.
* Büyük tool output’larında summary veya id sakla.

---

## 14.6 Error Status Doğru Set Edilmeli

Hata alan span’ler error status ile işaretlenmelidir.

Örnek:

```python
span.set_status(Status(StatusCode.ERROR, "Vector DB timeout"))
span.record_exception(error)
```

İzlenmesi gereken hata tipleri:

* LLM provider timeout
* Rate limit
* Invalid JSON output
* Tool execution error
* Retriever empty result
* Guardrail block
* Schema validation failure
* Authentication/authorization failure

---

## 14.7 Sampling Stratejisi Kurulmalı

Production’da her trace’i tam detaylı saklamak maliyetli olabilir.

Örnek strateji:

* Development: %100 trace
* Staging: %100 trace
* Production normal request: %5-20 sample
* Production error request: %100 trace
* High-value user/session: %100 trace
* Evaluation run: %100 trace

Önemli nokta:

> Hata alan trace’ler mümkün olduğunca kaybolmamalıdır.

---

## 14.8 Trace’ler Eval Sonuçlarıyla Birleştirilmeli

Sadece “ne oldu?” sorusu yetmez. “Kaliteli miydi?” sorusu da cevaplanmalıdır.

Bu yüzden trace üzerine eval score bağlamak önemlidir.

Örnek eval metrikleri:

* Relevance
* Groundedness
* Correctness
* Helpfulness
* Safety
* Tool correctness
* JSON validity
* Citation quality
* Retrieval precision
* Hallucination risk

Örnek:

```text
trace_id = abc123
eval.groundedness.score = 0.82
eval.answer_relevance.score = 0.91
eval.hallucination.label = "low"
```

---

## 14.9 Environment ve Deployment Bilgisi Eklenmeli

Aynı sistemin farklı ortamları karışmamalıdır.

Örnek attribute’lar:

```text
deployment.environment = production
service.name = ai-backend
service.version = 1.8.0
git.commit.sha = abc123
feature.flag = reranker_enabled
```

Bu sayede deploy sonrası regression tespit edilebilir.

---

## 14.10 Trace Schema Standardı Oluşturulmalı

Ekip içinde herkes farklı span adı ve attribute kullanırsa Phoenix ekranı karmaşıklaşır.

Bu yüzden küçük bir internal convention dosyası tutulmalıdır.

Örnek:

```text
Root span naming:
- POST /api/<route>

Chain span naming:
- <domain>.<workflow>

LLM span naming:
- llm.<purpose>

Retriever span naming:
- retriever.<source>

Tool span naming:
- tool.<tool_name>

Required attributes:
- session.id
- user.id
- service.name
- deployment.environment
- llm.model_name
- llm.token_count.total
- llm.prompt_template.version
```

---

# 15. RAG Pipeline İçin Örnek Trace Tasarımı

Örnek sistem:

> Kullanıcı şirket dokümanlarına soru soruyor. Sistem query embedding oluşturuyor, vector DB’den doküman çekiyor, reranker uyguluyor ve LLM ile cevap üretiyor.

Önerilen trace:

```text
Trace: POST /api/chat
└── chain:company_docs_rag.answer_question
    ├── guardrail:check_input
    ├── chain:query_preprocessing
    │   └── llm:rewrite_query
    ├── retriever:search_company_docs
    │   ├── embedding:create_query_embedding
    │   └── vector_db:qdrant_search
    ├── reranker:rerank_retrieved_docs
    ├── chain:build_answer_prompt
    ├── llm:generate_answer
    ├── guardrail:check_output
    └── eval:score_answer_groundedness
```

Her span için önerilen attribute’lar:

## Root Span

```text
http.route = /api/chat
session.id = ...
user.id = ...
metadata.feature = company_docs_chat
metadata.tenant_id = ...
```

## Retriever Span

```text
retrieval.query = ...
retrieval.top_k = 10
retrieval.index_name = company_docs
retrieval.filters = ...
retrieval.document_count = 10
```

## Document Metadata

```text
document.id = doc_123
document.chunk_id = chunk_456
document.source = employee_handbook.pdf
document.score = 0.87
```

## LLM Span

```text
llm.model_name = ...
llm.provider = ...
llm.invocation_parameters = ...
llm.token_count.prompt = ...
llm.token_count.completion = ...
llm.token_count.total = ...
llm.prompt_template.version = answer-v3
```

---

# 16. Agentic Workflow İçin Örnek Trace Tasarımı

Örnek sistem:

> AI coach agent, kullanıcının mesajına göre doğru coaching agent’ını seçiyor, gerektiğinde tool çağırıyor ve cevap üretiyor.

Önerilen trace:

```text
Trace: POST /api/coach
└── agent:ai_coach.supervisor
    ├── guardrail:check_user_message
    ├── llm:classify_user_intent
    ├── agent:route_to_specialist
    ├── agent:career_coach
    │   ├── tool:get_user_profile
    │   ├── tool:get_previous_goals
    │   └── llm:generate_coaching_response
    ├── guardrail:check_response_safety
    └── eval:score_coaching_quality
```

Önerilen agent metadata:

```text
metadata.selected_agent = career_coach
metadata.coaching_mode = reflective
metadata.relationship_stage = early
metadata.user_goal_category = career_growth
metadata.route_confidence = 0.86
```

---

# 17. Phoenix’te Debugging Senaryoları

## Senaryo 1: Cevap yanlış geldi

Bakılacak yerler:

1. Retriever doğru dokümanları getirdi mi?
2. Retrieved document score’ları düşük mü?
3. Reranker doğru sıraladı mı?
4. Prompt içine context doğru girmiş mi?
5. LLM context’i kullanmış mı?
6. Prompt version değişmiş mi?
7. Model değişmiş mi?
8. Temperature yüksek mi?
9. Eval groundedness düşük mü?

---

## Senaryo 2: Sistem yavaşladı

Bakılacak yerler:

1. Total trace duration
2. En uzun span
3. LLM latency
4. Vector DB latency
5. Tool API latency
6. Reranker latency
7. Guardrail latency
8. Sequential çalışması gerekmeyen adımlar paralel mi?
9. Gereksiz LLM call var mı?

---

## Senaryo 3: Maliyet arttı

Bakılacak yerler:

1. Token count per trace
2. Prompt token artışı
3. Retrieved context çok mu büyük?
4. Prompt template şişti mi?
5. Gereksiz conversation history gönderiliyor mu?
6. Daha pahalı model route ediliyor mu?
7. Tool/agent loop çok fazla dönüyor mu?
8. Completion max_tokens gereksiz yüksek mi?

---

## Senaryo 4: Agent yanlış tool seçiyor

Bakılacak yerler:

1. Agent decision span
2. Tool definitions prompt’a doğru verilmiş mi?
3. User intent doğru classify edilmiş mi?
4. Tool input schema doğru mu?
5. LLM output tool call formatı doğru mu?
6. Tool result agent’a doğru dönmüş mü?
7. Agent final answer tool sonucunu kullanmış mı?

---

# 18. Sık Yapılan Hatalar

## 18.1 Her Şeyi Tek Span’e Yazmak

Kötü:

```text
Span: process_request
```

İçinde her şey var ama alt adımlar yok.

Sorun:

* Hangi adım yavaş bilinmez.
* Hangi adım hata verdi bilinmez.
* RAG mi LLM mi problemli anlaşılmaz.

Doğru:

```text
process_request
├── retrieve_documents
├── call_llm
└── parse_response
```

---

## 18.2 Çok Fazla Gereksiz Span Açmak

Her küçük helper function için span açmak trace’i okunmaz hale getirir.

Kötü:

```text
format_string
clean_whitespace
dict_to_json
append_message
```

Doğru:

```text
build_prompt
```

Span açma kriteri:

> Bu adım debugging, latency, cost veya quality açısından anlamlı mı?

Cevap evetse span aç. Hayırsa açma.

---

## 18.3 Sensitive Data’yı Kontrolsüz Loglamak

Kötü:

```text
input.value = full user medical record
tool.output = raw customer financial data
```

Doğru:

```text
metadata.record_type = medical
metadata.redacted = true
input.value = [REDACTED]
```

---

## 18.4 Prompt Version Tutmamak

Prompt değişiklikleri trace’e yansımazsa kalite değişimlerinin sebebi bulunamaz.

Mutlaka tutulmalı:

```text
llm.prompt_template.version
```

---

## 18.5 Tool Call’ları LLM Span İçinde Kaybetmek

Tool call’ları ayrı TOOL span olarak görünmezse agent debugging zorlaşır.

Doğru yapı:

```text
agent
├── llm:decide_tool
├── tool:search_database
└── llm:final_answer
```

---

# 19. Minimum Production Checklist

Aşağıdaki checklist production seviyesinde temel kabul edilebilir tracing standardı için kullanılabilir.

## Genel

* [ ] Her request için root trace var.
* [ ] Parent-child span ilişkisi doğru.
* [ ] Service name set edilmiş.
* [ ] Environment bilgisi set edilmiş.
* [ ] Session id set edilmiş.
* [ ] User id güvenli şekilde set edilmiş.
* [ ] Error status doğru set ediliyor.
* [ ] Exception’lar span’e kaydediliyor.
* [ ] Sampling stratejisi var.

## LLM

* [ ] Model adı kaydediliyor.
* [ ] Provider kaydediliyor.
* [ ] Prompt/completion token sayıları kaydediliyor.
* [ ] Invocation parameter’lar kaydediliyor.
* [ ] Prompt template version kaydediliyor.
* [ ] Sensitive prompt masking stratejisi var.

## RAG

* [ ] Retriever span ayrı.
* [ ] Embedding span ayrı.
* [ ] Vector DB search span ayrı.
* [ ] Query kaydediliyor.
* [ ] top_k ve filter bilgisi kaydediliyor.
* [ ] Retrieved document id/source/score kaydediliyor.
* [ ] Büyük document content’leri sınırlı tutuluyor.

## Agent / Tool

* [ ] Agent span ayrı.
* [ ] Tool call’lar ayrı span.
* [ ] Tool input/output kontrollü kaydediliyor.
* [ ] Tool errors yakalanıyor.
* [ ] Agent route/decision metadata olarak tutuluyor.

## Privacy

* [ ] PII masking var.
* [ ] Secret/API key span’e yazılmıyor.
* [ ] Production logging seviyesi kontrollü.
* [ ] Embedding vector’leri saklanmıyor.
* [ ] Büyük payload limitleri var.

## Evaluation

* [ ] Trace veya span bazlı eval score tutuluyor.
* [ ] Eval prompt version tutuluyor.
* [ ] Judge model adı tutuluyor.
* [ ] Human feedback/annotation mümkünse trace’e bağlanıyor.

---

# 20. Önerilen Mimari

Basit local geliştirme mimarisi:

```text
FastAPI / LangGraph App
    ↓
OpenTelemetry SDK
    ↓
OpenInference Instrumentation
    ↓
OTLP HTTP Exporter
    ↓
Phoenix local server
    ↓
Phoenix UI
```

Production mimarisi:

```text
AI Application
    ↓
OpenTelemetry SDK
    ↓
OpenTelemetry Collector
    ↓
Processors
      - batching
      - sampling
      - redaction
      - resource enrichment
    ↓
Exporters
      - Phoenix
      - long-term trace backend
      - metrics/log backend
```

Production’da doğrudan app → Phoenix yapılabilir ama daha kontrollü yapı için OpenTelemetry Collector kullanmak daha sağlıklıdır.

Collector ile:

* Sampling
* Retry
* Batch
* Redaction
* Multi-destination export
* Resource attribute enrichment
* Environment bazlı routing

daha kolay yönetilir.

---

# 21. Kod Tarafında Önerilen Basit Pattern

## 21.1 Root Span

```python
with tracer.start_as_current_span("POST /api/chat") as root_span:
    root_span.set_attribute("session.id", session_id)
    root_span.set_attribute("user.id", user_id)
    root_span.set_attribute("metadata.feature", "policy_rag_chat")

    response = run_rag_pipeline(user_message)
```

## 21.2 Chain Span

```python
with tracer.start_as_current_span("policy_rag.answer_question") as span:
    span.set_attribute("openinference.span.kind", "CHAIN")
    span.set_attribute("input.value", user_question)

    answer = generate_answer(user_question)

    span.set_attribute("output.value", answer)
```

## 21.3 Retriever Span

```python
with tracer.start_as_current_span("retriever.search_policy_docs") as span:
    span.set_attribute("openinference.span.kind", "RETRIEVER")
    span.set_attribute("retrieval.query", query)
    span.set_attribute("retrieval.top_k", top_k)

    docs = retriever.search(query, top_k=top_k)

    span.set_attribute("retrieval.document_count", len(docs))
```

## 21.4 Error Handling

```python
try:
    result = call_tool(input_data)
except Exception as exc:
    span.record_exception(exc)
    span.set_status(Status(StatusCode.ERROR, str(exc)))
    raise
```

---

# 22. Kısa Özet

OpenTelemetry, trace datasının standart şekilde oluşturulmasını ve taşınmasını sağlar.

OpenInference, LLM/AI uygulamalarındaki özel span türlerini ve attribute’ları standartlaştırır.

Phoenix, bu trace’leri AI observability odaklı şekilde görselleştirir ve debugging/evaluation sürecini kolaylaştırır.

İyi bir tracing yapısı sadece teknik hataları değil, LLM kalitesini de analiz edebilmelidir.

Başarılı bir observability setup’ı şu sorulara hızlı cevap vermelidir:

* Request nerede yavaşladı?
* Hangi LLM çağrısı pahalıydı?
* Hangi prompt versiyonu kullanıldı?
* Retrieval doğru context’i getirdi mi?
* Tool doğru çalıştı mı?
* Agent doğru karar verdi mi?
* Output güvenli ve kaliteli miydi?
* Hata hangi span’de oluştu?
* Production’da hangi kullanıcı/session etkilenmiş?

En iyi yaklaşım:

```text
OpenTelemetry ile standart trace altyapısı
+
OpenInference ile AI-specific semantic attribute’lar
+
Phoenix ile LLM observability, debugging ve evaluation
```

Bu üçlü birlikte kullanıldığında LLM sistemleri “kara kutu” olmaktan çıkar; izlenebilir, debug edilebilir, ölçülebilir ve iyileştirilebilir hale gelir.
