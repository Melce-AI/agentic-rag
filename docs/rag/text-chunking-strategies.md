# Text Chunking Strategies

> Disclaimer: This page focuses on text chunking. Other data types, such as
> images, video, audio, and code, can also be chunked, but text is the most
> common starting point for RAG systems.

## The Real Beginning: Data Structure

Our pipeline starts with the data and how we represent what we want to search.
In practice, this means thinking about the structure of the data we store. Most
real-world data is messy:

- Text documents are long.
- Product descriptions vary in length.
- User profiles can have nested attributes.

We need a way to break this data down into manageable chunks.

Data preprocessing, especially chunking and embedding, defines the data that
Qdrant works with.

## From Raw Text to Search-Ready

### The Problem with Whole Documents

Storing an entire document as a single vector is often ineffective because
embedding models operate with a limited context window.

Every model has a maximum number of tokens it can process at once. For example,
many sentence-transformer models have a limit of 512 tokens, while OpenAI's
`text-embedding-3-small` has a limit of 8,191 tokens. If a document exceeds this
maximum token count, the information past that limit is dropped, causing a large
loss of data.

Even if a document fits within the limit, embedding a large, multi-topic text
into a single vector can dilute its meaning. The model creates a semantic
average of all the content, making it difficult for a specific query to find a
precise match.

This is where chunking comes in. The goal is to create chunks that are:

- Small enough to be processed effectively by embedding models without
  truncation.
- Large enough to contain meaningful, coherent context.

By breaking a document into focused chunks, each chunk gets its own vector that
accurately represents a specific idea. This makes search much more precise.

### Example: Qdrant Collection Configuration Guide

Consider a multi-page document like a Qdrant collection configuration guide that
covers everything from HNSW to sharding and quantization.

If a user asks, "What does the `m` parameter do?", whole-document embedding is a
poor fit.

Without chunking:

- The guide may be too long and get truncated by the model, potentially losing
  the section about the `m` parameter entirely.
- Even if it fits, the resulting vector is a noisy average of all topics, making
  it unlikely to be retrieved for such a specific query.

With proper chunking:

- The guide is split into topic-focused chunks, such as one chunk for HNSW
  parameters.
- The chunk about the `m` parameter gets its own precise vector.
- Qdrant can retrieve this specific chunk and provide a clear, relevant answer.

## Why Chunking Makes All the Difference

Instead of treating documents as monolithic blocks, you break them into
paragraphs, headings, and subsections. Each chunk gets its own vector tied to a
specific idea or topic.

You can also attach metadata to each chunk, such as:

- Section title.
- Page number.
- Original source document.
- Tags.

This enables:

- Filtered retrieval: "Only show results from this section."
- Context-aware fragments: precise answers to specific queries.
- Efficient processing: no wasted tokens on irrelevant content.

## Chunking Strategies: The Shape Matters

How you chunk affects what your embeddings capture, what your retriever can
surface, and what your LLM can reason over. There is no one-size-fits-all
approach.

## 1. Fixed-Size Chunking

### Approach

Define a number of tokens or words per chunk, such as 200, with a small overlap
buffer to preserve context.

Example text:

```text
The HNSW algorithm builds a multi-layer graph where each node represents a
vector. The algorithm starts by inserting vectors into the bottom layer and then
selectively promotes some to higher layers based on probability. This creates
shortcuts that allow for faster traversal during search operations.
```

Fixed-size chunks with 10 words each:

```text
Chunk 1: The HNSW algorithm builds a multi-layer graph where each
Chunk 2: node represents a vector. The algorithm starts by inserting vectors
Chunk 3: into the bottom layer and then selectively promotes some to
Chunk 4: higher layers based on probability. This creates shortcuts that allow
Chunk 5: for faster traversal during search operations.
```

Notice how each chunk, except the last one, has exactly 10 words, but sentences
break arbitrarily.

### Implementation

```python
def fixed_size_chunk(text: str, chunk_size: int = 200, overlap: int = 50) -> list[str]:
    words = text.split()
    chunks = []

    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i : i + chunk_size])
        chunks.append(chunk)

    return chunks
```

### Pros

- Simple to implement.
- Consistent chunk sizes.
- Predictable processing.

### Cons

- Ignores natural language boundaries.
- May split mid-sentence or mid-thought.
- Has no semantic awareness.

Best for: documents lacking consistent formatting and initial prototyping.

## 2. Sentence-Based Chunking

### Approach

Break documents into sentences using a tokenizer, then group sentences into
chunks under a specified word count.

Example text:

```text
The HNSW algorithm builds a multi-layer graph. Each node represents a vector in
the collection. The algorithm creates shortcuts between layers for faster search.
This hierarchical structure enables efficient approximate nearest neighbor
queries.
```

