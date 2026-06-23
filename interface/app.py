"""
Interfaz Streamlit del asistente de recepción.

Dos pestañas: "Consultas" (el chat, con toggle de modo y feedback 👍/👎) y
"Métricas" (panel de impacto para la presentación a dirección).

Punto de entrada único hacia el backend: src.orchestration.pipeline.ask /
submit_feedback. Esta capa no conoce los detalles de retrieval, embeddings
ni generación — solo orquesta la UI.

Ejecutar con:  streamlit run interface/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Permitir importar el paquete src/ cuando Streamlit ejecuta este archivo directamente.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_settings  # noqa: E402
from src.embeddings.indexer import get_collection  # noqa: E402
from src.embeddings.ollama_client import OllamaEmbeddingClient  # noqa: E402
from src.generation.ollama_generator import OllamaGenerationClient  # noqa: E402
from src.orchestration.metrics import (  # noqa: E402
    FEEDBACK_CORRECTO,
    FEEDBACK_INCORRECTO,
    GAP_LOG_COLUMNS,
    compute_summary_metrics,
)
from src.orchestration.pipeline import ask, submit_feedback  # noqa: E402

MODE_LABELS = {"directo": "Directo — solo la acción", "explicado": "Explicado — con el porqué"}

# Costura de inyección de dependencias para tests con AppTest.
#
# AppTest.from_file() ejecuta este script en un namespace propio y aislado en
# cada `.run()`: no reutiliza el módulo ya importado en el proceso de test,
# así que `unittest.mock.patch("interface.app.X")` no llega a afectar lo que
# AppTest realmente ejecuta. session_state sí es compartido (AppTest lo
# soporta explícitamente para esto), así que es el punto de inyección que
# usan los tests en tests/test_app.py para sustituir collection/ask/
# submit_feedback sin tocar Ollama ni ChromaDB reales.
_UNSET = object()


def _resolve_collection(settings):
    override = st.session_state.get("_test_collection_override", _UNSET)
    if override is not _UNSET:
        return override
    return _load_collection(str(settings.chroma_db_path))


def _resolve_settings():
    override = st.session_state.get("_test_settings_override", _UNSET)
    if override is not _UNSET:
        return override
    return _load_settings()


def _resolve_ask():
    return st.session_state.get("_test_ask_override", ask)


def _resolve_submit_feedback():
    return st.session_state.get("_test_submit_feedback_override", submit_feedback)


@st.cache_resource
def _load_settings():
    return load_settings()


@st.cache_resource
def _load_collection(chroma_db_path_str: str):
    """Cachea la colección de ChromaDB. Devuelve None si todavía no existe un índice utilizable."""
    settings = _load_settings()
    try:
        collection = get_collection(settings.chroma_db_path)
        if collection.count() == 0:
            return None
        return collection
    except Exception:
        return None


@st.cache_resource
def _load_embedding_client():
    settings = _load_settings()
    return OllamaEmbeddingClient(model=settings.embedding_model, host=settings.ollama_host)


@st.cache_resource
def _load_generation_client():
    settings = _load_settings()
    return OllamaGenerationClient(
        model=settings.generation_model,
        host=settings.ollama_host,
        temperature=settings.temperature,
        max_tokens=settings.max_tokens,
    )


def _init_state() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []  # lista de dicts: role, content, sources?, interaction_id?, escalated?, is_clarification?, feedback?


def _render_index_missing_notice() -> None:
    st.warning(
        "Todavía no hay documentación indexada. Para empezar, añade documentos en `docs/` "
        "y ejecuta `python scripts/reindex.py` desde la raíz del proyecto. Luego recarga esta página."
    )


def _record_feedback(index: int, value: str) -> None:
    """Callback de los botones de feedback: registra y marca el mensaje para no volver a preguntar."""
    settings = _resolve_settings()
    message = st.session_state.messages[index]
    try:
        _resolve_submit_feedback()(message["interaction_id"], value, settings)
        message["feedback"] = value
    except ValueError as exc:
        st.session_state.feedback_error = str(exc)


def _render_message(message: dict, index: int) -> None:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

        if message["role"] != "assistant":
            return

        if message.get("sources"):
            st.caption("Fuentes: " + ", ".join(message["sources"]))

        # Sin feedback para respuestas escaladas o preguntas de aclaración:
        # no hay nada que evaluar como correcto/incorrecto todavía.
        if message.get("escalated") or message.get("is_clarification"):
            return

        existing = message.get("feedback")
        if existing == FEEDBACK_CORRECTO:
            st.caption("Marcado como útil. Gracias.")
        elif existing == FEEDBACK_INCORRECTO:
            st.caption("Marcado como incorrecto. Se registrará para revisar la documentación.")
        else:
            col_yes, col_no, _ = st.columns([1, 1, 6])
            col_yes.button("👍 Útil", key=f"fb_yes_{index}", on_click=_record_feedback, args=(index, FEEDBACK_CORRECTO))
            col_no.button("👎 No me sirve", key=f"fb_no_{index}", on_click=_record_feedback, args=(index, FEEDBACK_INCORRECTO))


def _render_chat_tab(collection) -> None:
    if collection is None:
        _render_index_missing_notice()
        return

    settings = _resolve_settings()

    if "feedback_error" in st.session_state:
        st.error(st.session_state.pop("feedback_error"))

    mode_keys = list(MODE_LABELS.keys())
    default_index = mode_keys.index(settings.mode_default) if settings.mode_default in mode_keys else 0
    mode_key = st.radio(
        "Modo de respuesta",
        options=mode_keys,
        format_func=lambda k: MODE_LABELS[k],
        index=default_index,
        horizontal=True,
    )

    for index, message in enumerate(st.session_state.messages):
        _render_message(message, index)

    prompt = st.chat_input("Escribe tu consulta operativa…")
    if not prompt:
        return

    # Historial previo a este turno (todo lo ya mostrado, antes de añadir el mensaje actual),
    # usado tanto para enriquecer la búsqueda como para que el modelo entienda seguimientos (ADR 0010).
    history = [(m["role"], m["content"]) for m in st.session_state.messages]

    st.session_state.messages.append({"role": "user", "content": prompt})

    embedding_client = _load_embedding_client()
    generation_client = _load_generation_client()

    try:
        with st.spinner("Buscando en la documentación…"):
            result = _resolve_ask()(
                prompt, mode_key, settings, embedding_client, collection, generation_client, history=history
            )
    except Exception as exc:  # noqa: BLE001 — la UI debe degradar con gracia ante cualquier fallo del backend
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": (
                    "No he podido procesar la consulta. Comprueba que Ollama esté en marcha "
                    f"y vuelve a intentarlo.\n\nDetalle técnico: {exc}"
                ),
                "escalated": True,
            }
        )
        st.rerun()
        return

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": result.text,
            "sources": result.sources,
            "interaction_id": result.interaction_id,
            "escalated": result.was_escalated,
            "is_clarification": result.is_clarification,
        }
    )
    st.rerun()


def _render_metrics_tab() -> None:
    settings = _resolve_settings()
    metrics = compute_summary_metrics(settings.feedback_log_path)

    st.subheader("Impacto acumulado")
    if metrics["total_interacciones"] == 0:
        st.info("Aún no hay consultas registradas. Las métricas aparecerán aquí en cuanto empieces a usar el asistente.")
        return

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Consultas totales", metrics["total_interacciones"])
    col2.metric("Tasa de respuesta", f"{metrics['tasa_respuesta'] * 100:.0f}%")
    col3.metric("Tasa de escalado", f"{metrics['tasa_escalado'] * 100:.0f}%")
    col4.metric("Tasa de acierto", f"{metrics['tasa_acierto'] * 100:.0f}%")
    st.caption(
        "La tasa de acierto se calcula solo sobre las respuestas que alguien ha valorado con 👍/👎. "
        "El resto cuentan como aún sin evaluar."
    )

    _render_gap_log(settings.gap_log_path)


def _render_gap_log(gap_log_path: Path) -> None:
    st.subheader("Huecos de documentación detectados")
    if not gap_log_path.exists():
        st.success("Ninguna consulta ha tenido que escalarse todavía. No hay huecos de documentación detectados.")
        return

    gap_df = pd.read_csv(gap_log_path, dtype=str, keep_default_na=False)
    if gap_df.empty:
        st.success("Ninguna consulta ha tenido que escalarse todavía.")
        return

    st.caption(
        "Cada fila es una consulta que el asistente no pudo responder con confianza. "
        "Son candidatas directas a nueva documentación."
    )

    # Evolución semanal: cuántos huecos por semana ISO.
    timestamps = pd.to_datetime(gap_df["timestamp"], errors="coerce", utc=True)
    weekly = timestamps.dt.strftime("%Y-S%V").value_counts().sort_index()
    if not weekly.empty:
        st.bar_chart(weekly, x_label="Semana", y_label="Huecos detectados")

    st.dataframe(
        gap_df[GAP_LOG_COLUMNS].rename(
            columns={
                "timestamp": "Fecha",
                "pregunta": "Consulta",
                "modo": "Modo",
                "confianza_mejor_resultado": "Confianza máx.",
            }
        ),
        width="stretch",
        hide_index=True,
    )


def main() -> None:
    st.set_page_config(page_title="Asistente de recepción", page_icon="🛎️", layout="centered")
    _init_state()

    st.title("🛎️ Asistente de recepción")
    st.caption("Consulta procedimientos, contactos y ubicaciones a partir de la documentación interna del hotel.")

    settings = _resolve_settings()
    collection = _resolve_collection(settings)

    chat_tab, metrics_tab = st.tabs(["Consultas", "Métricas"])
    with chat_tab:
        _render_chat_tab(collection)
    with metrics_tab:
        _render_metrics_tab()


if __name__ == "__main__":
    main()
