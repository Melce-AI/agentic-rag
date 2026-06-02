# RAG business logic ne yapıyor?

Kodun omurgası artık şu akış:

```text
POST /documents/ingest
→ validate input
→ Markdown/plain text chunking
→ dense + sparse embedding
→ chunk payload oluşturma
→ Qdrant batch upsert

POST /search
→ validate query
→ query dense + sparse embedding
→ Qdrant tenant-filtered hybrid query
→ dense + sparse prefetch
→ RRF fusion
→ source-aware RetrievedChunk response
```

## **1. API Boundary**
İki ana endpoint var.

```text
POST /documents/ingest
```

Doküman alıyor:

```json
{
  "source_name": "policy.md",
  "content": "# Security Policy\n...",
  "tenant_id": "demo-company"
}
```

Bu endpoint iş mantığı yapmıyor. Sadece `DocumentIngestService.ingest_document()` çağırıyor.

```text
POST /search
```

Query alıyor:

```json
{
  "query": "database access rules",
  "tenant_id": "demo-company",
  "top_k": 5
}
```

Bu da sadece `HybridRetriever.search()` çağırıyor.

Buradaki business kuralı şu: router ince, RAG logic `src/rag/`, Qdrant detayı `src/storage/qdrant_client.py`.

## **2. Domain Model**
`src/rag/models.py` içinde RAG iç modelleri var:

```python
Document
Chunk
ChunkDraft
RetrievedChunk
```

Bunlar API schema değil. Yani dışarıya dönen DTO değil, iç business model.

Önemli model `Chunk`:

```python
Chunk(
    chunk_id="...",
    document_id="...",
    tenant_id="demo-company",
    text="...",
    heading_path=["Security Policy", "Database Access"],
    chunk_index=3,
    source_name="security-policy.md",
    created_at="...",
    content_hash="..."
)
```

Buradaki business fikir şu: Qdrant’ta “doküman” değil, “chunk” saklıyoruz. Çünkü retrieval chunk seviyesinde yapılır. Kullanıcı soru sorunca tüm PDF/doküman değil, ilgili parça geri dönmeli.

## **3. Chunking Stratejisi**
Chunking `src/rag/chunking.py` içinde.

Şu an desteklenen input:

```text
Markdown / plain text
```

PDF yok, CSV yok.

Strateji:

1. İçerik trim edilir.
2. Markdown heading satırları yakalanır:
   - `#`
   - `##`
   - `###`
   - teknik olarak `######` seviyesine kadar destek var.
3. Heading stack tutulur.
4. Her chunk’a `heading_path` yazılır.
5. Başlık metni chunk text içine dahil edilir.
5. Heading context is included in chunk text so retrieved chunks stand alone.
6. Long sections are split by token budget, not character count.
7. Recursive splitting prefers paragraph, line, sentence-like separators, punctuation, spaces, then a final fallback.
8. Token overlap is applied.
9. Each chunk receives section metadata for citations and future section expansion.

Örnek:

```markdown
# Security Policy
Intro text.

## Database Access
Users must use MFA.

## Audit Logs
Logs are retained.
```

Chunk’lar yaklaşık şöyle olur:

```python
ChunkDraft(
    text="Security Policy\nIntro text.",
    heading_path=["Security Policy"],
    chunk_index=0,
)

ChunkDraft(
    text="Database Access\nUsers must use MFA.",
    heading_path=["Security Policy", "Database Access"],
    chunk_index=1,
)

ChunkDraft(
    text="Audit Logs\nLogs are retained.",
    heading_path=["Security Policy", "Audit Logs"],
    chunk_index=2,
)
```

Business açısından `heading_path` çok önemli. Çünkü search sonucu döndüğümüzde sadece text değil, “bu parça dokümanın hangi bölümünden geldi?” bilgisini de veririz. Bu citation/trace için temel.

Chunk size config is token-based:

```python
RAG_CHUNK_MAX_TOKENS = 350
RAG_CHUNK_OVERLAP_TOKENS = 50
```

