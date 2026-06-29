"""
Caché semántico de respuestas validadas.

Almacena pares (embedding_de_consulta, respuesta) validados con 👍. Cuando llega
una consulta con alta similitud coseno a una entrada activa, la respuesta se sirve
directamente sin llamar a retrieve() ni al LLM generador — la operación más cara
en hardware de baja potencia.

Ciclo de vida de una entrada:
  - Se crea como tentativa (active=False) con cada respuesta fresca del pipeline.
  - 👍  → active=True (se sirve en futuras consultas similares).
  - 👎  → negative_votes += 1; si negatives >= positives → active=False.
  Solo sobreviven en el caché las respuestas consistentemente validadas.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

# Similitud mínima para considerar que dos preguntas son la misma a efectos de
# fusión (evita crear entradas duplicadas para variantes casi idénticas).
_MERGE_THRESHOLD = 0.95


def _cosine(a: list[float], b: list[float]) -> float:
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    return float(np.dot(va, vb) / denom) if denom > 0 else 0.0


def load_cache(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_cache(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def lookup(
    query_embedding: list[float],
    mode: str,
    path: Path,
    threshold: float,
) -> dict | None:
    """
    Devuelve la entrada activa más similar a `query_embedding` si supera `threshold`.

    En empate de similitud prefiere la entrada con mayor ratio de aciertos
    (positive_votes / total_votes) — así las respuestas más consistentemente
    validadas tienen preferencia sobre las que solo recibieron un 👍.
    """
    entries = load_cache(path)
    best: dict | None = None
    best_sim = -1.0
    best_ratio = -1.0

    for entry in entries:
        if not entry.get("active") or entry.get("mode") != mode:
            continue
        sim = _cosine(query_embedding, entry["query_embedding"])
        if sim < threshold:
            continue
        total = entry["positive_votes"] + entry["negative_votes"]
        ratio = entry["positive_votes"] / total if total > 0 else 0.0
        if sim > best_sim or (sim == best_sim and ratio > best_ratio):
            best = entry
            best_sim = sim
            best_ratio = ratio

    return best


def add_tentative(
    query_text: str,
    query_embedding: list[float],
    answer: str,
    sources: list[str],
    mode: str,
    path: Path,
) -> str:
    """
    Crea una entrada tentativa (active=False) para una respuesta recién generada.

    Si ya existe una entrada activa con similitud >= _MERGE_THRESHOLD, devuelve
    su cache_id en vez de crear un duplicado — la misma pregunta reformulada
    refuerza la entrada existente en vez de fragmentar el caché.
    """
    entries = load_cache(path)
    now = datetime.now(timezone.utc).isoformat()

    for entry in entries:
        if entry.get("active") and entry.get("mode") == mode:
            if _cosine(query_embedding, entry["query_embedding"]) >= _MERGE_THRESHOLD:
                return entry["cache_id"]

    cache_id = str(uuid.uuid4())
    entries.append({
        "cache_id": cache_id,
        "query_text": query_text,
        "query_embedding": [float(x) for x in query_embedding],
        "answer": answer,
        "sources": sources,
        "mode": mode,
        "positive_votes": 0,
        "negative_votes": 0,
        "active": False,
        "created_at": now,
        "updated_at": now,
    })
    save_cache(path, entries)
    return cache_id


def record_cache_positive(cache_id: str, path: Path) -> None:
    """Activa la entrada e incrementa positive_votes."""
    entries = load_cache(path)
    now = datetime.now(timezone.utc).isoformat()
    for entry in entries:
        if entry["cache_id"] == cache_id:
            entry["positive_votes"] += 1
            entry["active"] = True
            entry["updated_at"] = now
            break
    save_cache(path, entries)


def record_cache_negative(cache_id: str, path: Path) -> None:
    """Incrementa negative_votes y desactiva la entrada si los negativos igualan o superan los positivos."""
    entries = load_cache(path)
    now = datetime.now(timezone.utc).isoformat()
    for entry in entries:
        if entry["cache_id"] == cache_id:
            entry["negative_votes"] += 1
            if entry["negative_votes"] >= entry["positive_votes"]:
                entry["active"] = False
            entry["updated_at"] = now
            break
    save_cache(path, entries)
