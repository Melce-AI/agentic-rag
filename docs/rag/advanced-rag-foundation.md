# Advanced RAG Foundation

This document records the first real RAG foundation for Sentinel-MCP.

## Decisions

- Start with Markdown/plain-text ingest before PDF or CSV parsing.
- Use `POST /documents/ingest` as the first document ingest route.
- Add `POST /search` as the first retrieval surface.
- Use local FastEmbed models so v1 does not require external API keys:
  `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` for dense embeddings
  and `Qdrant/bm25` for sparse embeddings.
- Store chunks in Qdrant with named dense and sparse vectors, plus citation-friendly payload metadata.
- Do not add reranking in this milestone; Qdrant RRF returns candidates and the retriever applies deterministic top-k ordering.

## Flow

1. API receives `source_name`, `content`, and required `tenant_id`.
2. `src.rag.chunking` splits Markdown/plain text with heading hierarchy preserved in `heading_path`.
3. `src.rag.embeddings` creates dense and sparse vectors with FastEmbed.
4. `src.rag.ingest` writes chunk points through the Qdrant storage adapter.
5. `src.rag.retriever` embeds the query, asks Qdrant for tenant-filtered hybrid dense+sparse candidates, and returns top-k citation results.

## Boundaries

- Routers stay thin and do not call Qdrant directly.
- `src.rag.models` owns domain models; `src.schemas` owns public API DTOs.
- Tests mock embedding and Qdrant calls; no network or model download is required in CI.
- PDF parsing, CSV ingestion, LLM answer generation, MCP tools, LangGraph agents, and real reranking are later steps.