The old character-based settings were removed directly. Semantic and LLM-based chunking are intentionally left out of this foundation step.

## **4. Stable ID Mantığı**
`ingest.py` içinde deterministic ID üretiyoruz.

Önce content hash:

```python
content_hash = sha256(content)
```

Sonra document id:

```python
document_id = uuid5(tenant_id + source_name + content_hash)
```

Sonra chunk id:

```python
chunk_id = uuid5(document_id + content_hash + chunk_index)
```

Business sonucu:

- Aynı tenant
- aynı source_name
- aynı content
- aynı chunk_index

tekrar ingest edilirse aynı ID oluşur. Böylece duplicate point üretme riski azalır; Qdrant upsert aynı point’i günceller.

## **5. Embedding Nedir?**
Embedding, text’i sayısal vektöre dönüştürme işi.

Biz iki tür embedding üretiyoruz:

```text
Dense embedding
Sparse embedding
```

İkisini birlikte kullanmamızın sebebi hybrid search.

## **6. Dense Embedding**
Dense embedding semantic similarity içindir.

Config:

```python
RAG_DENSE_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
```

Bu model Türkçe + İngilizce için daha uygun. Vektör boyutu `384`, bu yüzden Qdrant config ile uyumlu:

```python
QDRANT_VECTOR_SIZE = 384
```

Dense vector örnek olarak şuna benzer:

```python
[0.012, -0.44, 0.091, ...]  # 384 float
```

Bu vektör metnin anlamını temsil eder. Örneğin:

```text
"database access"
```

ile

```text
"veritabanı erişim yetkileri"
```

kelime olarak farklı olsa bile dense embedding semantic yakınlık yakalayabilir.

## **7. Sparse Embedding**
Sparse embedding keyword/lexical matching tarafıdır.

Config:

```python
RAG_SPARSE_MODEL = "Qdrant/bm25"
```

BM25 klasik arama motoru mantığına yakın çalışır. Anahtar kelime eşleşmesi, özel terimler, kodlar, ürün adları, policy ID’leri gibi şeylerde dense aramadan daha güvenilir olabilir.

Sparse vector dense vector gibi 384 float değildir. Çok büyük bir vocabulary uzayında sadece bazı pozisyonlar doludur.

Bu yüzden iki listeyle temsil edilir:

```python
SparseEmbedding(
    indices=[102, 9812, 44001],
    values=[0.7, 1.4, 0.9],
)
```

### **`indices` nedir?**
Vocabulary içindeki aktif token/term pozisyonlarıdır.

Örnek mantıksal anlatım:

```text
"database" → index 102
"access"   → index 9812
"mfa"      → index 44001
```

### **`values` nedir?**
O index’teki kelimenin ağırlığıdır. BM25 mantığıyla daha ayırt edici kelimeler daha yüksek ağırlık alabilir.

Yani:

```python
indices=[102, 9812]
values=[0.8, 1.3]
```

şu demek gibi düşünebilirsin:

```text
term#102 metinde var, ağırlığı 0.8
term#9812 metinde var, ağırlığı 1.3
```

Sparse vector’ın avantajı: “SOC2”, “ISO-27001”, “DB-ACCESS-17”, “MFA” gibi özel terimleri iyi yakalar.

## **8. FastEmbed Wrapper**
`src/rag/embeddings.py` şu işi yapıyor:

```text
texts → dense vectors + sparse vectors
query → dense vector + sparse vector
```

İki method var:

```python
embed_documents(texts)
embed_query(text)
```

Ingest sırasında chunk text’leri embed edilir.

Search sırasında query embed edilir.

Hatalar artık çıplak `RuntimeError` olarak kaçmıyor. FastEmbed model yükleme veya embedding üretme patlarsa:

```python
RagEmbeddingError
```

üretir.

## **9. Ingest Business Logic**
`DocumentIngestService.ingest_document()` adımları:

1. `source_name` boş mu kontrol eder.
2. `content` boş mu kontrol eder.
3. Chunker ile content’i chunk’lara böler.
4. Hiç chunk çıkmazsa `RagValidationError`.
5. `content_hash` üretir.
6. `document_id` üretir.
7. Her chunk için:
   - `chunk_id`
   - dense vector
   - sparse vector
   - payload
   oluşturur.
