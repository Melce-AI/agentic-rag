from dataclasses import dataclass

from src.rag.models import ChunkDraft


@dataclass(frozen=True)
class _SectionBlock:
    text: str
    heading_path: list[str]


class HeadingAwareChunker:
    def __init__(self, max_chars: int, overlap_chars: int) -> None:
        if max_chars < 100:
            raise ValueError("max_chars must be at least 100")
        if overlap_chars < 0 or overlap_chars >= max_chars:
            raise ValueError("overlap_chars must be non-negative and smaller than max_chars")

        self.max_chars = max_chars
        self.overlap_chars = overlap_chars

    def split(self, content: str) -> list[ChunkDraft]:
        normalized = content.strip()
        if not normalized:
            return []

        chunks: list[ChunkDraft] = []
        for block in self._section_blocks(normalized):
            for text in self._split_text(block.text):
                chunks.append(
                    ChunkDraft(
                        text=text,
                        heading_path=block.heading_path,
                        chunk_index=len(chunks),
                    )
                )

        return chunks

    def _section_blocks(self, content: str) -> list[_SectionBlock]:
        blocks: list[_SectionBlock] = []
        current_lines: list[str] = []
        heading_stack: list[str] = []
        current_path: list[str] = []

        for raw_line in content.splitlines():
            line = raw_line.rstrip()
            heading = self._parse_markdown_heading(line)

            if heading is not None:
                if current_lines:
                    blocks.append(
                        _SectionBlock(
                            text="\n".join(current_lines).strip(),
                            heading_path=current_path.copy(),
                        )
                    )
                    current_lines = []

                level, title = heading
                heading_stack = heading_stack[: level - 1]
                heading_stack.append(title)
                current_path = heading_stack.copy()
                current_lines.append(title)
                continue

            current_lines.append(line)

        if current_lines:
            blocks.append(
                _SectionBlock(
                    text="\n".join(current_lines).strip(),
                    heading_path=current_path.copy(),
                )
            )

        return [block for block in blocks if block.text]

    @staticmethod
    def _parse_markdown_heading(line: str) -> tuple[int, str] | None:
        stripped = line.lstrip()
        if not stripped.startswith("#"):
            return None

        marker = stripped.split(" ", 1)[0]
        if not marker or any(char != "#" for char in marker):
            return None
        if len(marker) > 6 or len(stripped) == len(marker):
            return None

        title = stripped[len(marker) :].strip()
        return (len(marker), title) if title else None

# TODO - chunk max_chars a göre değil de token aware chunking e geçilmeli.
    def _split_text(self, text: str) -> list[str]:
        if len(text) <= self.max_chars:
            return [text]

        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = min(start + self.max_chars, len(text))
            if end < len(text):
                boundary = self._find_boundary(text, start, end)
                if boundary > start:
                    end = boundary

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            if end >= len(text):
                break

            start = max(end - self.overlap_chars, start + 1)

        return chunks

    @staticmethod
    def _find_boundary(text: str, start: int, end: int) -> int:
        paragraph = text.rfind("\n\n", start, end)
        if paragraph > start:
            return paragraph

        newline = text.rfind("\n", start, end)
        if newline > start:
            return newline

        space = text.rfind(" ", start, end)
        if space > start:
            return space

        return end
