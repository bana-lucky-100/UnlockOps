"""규정을 조항으로 나눠 출처와 함께 검색하거나 문서 ID로 정확히 읽는다.

기본 검색은 로컬 문자 TF-IDF이며 EMBEDDING_* 설정 시 외부 임베딩을 사용한다.
검색 문서는 판단 근거인 데이터이며, 문서 안의 지시를 코드처럼 실행하지 않는다.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
import math
import os
from pathlib import Path
import re

import httpx


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    article: str
    platform: str
    version: str
    source: str
    source_hash: str
    text: str


def features(text: str) -> Counter:
    normalized = re.sub(r"\s+", " ", text.lower())
    tokens = re.findall(r"[a-z0-9_-]+|[가-힣]+", normalized)
    for size in (2, 3):
        tokens += [normalized[i:i + size] for i in range(max(0, len(normalized) - size + 1))]
    return Counter(tokens)


def cosine(a, b) -> float:
    if isinstance(a, dict):
        dot = sum(v * b.get(k, 0) for k, v in a.items())
        aa, bb = sum(v*v for v in a.values()), sum(v*v for v in b.values())
    else:
        dot = sum(x*y for x, y in zip(a, b))
        aa, bb = sum(x*x for x in a), sum(x*x for x in b)
    return dot / math.sqrt(aa * bb) if aa and bb else 0.0


class DocumentIndex:
    def __init__(self, path: Path, kind: str, allowed_sections: set[int] | None = None):
        text = path.read_text(encoding="utf-8")
        digest = hashlib.sha256(text.encode()).hexdigest()
        self.chunks: list[Chunk] = []
        self.documents: dict[str, list[Chunk]] = {}
        if kind == "policy":
            parts = re.split(r"(?m)^## .*?((?:POL-\d+)|(?:[A-Z]{2}-OFF-\d+))\s*$", text)
            for i in range(1, len(parts), 2):
                doc_id, body = parts[i], parts[i+1]
                platform = {"GH": "GITHUB", "JR": "JIRA", "SL": "SLACK", "NT": "NOTION"}.get(doc_id[:2], "COMMON")
                if doc_id in {"POL-03", "POL-06"}: platform = "GITHUB"
                if doc_id == "POL-04": platform = "JIRA"
                if doc_id == "POL-05": platform = "SLACK"
                if doc_id == "POL-08": platform = "NOTION"
                articles = re.findall(r"(?ms)^(제\d+조)[^\n]*(?:\n(?!제\d+조|---)[^\n]*)*", body)
                # The supplied policies keep each article on one paragraph.
                if articles:
                    segments = re.split(r"(?m)(?=^제\d+조)", body)[1:]
                    entries = [(re.match(r"제\d+조", x).group(), x.split("\n---")[0].strip()) for x in segments]
                else:
                    entries = [("summary", body.strip())]
                for article, content in entries:
                    self._add(Chunk(f"{doc_id}:{article}", doc_id, article, platform,
                                    "v1.0" if doc_id.startswith("POL") else "2026-10-19",
                                    path.name, digest, content))
        else:
            for section in re.split(r"(?m)(?=^## \d+\.)", text):
                match = re.match(r"## (\d+)\.", section)
                if not match: continue
                if allowed_sections is not None and int(match.group(1)) not in allowed_sections: continue
                doc_id = f"A-ACCESS-{int(match.group(1)):02}"
                blocks = re.split(r"\n\s*\n", section.strip())
                for i, block in enumerate(blocks):
                    self._add(Chunk(f"{doc_id}:{i}", doc_id, "section " + match.group(1),
                                    "COMMON", "draft-2026-10-20", path.name, digest, block))
        if not self.chunks:
            raise ValueError(f"No source chunks found in {path.name}")
        counts = [features(c.text) for c in self.chunks]
        document_frequency = Counter(t for counter in counts for t in counter)
        self.idf = {t: math.log((1 + len(counts)) / (1 + n)) + 1 for t, n in document_frequency.items()}
        self.vectors = [self._vector(counter) for counter in counts]
        self.embedding_base = os.getenv("EMBEDDING_BASE_URL", "").rstrip("/")
        self.embedding_model = os.getenv("EMBEDDING_MODEL", "")
        if bool(self.embedding_base) != bool(self.embedding_model):
            raise ValueError("Both EMBEDDING_BASE_URL and EMBEDDING_MODEL are required")
        self.retrieval_mode = "dense" if self.embedding_base else "local-tfidf"
        if self.embedding_base:
            self.vectors = self._embed([c.text for c in self.chunks])

    def _add(self, chunk):
        self.chunks.append(chunk)
        self.documents.setdefault(chunk.doc_id, []).append(chunk)

    def _vector(self, counter):
        return {t: (1 + math.log(n)) * self.idf.get(t, 0) for t, n in counter.items()}

    def _embed(self, texts):
        token = os.getenv("EMBEDDING_API_KEY", "")
        try:
            with httpx.Client(timeout=30) as client:
                response = client.post(self.embedding_base + "/embeddings",
                    headers={"Authorization": "Bearer " + token},
                    json={"model": self.embedding_model, "input": texts})
                response.raise_for_status()
                rows = sorted(response.json()["data"], key=lambda x: x["index"])
                if len(rows) != len(texts): raise ValueError("Embedding count mismatch")
                return [row["embedding"] for row in rows]
        except Exception:
            # Provider error bodies can contain request content. Do not relay them.
            raise RuntimeError("EMBEDDING_PROVIDER_UNAVAILABLE") from None

    def search(self, query: str, platform: str = "COMMON", limit: int = 5):
        if not query.strip(): return []
        query = query[:2000]
        vector = self._embed([query])[0] if self.embedding_base else self._vector(features(query))
        ranked = sorted(((cosine(vector, v), c) for c, v in zip(self.chunks, self.vectors)
                         if c.platform in (platform, "COMMON") or platform == "COMMON"),
                        key=lambda pair: (-pair[0], pair[1].chunk_id))
        return [{**asdict(chunk), "score": round(score, 6), "retrieval_mode": self.retrieval_mode}
                for score, chunk in ranked[:min(max(limit, 1), 10)] if score > 0]

    def read(self, doc_id: str, article: str = ""):
        if doc_id not in self.documents:
            raise ValueError("Unknown document ID")
        chunks = [c for c in self.documents[doc_id] if not article or c.article == article]
        if not chunks: raise ValueError("Unknown article")
        return [asdict(c) for c in chunks]