8. Qdrant’a batch upsert eder.

Qdrant’a gönderilen record kabaca:

```python
{
  "id": chunk_id,
  "dense_vector": [...],
  "sparse_indices": [...],
  "sparse_values": [...],
  "payload": {
    "tenant_id": "demo-company",
    "document_id": "...",
    "chunk_id": "...",
    "source_name": "policy.md",
    "heading_path": ["Security Policy", "Database Access"],
    "chunk_index": 3,
    "text": "...",
    "created_at": "...",
    "content_hash": "..."
  }
}
```

Burada payload çok önemli. Vector similarity sadece “hangi point yakın?” der. Payload ise business context verir:

```text
Bu chunk hangi tenant’a ait?
Hangi dokümandan geldi?
Kaynak adı ne?
Dokümanın hangi başlığı altında?
Orijinal text ne?
```

## **10. Qdrant Collection Mantığı**
`src/storage/qdrant_client.py` startup’ta collection hazırlar.

Collection iki vector alanına sahip:

```python
dense-text
sparse-text
```

Dense taraf:

```python
VectorParams(
    size=384,
    distance=Distance.COSINE,
)
```

Sparse taraf:

```python
SparseVectorParams()
```

Yani her point içinde iki vector var:

```python
vector={
  "dense-text": [0.1, 0.2, ...],
  "sparse-text": SparseVector(
      indices=[...],
      values=[...],
  )
}
```

Ayrıca payload index oluşturuyoruz:

```python
tenant_id
document_id
created_at
```

Bu index’ler filtering performansı için önemli. Özellikle `tenant_id` enterprise izolasyon için kritik.

## **11. Batch Upsert**
`upsert_chunks(records)` her chunk’ı Qdrant point’e çeviriyor:

```python
PointStruct(
    id=chunk_id,
    vector={
        "dense-text": dense_vector,
        "sparse-text": SparseVector(indices=..., values=...)
    },
    payload={...}
)
```

Sonra tek batch halinde Qdrant’a gönderiyor.

Business etkisi:
- Her chunk bağımsız aranabilir.
- Aynı chunk ID tekrar gelirse update edilir.
- Batch upsert tek tek insert’e göre daha verimli.

## **12. Hybrid Retrieval**
Search tarafında `HybridRetriever.search()` çalışır.

Adımlar:

1. Query boş mu kontrol eder.
2. Query için dense embedding üretir.
3. Query için sparse embedding üretir.
4. Qdrant adapter’a gider:

```python
query_hybrid(
    dense_vector=...,
    sparse_indices=...,
    sparse_values=...,
    tenant_id=...,
    limit=20,
)
```

Burada `tenant_id` zorunlu. Bu çok önemli: bir tenant başka tenant’ın chunk’larını arama sonucunda göremez.

## **13. Qdrant Hybrid Query ve Prefetch**
Qdrant tarafında şu yapılır:

```python
prefetch=[
    Prefetch(query=dense_vector, using="dense-text", limit=20),
    Prefetch(query=sparse_vector, using="sparse-text", limit=20),
],
query=FusionQuery(fusion=Fusion.RRF),
query_filter=tenant_filter,
limit=20
```

Anlamı:

1. Dense search yap:
   - semantic olarak yakın 20 chunk getir.
2. Sparse search yap:
   - keyword/BM25 olarak yakın 20 chunk getir.
3. Bu iki listeyi RRF ile birleştir.
4. Sadece aynı `tenant_id` içinden getir.

## **14. RRF Fusion Nedir?**
RRF = Reciprocal Rank Fusion.

Basit fikir:

```text
Dense listesinde üstte çıkan iyi.
Sparse listesinde üstte çıkan da iyi.
İki listede de iyi sıradaysa daha da iyi.
```

