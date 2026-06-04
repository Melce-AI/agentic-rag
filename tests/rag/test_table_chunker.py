from src.rag.chunking import TableChunker


def test_each_row_is_self_describing_with_column_names():
    chunker = TableChunker(max_tokens=350)

    chunks = chunker.split("name,role\nAyse,admin\nMehmet,viewer\n")

    assert len(chunks) == 1
    text = chunks[0].text
    assert "columns: name, role" in text
    assert "name: Ayse | role: admin" in text
    assert "name: Mehmet | role: viewer" in text


def test_every_chunk_repeats_the_column_schema():
    chunker = TableChunker(max_tokens=350, rows_per_chunk=1)

    chunks = chunker.split("name,role\nAyse,admin\nMehmet,viewer\n")

    assert len(chunks) == 2
    assert all(chunk.text.startswith("columns: name, role") for chunk in chunks)
    assert [chunk.chunk_index for chunk in chunks] == [0, 1]


def test_token_budget_packs_whole_rows_without_splitting_records():
    chunker = TableChunker(max_tokens=25)

    chunks = chunker.split("name,role\nAyse,admin\nMehmet,viewer\nFatma,editor\n")

    # Records are atomic: a row never appears split across two chunks.
    assert len(chunks) > 1
    for chunk in chunks:
        for line in chunk.text.splitlines():
            if line.startswith("name:"):
                assert line.count("|") == 1  # exactly name + role, never a fragment


def test_blank_rows_and_empty_cells_are_skipped():
    chunker = TableChunker(max_tokens=350)

    chunks = chunker.split("name,role\n\nAyse,\n,admin\n")

    text = chunks[0].text
    assert "name: Ayse" in text
    assert "role: admin" in text
    assert "role: \n" not in text  # empty cell not serialized


def test_empty_table_yields_no_chunks():
    chunker = TableChunker(max_tokens=350)

    assert chunker.split("") == []
    assert chunker.split("name,role\n") == []  # header only, no data rows