Sentence-based chunks:

```text
Chunk 1: The HNSW algorithm builds a multi-layer graph. Each node represents a vector in the collection.
Chunk 2: The algorithm creates shortcuts between layers for faster search. This hierarchical structure enables efficient approximate nearest neighbor queries.
```

Each chunk contains complete sentences, preserving the logical flow. This method
keeps the structure neat and maintains complete thoughts, though chunk sizes
vary.

### Implementation

```python
from nltk.tokenize import sent_tokenize


def sentence_chunk(text: str, max_words: int = 150) -> list[str]:
    sentences = sent_tokenize(text)
    chunks, buffer, length = [], [], 0

    for sentence in sentences:
        count = len(sentence.split())

        if length + count > max_words and buffer:
            chunks.append(" ".join(buffer))
            buffer, length = [], 0

        buffer.append(sentence)
        length += count

    if buffer:
        chunks.append(" ".join(buffer))

    return chunks
```

### Pros

- Preserves complete thoughts.
- Respects natural language boundaries.
- Usually has good semantic coherence.

### Cons

- Produces irregular chunk lengths.
- Sentence size varies significantly.
- May not respect topic boundaries.

Best for: RAG systems, Q&A applications, and general text processing.

## 3. Paragraph-Based Chunking

### Approach

Split on paragraph breaks, leveraging existing document structure.

Example text:

```text
Paragraph 1: HNSW is a graph-based algorithm for approximate nearest neighbor
search. It builds a multi-layer structure where each layer contains a subset of
the data points.

Paragraph 2: The algorithm works by creating connections between nearby points
in each layer. Higher layers have fewer points but longer connections, creating
shortcuts for faster traversal during search operations.

Paragraph 3: When searching, HNSW starts from the top layer and gradually moves
down, using the shortcuts to quickly navigate to the target region before
performing a more detailed search in the bottom layer.
```

Each chunk corresponds to an entire paragraph: a natural boundary where ideas
tend to cohere. This approach respects the author's intended organization and
keeps related concepts together.

### Implementation

```python
def paragraph_chunk(text: str) -> list[str]:
    return [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]
```

### Pros

- Aligns with natural topic boundaries.
- Produces semantically rich chunks by default.
- Respects the author's organization.

### Cons

- Produces unpredictable sizes, from a single line to a whole page.
- May need token limits or fallback splitting.
- Depends on clean document structure.

Best for: articles, blogs, documentation, books, and emails.

## 4. Sliding Window Chunking

### Approach

Create overlapping chunks to maintain context continuity.

Example text:

```text
HNSW builds a multi-layer graph where each node represents a vector. The
algorithm starts by inserting vectors into the bottom layer and then selectively
promotes some to higher layers based on probability. This creates shortcuts that
allow for faster traversal during search operations.
```

Sliding window with 10 words per chunk and 4 words of overlap:

```text
Chunk 1: HNSW builds a multi-layer graph where each node represents a
Chunk 2: where each node represents a vector. The algorithm starts by inserting vectors
Chunk 3: starts by inserting vectors into the bottom layer and then selectively promotes
Chunk 4: and then selectively promotes some to higher layers based on probability. This
```

Sliding window chunking creates overlapping segments of consistent size. Each
chunk maintains a fixed word count with a consistent overlap, preserving
information continuity across boundaries.

### Implementation

```python
def sliding_window(text: str, window: int = 200, stride: int = 100) -> list[str]:
    words = text.split()
    chunks = []

    for i in range(0, len(words) - window + 1, stride):
        chunk = " ".join(words[i : i + window])
        chunks.append(chunk)

    return chunks
```

### Pros

- Maintains context at boundaries.
- Can increase recall.
- Reduces information loss.

### Cons

- Adds storage redundancy, often 20-50%.
- Increases processing cost.
- May return duplicate information.

Best for: critical applications where missing information is costly, especially
when paired with reranking.

## 5. Recursive Chunking

### Approach

Use a fallback hierarchy of separators when data does not follow predictable
structure.

Recursive splitting tries to split on large blocks first, such as headings or
paragraph breaks. If a chunk is still too long, it falls back to smaller
separators like lines or sentences. If it still does not fit, it continues with
words or characters as a last resort.

Example messy text:

```text
# HNSW Overview

The HNSW algorithm builds a multi-layer graph.
Each node represents a vector in the collection.

The algorithm creates shortcuts between layers for faster search. This
hierarchical structure enables efficient approximate nearest neighbor queries.

## Performance Benefits
HNSW provides logarithmic search complexity.
```

Recursive chunking tries paragraph breaks first, then sentences, then words:

```text
Chunk 1: # HNSW Overview
Chunk 2: The HNSW algorithm builds a multi-layer graph.
Chunk 3: Each node represents a vector in the collection.
Chunk 4: The algorithm creates shortcuts between layers for faster search.
Chunk 5: This hierarchical structure enables efficient approximate nearest neighbor queries.
Chunk 6: ## Performance Benefits
         HNSW provides logarithmic search complexity.
```

Typical hierarchy:

- Large blocks: headings and paragraph breaks.
- Medium blocks: lines and sentences.
- Small blocks: spaces and characters.

### Implementation

```python
from langchain.text_splitter import RecursiveCharacterTextSplitter


splitter = RecursiveCharacterTextSplitter(
    chunk_size=512,
    chunk_overlap=100,
    separators=["\n\n", "\n", ". ", " ", ""],
)

text = """
Hello, world! More text here. Another line.
Hello, world! More text here. Another line...
"""

chunks = splitter.split_text(text)
```

### Pros

- Adapts to messy or inconsistent input.
- Preserves semantic coherence when possible.
- Handles various document formats.

### Cons

- Heuristic-based results may be inconsistent.
- More complex than simple splitting.
- May not work perfectly with every content type.

Best for: scraped web content, mixed formats, and CMS exports.

## 6. Semantic-Aware Chunking

### Approach

Use embeddings to detect meaning shifts and break at topic boundaries.

Everything up to this point has been about structure. But structure is not the
same as meaning. Semantic chunking uses embeddings to find meaning shifts: it
detects where topics or semantic coherence changes and splits there.

Example text with topic shifts:

```text
HNSW is a graph-based algorithm for vector search. It builds hierarchical layers
for efficient navigation. The algorithm uses probability to promote nodes between
layers. Vector databases like Qdrant implement HNSW for fast similarity search.
Machine learning models generate embeddings for text data. These embeddings
capture semantic meaning in high-dimensional space.
```

Semantic-aware chunks:

```text
Topic 1 - HNSW Algorithm:
HNSW is a graph-based algorithm for vector search. It builds hierarchical layers
for efficient navigation. The algorithm uses probability to promote nodes between
layers.

Topic 2 - Vector Databases:
Vector databases like Qdrant implement HNSW for fast similarity search.

Topic 3 - Machine Learning:
Machine learning models generate embeddings for text data. These embeddings
capture semantic meaning in high-dimensional space.
```

Semantic chunking does not care about sentence count or fixed token limits. It
looks for natural boundaries in meaning. If a definition needs multiple
sentences, it keeps them together. This improves retrieval because chunks
contain complete, coherent concepts.

### Process

1. Embed sentences or small segments.
2. Calculate similarity between consecutive segments.
3. Identify topic transitions where similarity drops.
4. Split at coherence boundaries.

### Implementation

```python
import numpy as np
from sentence_transformers import SentenceTransformer


def semantic_chunking(text: str, similarity_threshold: float = 0.5) -> list[str]:
    model = SentenceTransformer("all-MiniLM-L6-v2")
    sentences = [sentence.strip() for sentence in text.split(".") if sentence.strip()]
    embeddings = model.encode(sentences)

    chunks = []
    current_chunk = [sentences[0]]

    for i in range(1, len(sentences)):
        similarity = np.dot(embeddings[i - 1], embeddings[i]) / (
            np.linalg.norm(embeddings[i - 1]) * np.linalg.norm(embeddings[i])
        )

        if similarity < similarity_threshold:
            chunks.append(". ".join(current_chunk))
            current_chunk = [sentences[i]]
        else:
            current_chunk.append(sentences[i])

    chunks.append(". ".join(current_chunk))
    return chunks
```

The trade-off is computational cost. You embed the full document upfront just to
decide where to split it, before storing anything. It is slower and more
expensive, but each chunk carries more coherent ideas.

### Pros

- High semantic precision.
- Each chunk carries coherent ideas.
- Strong fit for complex documents.

### Cons

- Computationally expensive because it requires embedding the document before
  chunking.
- Requires additional model inference.
- Slows down the ingestion pipeline.

Best for: legal documents, research papers, and critical applications requiring
high precision.

## Text Chunking Strategy Comparison

| Method | Strength | Trade-off | Best For |
| --- | --- | --- | --- |
| Fixed-size | Simple, predictable chunks | Ignores structure and can break meaning | Raw or unstructured text |
| Sentence | Preserves complete thoughts | Inconsistent sizes | RAG and Q&A systems |
| Paragraph | Aligns with semantic units | Large variance in length | Docs, manuals, instructional content |
| Sliding window | Maintains context across boundaries | Redundant and compute-heavy | Reranking and high-recall retrieval |
| Recursive | Flexible with messy input | Heuristic and sometimes brittle | Scraped web content and mixed sources |
| Semantic | High-quality and meaning-aware | Slower and resource-intensive | Legal, research, critical QA |