RRF score, raw cosine score veya BM25 score’u doğrudan karşılaştırmaya çalışmaz. Çünkü dense score ve sparse score farklı dünyalardır. Bunun yerine rank sırasını kullanır.

Örnek:

Dense sonucu:

```text
1. chunk A
2. chunk B
3. chunk C
```

Sparse sonucu:

```text
1. chunk B
2. chunk D
3. chunk A
```

RRF şunu fark eder:

```text
A dense'te 1., sparse'ta 3.
B dense'te 2., sparse'ta 1.
```

A ve B güçlü adaydır. Sadece dense veya sadece sparse kullanmaktan daha dengeli sonuç verir.

Business olarak bu iyi başlangıç çünkü eval set olmadan özel weighting yapmak riskli. Qdrant RRF güvenli default.

## **15. Search Response**
Qdrant’tan dönen point payload’ı `RetrievedChunk` modeline çevriliyor.

Response şuna benzer:

```json
{
  "success": true,
  "data": {
    "results": [
      {
        "chunk_id": "...",
        "document_id": "...",
        "source_name": "policy.md",
        "heading_path": ["Security Policy", "Database Access"],
        "text": "Users must use MFA...",
        "score": 0.83,
        "metadata": {
          "tenant_id": "demo-company",
          "chunk_index": 3,
          "created_at": "...",
          "content_hash": "..."
        }
      }
    ]
  }
}
```

Bu “kaynak bilgili sonuç” demek. Henüz LLM answer yok ama ileride LLM’e context verirken citation için gereken metadata hazır.

## **16. Delete by Document**
Qdrant adapter’da:

```python
delete_by_document_id(document_id, tenant_id)
```

var.

Bu method tüm tenant içinde belirli dokümana ait chunk’ları siler. Tenant filtresi burada da zorunlu. Böylece yanlışlıkla başka tenant’ın aynı document ID’si veya data alanı etkilenmez.

## **17. Error Business Logic**
Şu an hata ayrımı şöyle:

- Request schema hatası:
  - `REQ_422`
- RAG validation:
  - `RAG_422`
- Chunking config hatası:
  - `RAG_CFG_500`
- Embedding hatası:
  - `RAG_EMBED_500`
- Ingest pipeline hatası:
  - `RAG_INGEST_500`
- Retrieval pipeline hatası:
  - `RAG_SEARCH_500`
- Qdrant operation hatası:
  - `VEC_02`

Global exception handler bunları standart response’a çeviriyor.

## **18. Şu An Ne Kanıtlıyoruz?**
Bu milestone’un business sorusu şuydu:

```text
Bir dokümanı ingest edip ilgili chunk'ları güvenilir biçimde geri bulabiliyor muyuz?
```

Kod seviyesi cevap:

```text
Evet, foundation hazır.
```

Ama gerçek Qdrant container + gerçek FastEmbed modeliyle manuel smoke test henüz ayrı bir adım olarak yapılmalı.

Unit/API testlerde kanıtlananlar:
- heading path korunuyor
- chunk ID stable
- payload doğru
- dense/sparse vector shape doğru aktarılıyor
- retriever Qdrant hybrid query çağırıyor
- search response normalize ediliyor
- errors global shape’e uyuyor

### **19. Şu An Bilinçli Olarak Yok**
Bunları eklemedik:

```text
LLM answer generation
PDF parsing
CSV parsing
reranker
LangChain
LangGraph agents
MCP integration
retrieval eval dataset
auth/RBAC
```

Retrieval hattını önce çıplak ve gözlemlenebilir hale getirdik.

### **20. Bir Sonraki En Mantıklı Business Adım**

```text
Gerçek Qdrant + gerçek FastEmbed ile smoke test
```

Yani:

1. Qdrant container çalıştır.
2. Küçük Türkçe/İngilizce markdown doküman ingest et.
3. `/search` ile:
   - Türkçe query
   - İngilizce query
   - özel terim query
   - yanlış tenant query
   test et.
4. Sonuçları küçük `docs/rag/retrieval-smoke-results.md` dosyasına kaydet.

Sonraki adımlar: retrieval eval seti veya PDF parser.
