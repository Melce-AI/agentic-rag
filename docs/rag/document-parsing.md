# Document Parsing

Document parsing is the first step in the ingest pipeline. When a binary file (PDF, DOCX, PPTX, XLSX) is uploaded, it must be converted to plain text before chunking and embedding can happen. The quality of this conversion directly affects retrieval quality — garbled or reordered text produces bad chunks, which produce bad embeddings, which produce bad search results.

## Why Docling

Most PDF parsers (pypdf, pdfminer) extract text in stream order, which breaks on multi-column layouts, tables, and figures. A two-column academic paper becomes interleaved garbage. A table becomes a flat sequence of cell values with no row context.

Docling uses ML models to understand document layout before extracting text:

- **Reading order detection** — determines the correct left-to-right, top-to-bottom flow across columns
- **Table structure recognition** — identifies table boundaries, headers, and cells; exports as structured CSV
- **Heading hierarchy** — detects section titles and nesting, which feeds directly into `HeadingAwareChunker`
- **Figure handling** — skips or describes visual content instead of producing noise

For enterprise RAG where documents are contracts, reports, and technical specs, this matters. The HeadingAwareChunker produces better chunks from well-structured markdown than from flattened text.

## Two-parser design

Docling brings in `torch` and `transformers` as dependencies (~250 MB CPU, ~530 MB CUDA). This is acceptable at runtime but made Docker builds slow. The solution is two parsers behind a single interface.

```
src/rag/
  parsers.py   — DoclingParser, LightweightParser, binary_parser singleton
  loaders.py   — load_document, _PARSERS dispatch table
```

`parsers.py` checks at import time whether docling is installed:

```python
_DOCLING_AVAILABLE = importlib.util.find_spec("docling") is not None

binary_parser: DoclingParser | LightweightParser = (
    DoclingParser() if _DOCLING_AVAILABLE else LightweightParser()
)
```

`loaders.py` dispatches by file type through a single dict, unaware of which parser is active:

```python
_PARSERS = {
    DocumentFileType.PDF:  binary_parser.to_markdown,
    DocumentFileType.DOCX: binary_parser.to_markdown,
    DocumentFileType.PPTX: binary_parser.to_markdown,
    DocumentFileType.XLSX: binary_parser.to_csv_tables,
}
```

### DoclingParser

ML-powered. Lazy-initialises the `DocumentConverter` on the first request — model loading takes a few seconds, but the converter is reused across all subsequent requests.

`to_markdown` is used for prose formats (PDF, DOCX, PPTX).
`to_csv_tables` is used for spreadsheets (XLSX) so rows feed directly into `TableChunker`.

### LightweightParser

Fallback when docling is not installed. Uses:

| Format | Library |
|--------|---------|
| PDF | pypdf |
| DOCX | python-docx |
| PPTX | python-pptx |
| XLSX | openpyxl |

No ML, no layout analysis. Text is extracted in document stream order. Acceptable for simple documents; degrades on multi-column PDFs and tables.

## Dependency isolation

Docling lives in an optional `[ingest]` dependency group, not in the main dependencies. This is the key build optimization.

```toml
# pyproject.toml
[dependency-groups]
ingest = ["docling>=2.104.0", "torch", "torchvision"]

[tool.uv.sources]
torch      = [{ index = "pytorch-cpu" }]
torchvision = [{ index = "pytorch-cpu" }]

[[tool.uv.index]]
name = "pytorch-cpu"
url  = "https://download.pytorch.org/whl/cpu"
explicit = true
```

**CPU-only torch:** Docling uses torch for inference (layout models, OCR), not training. The CPU variant (~250 MB) is sufficient. The CUDA variant (~530 MB) was the default from PyPI and unnecessarily inflated the image. `torchvision` must also come from the CPU index — the PyPI variant links against CUDA operators that do not exist in the CPU torch build, causing a `RuntimeError` at import time.

**Dockerfile layer split:** The builder stage runs `uv sync` twice:

```dockerfile
# Layer 1 — main deps (no torch). Fast, rebuilt on every non-ingest dep change.
RUN --mount=type=cache,target=/root/.cache \
    uv sync --locked --no-dev --no-install-project

# Layer 2 — ingest group (docling + torch). Cached until ingest group changes.
RUN --mount=type=cache,target=/root/.cache \
    uv sync --locked --no-dev --group ingest --no-compile-bytecode --no-install-project
```

With this split, adding a LangChain package (which changes Layer 1) does not invalidate Layer 2. Torch is only re-downloaded when the `[ingest]` group itself changes — which is rare.

`--no-compile-bytecode` on Layer 2 skips `.pyc` compilation for torch and transformers. These packages contain thousands of Python files; precompiling them adds several minutes to the build with negligible runtime benefit.

**Runtime system libraries:** The `runtime-base` stage installs the system libraries that OpenCV (a Docling dependency) requires on `python:3.13-slim`:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxcb1 \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
```

These are not needed at build time (wheels are pre-built binaries) but are required at runtime when OpenCV initialises.

## Build time summary

| Scenario | Layer 1 | Layer 2 | Total |
|----------|---------|---------|-------|
| First build ever | ~2 min | ~5 min | ~7 min |
| Code change | cache | cache | seconds |
| New main dependency | rebuild | cache | ~2 min |
| Docling version bump | cache | rebuild | ~5 min |

## Supported formats

| Extension | Parser method | Chunker |
|-----------|--------------|---------|
| `.pdf` | `to_markdown` | HeadingAwareChunker |
| `.docx` | `to_markdown` | HeadingAwareChunker |
| `.pptx` | `to_markdown` | HeadingAwareChunker |
| `.xlsx` | `to_csv_tables` | TableChunker |
| `.md`, `.txt` | UTF-8 decode | HeadingAwareChunker |
| `.csv` | UTF-8 decode | TableChunker |