> Note: Sometimes it is necessary to keep the document intact. If chunking is too
> complicated, or the document is visually rich with diagrams and graphs, you can
> use vision-language models to embed the whole page.

## Adding Meaning with Metadata

Chunks by themselves are just fragments of text. They do not tell you where they
came from, what they belong to, or how to control what gets retrieved.

That is where metadata comes in.

In Qdrant, metadata lives in the payload: a JSON object attached to each vector
that carries real structure. You can use it to store anything needed to identify
or organize chunks.

### Essential Metadata Fields

```json
{
  "document_id": "collection-config-guide",
  "document_title": "What is a Vector Database",
  "section_title": "What Is a Vector",
  "chunk_index": 7,
  "chunk_count": 15,
  "url": "https://qdrant.tech/documentation/manage-data/collections/",
  "tags": ["qdrant", "vector search", "point", "vector", "payload"],
  "source_type": "documentation",
  "created_at": "2025-01-15T10:00:00Z",
  "content": "There are three key elements that define a vector in vector search...",
  "word_count": 45,
  "char_count": 287
}
```

## What Metadata Enables

> Disclaimer: For performance reasons, filterable fields should be indexed using
> Qdrant payload indexes.

### 1. Filtered Search

You can filter results based on exact metadata values, which is ideal for
categorical data.

```python
from qdrant_client import models


query_filter = models.Filter(
    must=[
        models.FieldCondition(
            key="document_id",
            match=models.MatchValue(value="collection-config-guide"),
        )
    ]
)
```

### 2. Hybrid Search with Text Filtering

For more powerful text-based filtering, you can combine vector search with
traditional keyword search. This requires a full-text index on the payload field.

```python
query_filter = models.Filter(
    must=[
        models.FieldCondition(
            key="content",
            match=models.MatchText(text="HNSW algorithm"),
        )
    ]
)
```

### 3. Grouped Results

Grouped results let you return, for example, the most relevant chunk from each
source document.

```python
group_by = "document_id"
```

### 4. Rich Result Display

Metadata can support user-facing result displays with:

- Original content and source attribution.
- Section context for better understanding.
- Direct links to full documents.
- Creation timestamps for freshness.

### 5. Permission Control

Metadata can also enforce retrieval-time access control.

```python
query_filter = models.Filter(
    must=[
        models.FieldCondition(
            key="access_level",
            match=models.MatchValue(value="public"),
        )
    ]
)
```

## Search with Metadata

```python
from qdrant_client import models


def search_with_filters(query: str, document_type: str | None = None, date_range: dict | None = None):
    """Search with metadata filtering."""
    filter_conditions = []

    if document_type:
        filter_conditions.append(
            models.FieldCondition(
                key="source_type",
                match=models.MatchValue(value=document_type),
            )
        )

    if date_range:
        filter_conditions.append(
            models.FieldCondition(
                key="created_at",
                range=models.Range(gte=date_range["start"], lte=date_range["end"]),
            )
        )

    query_filter = models.Filter(must=filter_conditions) if filter_conditions else None

    return client.query_points(
        collection_name="documents",
        query=generate_embedding(query),
        query_filter=query_filter,
        limit=5,
    )
```

## Performance Considerations

### Token Efficiency

Consider your embedding model's token limits:

- OpenAI `text-embedding-3-small`: 8,191 tokens max.
- Sentence Transformers: varies greatly by model. Many classic models, such as
  `all-MiniLM-L6-v2`, have a maximum length of 512 tokens, but newer models can
  handle much more.
- Always leave buffer space for special tokens and formatting.

### Overlap Recommendations

- 10-20% overlap: good balance for most applications.
- 25-50% overlap: high-recall scenarios where missing information is costly.
- No overlap: when storage and compute costs are the primary concern.

## Key Takeaways

- Chunking strategy directly impacts search quality. Choose based on your text
  data and use case.
- Smaller, focused chunks provide more precise results than whole-document
  embeddings.
- Metadata is crucial for filtering, grouping, access control, and result
  presentation.
- Different strategies have different trade-offs. Experiment to find what works.
- Semantic text chunking is powerful but computationally expensive.
- Overlap helps preserve context, but increases storage requirements.

## What's Next

Now that you understand how to structure and prepare textual data, the next step
is to put these concepts into practice in the RAG ingestion pipeline.

> Remember: Qdrant doesn’t make assumptions about what your data means. It compares vectors and gives you back what’s closest. But what it sees - the structure, the semantics, the context - that’s entirely up to you