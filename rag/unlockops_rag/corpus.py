"""Parse supplied policy bundles without confusing nested summary headings with documents."""
from dataclasses import dataclass
import re

from unlockops.common.phase2 import Platform


DOCUMENT = re.compile(r"(?m)^## [^\n]*?\b((?:POL-\d+)|(?:[A-Z]{2}-OFF-\d+))\s*$")


@dataclass(frozen=True)
class CorpusDocument:
    doc_id: str
    title: str
    platform: str
    version: str
    chunks: tuple[tuple[str, str], ...]


def parse_corpus(text: str) -> list[CorpusDocument]:
    parts = DOCUMENT.split(text)
    documents = []
    seen = set()
    for offset in range(1, len(parts), 2):
        doc_id, body = parts[offset:offset + 2]
        if doc_id in seen:
            raise ValueError(f"Duplicate document: {doc_id}")
        seen.add(doc_id)
        rows = list(re.finditer(r"(?m)^\|[^\n]+\|\s*$", body))
        metadata = next((row for row in rows if row.group().split('|')[1].strip().strip('*') == doc_id), None)
        if metadata is None:
            raise ValueError(f"Missing metadata: {doc_id}")
        cells = [cell.strip().strip('*').strip() for cell in metadata.group().strip().strip('|').split('|')]
        if len(cells) != 6:
            raise ValueError(f"Invalid metadata: {doc_id}")
        platform_match = re.search(r'`([A-Z_]+)`', cells[3])
        platform = platform_match[1] if platform_match else None
        if platform not in {'COMMON', *(item.value for item in Platform)}:
            raise ValueError(f"Unknown platform: {doc_id}")
        version = cells[4] if doc_id.startswith('POL-') else cells[5]
        content = body[metadata.end():].strip().removesuffix('---').strip()
        if doc_id.startswith('POL-'):
            chunks = []
            for paragraph in re.split(r'(?m)(?=^제\d+조)', content):
                if not paragraph.strip():
                    continue
                article = re.match(r'제\d+조(?:\([^\n)]*\))?', paragraph)
                if not article:
                    raise ValueError(f"Unrecognized article: {doc_id}")
                chunks.append((article[0], paragraph.strip()))
        else:
            chunks = []
            sections = re.split(r'(?m)^## ([^\n]+)\n', content)
            for i in range(1, len(sections), 2):
                chunks.append((sections[i].strip(), sections[i + 1].strip()))
        if not chunks or any(not value for _, value in chunks):
            raise ValueError(f"Empty document: {doc_id}")
        documents.append(CorpusDocument(doc_id, cells[1], platform, version, tuple(chunks)))
    if not documents:
        raise ValueError('No policy documents')
    return documents


def render_corpus(documents: list[CorpusDocument]) -> str:
    """Unique article labels preserve source ID/version while DB evidence binds the company revision."""
    return '\n\n'.join(
        f'## {doc.doc_id} | {doc.platform} | {doc.version} | {article}\n\n'
        f'문서: {doc.title}\n\n{body}'
        for doc in documents for article, body in doc.chunks
    ) + '\n'
