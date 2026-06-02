import re
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.rag.models import ChunkDraft


@dataclass(frozen=True)
class _SectionBlock:
    text: str
    heading_path: list[str]
    section_index: int

    @property
    def section_title(self) -> str | None:
        return self.heading_path[-1] if self.heading_path else None


class HeadingAwareChunker:
    def __init__(self, max_tokens: int, overlap_tokens: int) -> None:
        if max_tokens < 20:
            raise ValueError("max_tokens must be at least 20")
        if overlap_tokens < 0 or overlap_tokens >= max_tokens:
            raise ValueError("overlap_tokens must be non-negative and smaller than max_tokens")

        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens

    def split(self, content: str) -> list[ChunkDraft]:
        normalized = content.strip()
        if not normalized:
            return []

        chunks: list[ChunkDraft] = []
        for block in self._section_blocks(normalized):
            for text in self._split_text(block):
                chunks.append(
                    ChunkDraft(
                        text=text,
                        heading_path=block.heading_path,
                        chunk_index=len(chunks),
                        chunk_token_count=self.count_tokens(text),
                        section_title=block.section_title,
                        section_index=block.section_index,
                    )
                )

        return chunks

    def _section_blocks(self, content: str) -> list[_SectionBlock]:
        blocks: list[_SectionBlock] = []
        current_lines: list[str] = []
        heading_stack: list[str] = []
        current_path: list[str] = []
        section_index = 0

        for raw_line in content.splitlines():
            line = raw_line.rstrip()
            heading = self._parse_markdown_heading(line)

            if heading is not None:
                if current_lines:
                    blocks.append(
                        _SectionBlock(
                            text="\n".join(current_lines).strip(),
                            heading_path=current_path.copy(),
                            section_index=section_index,
                        )
                    )
                    current_lines = []
                    section_index += 1

                level, title = heading
                heading_stack = heading_stack[: level - 1]
                heading_stack.append(title)
                current_path = heading_stack.copy()
                continue

            current_lines.append(line)

        if current_lines or current_path:
            blocks.append(
                _SectionBlock(
                    text="\n".join(current_lines).strip(),
                    heading_path=current_path.copy(),
                    section_index=section_index,
                )
            )

        return [block for block in blocks if block.text or block.heading_path]

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

    def _split_text(self, block: _SectionBlock) -> list[str]:
        prefix = self._heading_prefix(block.heading_path)
        prefix_tokens = self.count_tokens(prefix)
        body = block.text.strip()

        if not body:
            return [prefix] if prefix else []

        budget = max(1, self.max_tokens - prefix_tokens)
        overlap = min(self.overlap_tokens, max(0, budget - 1))
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=budget,
            chunk_overlap=overlap,
            length_function=self.count_tokens,
            separators=["\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " ", ""],
            keep_separator=False,
        )

        pieces = [piece.strip() for piece in splitter.split_text(body) if piece.strip()]
        return [self._with_heading_prefix(prefix, piece) for piece in pieces]

    @staticmethod
    def _heading_prefix(heading_path: list[str]) -> str:
        return " > ".join(heading_path).strip()

    @staticmethod
    def _with_heading_prefix(prefix: str, text: str) -> str:
        if not prefix:
            return text
        if text.startswith(prefix):
            return text
        return f"{prefix}\n\n{text}"

    @staticmethod
    def count_tokens(text: str) -> int:
        return len(re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE))
