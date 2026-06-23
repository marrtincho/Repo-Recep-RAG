#!/usr/bin/env python3
"""
Batería de evaluación de retrieval.

Lee los casos de prueba de eval/retrieval_cases.csv y verifica que, para
cada pregunta, el documento esperado aparece entre los top-N resultados del
retrieval. Informe al final con tasa de acierto, casos que fallan, y las
similitudes exactas para diagnosticar.

Uso:
    python scripts/eval_retrieval.py                    # top-1 (más estricto)
    python scripts/eval_retrieval.py --top 3            # el documento esperado
                                                         # puede estar en posición 1, 2 o 3
    python scripts/eval_retrieval.py --verbose          # muestra todos los casos, no solo fallos
    python scripts/eval_retrieval.py --cases eval/retrieval_cases.csv  # fichero alternativo

Por qué top-1 por defecto: si el documento esperado no es el primero, el
modelo recibe el contexto equivocado en primera posición, que es exactamente
lo que produjo los fallos del log. top-3 es útil para detectar si un doc
está "cerca" pero desplazado, y decidir si vale la pena investigar.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_settings
from src.embeddings.indexer import get_collection
from src.embeddings.ollama_client import OllamaEmbeddingClient
from src.retrieval.pipeline import retrieve

# ── colores ANSI (se desactivan si la salida no es una terminal) ──────────────
_IS_TTY = sys.stdout.isatty()
GREEN = "\033[32m" if _IS_TTY else ""
RED   = "\033[31m" if _IS_TTY else ""
YELLOW= "\033[33m" if _IS_TTY else ""
DIM   = "\033[2m"  if _IS_TTY else ""
RESET = "\033[0m"  if _IS_TTY else ""


def _load_cases(path: Path) -> list[tuple[str, str, str]]:
    """
    Lee el CSV de casos de prueba.

    Formato: pregunta,documento_esperado,nota
    Líneas que empiezan por # se ignoran (son secciones/comentarios).
    """
    cases = []
    with path.open(encoding="utf-8") as f:
        for i, raw in enumerate(f):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line == "pregunta,documento_esperado,nota":
                continue  # cabecera exacta del CSV
            parts = line.split(",", 2)
            if len(parts) < 2:
                continue
            pregunta = parts[0].strip()
            doc_esperado = parts[1].strip()
            nota = parts[2].strip() if len(parts) > 2 else ""
            if pregunta and doc_esperado:
                cases.append((pregunta, doc_esperado, nota))
    return cases


def _doc_name(path_str: str) -> str:
    return Path(path_str).name if path_str else "?"


def run_eval(cases_path: Path, top_n: int, verbose: bool) -> int:
    """
    Ejecuta la batería y devuelve el número de fallos (0 = todo correcto).
    """
    settings = load_settings()
    embedding_client = OllamaEmbeddingClient(
        model=settings.embedding_model, host=settings.ollama_host
    )
    collection = get_collection(settings.chroma_db_path)
    total_chunks = collection.count()

    cases = _load_cases(cases_path)
    if not cases:
        print(f"{YELLOW}No se encontraron casos en {cases_path}{RESET}")
        return 1

    print(f"\nEvaluación de retrieval · {len(cases)} casos · top-{top_n} · {total_chunks} chunks en índice")
    print(f"Modelo de embeddings: {settings.embedding_model} · umbral confianza: {settings.confidence_threshold}")
    print("─" * 72)

    passed = failed = below_threshold = 0
    failure_details: list[dict] = []

    for pregunta, doc_esperado, nota in cases:
        decision = retrieve(pregunta, settings, embedding_client, collection)

        # Nombres de documento de los top-N resultados
        top_docs = [_doc_name(r.metadata.get("source_path", "")) for r in decision.results[:top_n]]
        similarities = [r.similarity for r in decision.results[:top_n]]

        ok = doc_esperado in top_docs

        if not decision.should_answer:
            below_threshold += 1
            status = f"{YELLOW}UMBRAL{RESET}"
            ok = False
        elif ok:
            passed += 1
            status = f"{GREEN}OK{RESET}"
        else:
            failed += 1
            status = f"{RED}FALLO{RESET}"

        if verbose or not ok:
            sim_str = ", ".join(f"{s:.3f}" for s in similarities)
            print(f"{status}  [{decision.confidence:.3f}]  {pregunta}")
            if not ok:
                top_str = " | ".join(f"{d} ({s:.3f})" for d, s in zip(top_docs, similarities))
                print(f"       esperado: {GREEN}{doc_esperado}{RESET}")
                print(f"       obtenido: {RED}{top_str}{RESET}")
                if nota:
                    print(f"       nota:     {DIM}{nota}{RESET}")
            else:
                pos = top_docs.index(doc_esperado) + 1
                print(f"       {DIM}{doc_esperado} en posición {pos}  ({sim_str}){RESET}")

    total = len(cases)
    print("─" * 72)
    print(f"\nResultado:  {GREEN}{passed} OK{RESET}  {RED}{failed} FALLOS{RESET}  {YELLOW}{below_threshold} bajo umbral{RESET}  de {total} casos")

    if below_threshold > 0:
        print(
            f"\n{YELLOW}Nota: {below_threshold} pregunta(s) no superaron el umbral de confianza "
            f"({settings.confidence_threshold}). El sistema las escalaría aunque el documento "
            f"exista. Considera bajar el umbral si son preguntas legítimas.{RESET}"
        )

    if failed == 0 and below_threshold == 0:
        print(f"\n{GREEN}✓ Todos los casos recuperan el documento esperado.{RESET}")
    elif failed > 0:
        print(
            f"\n{RED}✗ {failed} caso(s) recuperaron el documento equivocado.{RESET} "
            "Revisa los fallos arriba — suelen indicar un documento 'imán' que roba "
            "el retrieval, vocabulario desalineado, o un chunk_size que parte una entrada relevante."
        )

    return failed + below_threshold


def main() -> None:
    parser = argparse.ArgumentParser(description="Batería de evaluación de retrieval del RAG de recepción.")
    parser.add_argument(
        "--top", type=int, default=1,
        help="El documento esperado debe estar entre los top-N resultados (default: 1).",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Mostrar todos los casos, no solo los que fallan.",
    )
    parser.add_argument(
        "--cases", type=Path,
        default=Path(__file__).resolve().parent.parent / "eval" / "retrieval_cases.csv",
        help="Ruta al CSV de casos de prueba.",
    )
    args = parser.parse_args()

    if not args.cases.exists():
        print(f"{RED}No se encontró el fichero de casos: {args.cases}{RESET}")
        sys.exit(1)

    failures = run_eval(cases_path=args.cases, top_n=args.top, verbose=args.verbose)
    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()