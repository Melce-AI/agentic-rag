# Advanced RAG Foundation

This document records the first real RAG foundation for Sentinel-MCP.

## Decisions

- Started with Markdown/plain-text ingest, then added CSV (zero-dependency, stdlib
  `csv`) and PDF (`pypdf`, BSD-licensed, pure Python) loaders. Excel/Parquet are next.
- Loaders dispatch by file extension and tag each document with a `content_kind`
  (`text` vs `tabular`); ingest selects the chunker from that tag. Prose (`.md`,
  `.txt`, `.pdf`) uses the heading-aware chunker; tabular data (`.csv`) uses the
  row-oriented `TableChunker`, which serializes each row as self-describing
  `column: value` pairs and repeats the column schema in every chunk so headers
  are never lost when a table is split.
- Use `POST /documents/ingest` as the first document ingest route.
- Add `POST /search` as the first retrieval surface.
- Use local FastEmbed models so v1 does not require external API keys:
  `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` for dense embeddings
  and `Qdrant/bm25` for sparse embeddings.
- Store chunks in Qdrant with named dense and sparse vectors, plus citation-friendly payload metadata.
- Do not add reranking in this milestone; Qdrant RRF returns candidates and the retriever applies deterministic top-k ordering.

## Flow

1. API receives `source_name`, `content`, and required `tenant_id`. File uploads
   go through `src.rag.loaders.load_document`, which extracts text per file type
   and resolves the `content_kind`.
2. `src.rag.chunking` picks a strategy by `content_kind`: the heading-aware chunker
   preserves heading hierarchy in `heading_path` for prose; the `TableChunker`
   packs whole rows up to the token budget for tabular data.
3. `src.rag.embeddings` creates dense and sparse vectors with FastEmbed.
4. `src.rag.ingest` writes chunk points through the Qdrant storage adapter.
5. `src.rag.retriever` embeds the query, asks Qdrant for tenant-filtered hybrid dense+sparse candidates, and returns top-k citation results.

## Boundaries

- Routers stay thin and do not call Qdrant directly.
- `src.rag.models` owns domain models; `src.schemas` owns public API DTOs.
- Tests mock embedding and Qdrant calls; no network or model download is required in CI.
- Excel/Parquet ingestion (reusing `TableChunker`), LLM answer generation, MCP tools, LangGraph agents, and real reranking are later steps.
