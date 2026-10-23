"""Local TF-IDF over a server-bound policy revision; never a global company search."""
from collections import Counter
from functools import lru_cache
import hashlib
import math
import re
from unlockops.common.phase2 import PolicyEvidence
from unlockops.common.models import ToolFailure
from .search import features, cosine


class RevisionIndex:
    def __init__(self, company_id, policy_id, revision, doc_id, source_hash, content):
        if hashlib.sha256(content.encode("utf-8")).hexdigest() != source_hash:
            raise ToolFailure("POLICY_SOURCE_UNAVAILABLE", "Policy content/hash mismatch")
        self.source_hash = source_hash
        self.evidence = []
        for segment in re.split(r"(?m)(?=^## )", content):
            if not segment.startswith("## "):
                continue
            heading = segment.splitlines()[0][3:].strip()
            self.evidence.append(PolicyEvidence(doc_id=doc_id, article=heading,
                version=str(revision), source_hash=source_hash, text=segment.strip()))
        if not self.evidence:
            raise ToolFailure("POLICY_SOURCE_UNAVAILABLE", "Policy has no readable articles")
        counts = [features(e.text) for e in self.evidence]
        frequency = Counter(t for count in counts for t in count)
        self.idf = {t: math.log((1 + len(counts)) / (1 + n)) + 1 for t, n in frequency.items()}
        self.vectors = [self.vector(count) for count in counts]

    def vector(self, count):
        return {t: (1 + math.log(n)) * self.idf.get(t, 0) for t, n in count.items()}

    def search(self, query, limit):
        vector = self.vector(features(query))
        ranked = sorted(enumerate(self.evidence), key=lambda item: (-cosine(vector, self.vectors[item[0]]), item[0]))
        return [e.model_dump(mode="json") for i, e in ranked[:limit] if cosine(vector, self.vectors[i]) > 0]

    def read(self, article=""):
        selected = [e.model_dump(mode="json") for e in self.evidence if not article or e.article == article]
        if not selected:
            raise ToolFailure("POLICY_SOURCE_UNAVAILABLE", "Requested article is unavailable")
        return selected


@lru_cache(maxsize=32)
def revision_index(company_id, policy_id, revision, doc_id, source_hash, content):
    # Both tenant and revision/hash participate in cache identity. No fact/permission cache.
    return RevisionIndex(company_id, policy_id, revision, doc_id, source_hash, content)
