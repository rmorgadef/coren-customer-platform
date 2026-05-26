"""Vector store en memoria para la maqueta.

Equivalente conceptual a Qdrant en Coren. Para producción se sustituye este
módulo por un cliente Qdrant manteniendo la misma interfaz pública
(`retrieve(query, k) -> list[Doc]`).

Implementación: BM25 sobre tokens normalizados (sin embeddings ni red).
Más que suficiente para una KB de < 100 docs como la de RAI. Evita pagar
embeddings a la API en cada turno de conversación.
"""

import math
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml


DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


@dataclass
class Doc:
    id: str
    title: str
    tags: list[str]
    body: str
    score: float = 0.0


def _normalize(text) -> str:
    text = str(text)
    nfkd = unicodedata.normalize("NFKD", text)
    no_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    return no_accents.lower()


_TOKEN_RE = re.compile(r"[a-z0-9]{2,}")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(_normalize(text))


@lru_cache(maxsize=1)
def _load_corpus() -> list[Doc]:
    raw = yaml.safe_load((DATA_DIR / "knowledge.yaml").read_text(encoding="utf-8"))
    return [
        Doc(
            id=d["id"],
            title=d["title"],
            tags=d.get("tags", []),
            body=d["body"],
        )
        for d in raw.get("docs", [])
    ]


@lru_cache(maxsize=1)
def _doc_tokens() -> list[list[str]]:
    return [
        _tokenize(d.title) + _tokenize(d.body) + [_normalize(t) for t in d.tags]
        for d in _load_corpus()
    ]


@lru_cache(maxsize=1)
def _avg_doc_length() -> float:
    lens = [len(t) for t in _doc_tokens()]
    return sum(lens) / len(lens) if lens else 0.0


@lru_cache(maxsize=1)
def _document_frequencies() -> dict[str, int]:
    df: dict[str, int] = {}
    for tokens in _doc_tokens():
        for token in set(tokens):
            df[token] = df.get(token, 0) + 1
    return df


def _bm25_score(query_tokens: list[str], doc_tokens: list[str], k1: float = 1.5, b: float = 0.75) -> float:
    if not doc_tokens:
        return 0.0
    n = len(_load_corpus())
    df = _document_frequencies()
    avg_len = _avg_doc_length()
    doc_len = len(doc_tokens)
    score = 0.0
    tf_table: dict[str, int] = {}
    for t in doc_tokens:
        tf_table[t] = tf_table.get(t, 0) + 1
    for q in query_tokens:
        if q not in tf_table:
            continue
        idf = math.log((n - df.get(q, 0) + 0.5) / (df.get(q, 0) + 0.5) + 1)
        tf = tf_table[q]
        norm = tf * (k1 + 1) / (tf + k1 * (1 - b + b * doc_len / avg_len))
        score += idf * norm
    return score


def retrieve(query: str, k: int = 3, min_score: float = 0.5) -> list[Doc]:
    """Devuelve los top-k docs más relevantes para la query. Excluye los
    que no alcanzan `min_score` para no inyectar contexto irrelevante."""
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []
    corpus = _load_corpus()
    doc_tokens = _doc_tokens()
    scored: list[Doc] = []
    for doc, tokens in zip(corpus, doc_tokens):
        s = _bm25_score(query_tokens, tokens)
        if s >= min_score:
            scored.append(Doc(id=doc.id, title=doc.title, tags=doc.tags, body=doc.body, score=s))
    scored.sort(key=lambda d: d.score, reverse=True)
    return scored[:k]
