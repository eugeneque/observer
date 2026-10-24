from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader


@dataclass
class AIResult:
    text: str
    ai_name: str
    model: str


class AIProvider:
    name: str = ""
    model: str = ""

    async def analyze(self, system: str, user: str, files: list[Path]) -> AIResult:
        raise NotImplementedError


def pdf_to_text(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def files_as_text(files: list[Path]) -> str:
    return "\n\n".join(f'<file name="{f.name}">\n{pdf_to_text(f)}\n</file>' for f in files)
