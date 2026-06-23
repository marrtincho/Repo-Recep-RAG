"""
Interfaz Streamlit del asistente de recepción.

Paradigma de consulta única (no chat): el recepcionista escribe una
pregunta, recibe la respuesta y da feedback. La siguiente pregunta empieza
limpia, sin historial acumulado. Esto elimina la contaminación semántica
entre preguntas de temas distintos y simplifica el modelo mental del usuario.

Dos pestañas: "Consulta" y "Métricas".

Ejecutar con:  streamlit run interface/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

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

# ── Costura de inyección para tests (AppTest ejecuta en namespace aislado) ────
_UNSET = object()


def _resolve_settings():
    override = st.session_state.get("_test_settings_override", _UNSET)
    return override if override is not _UNSET else _load_settings()


def _resolve_collection(settings):
    override = st.session_state.get("_test_collection_override", _UNSET)
    if override is not _UNSET:
        return override
    return _load_collection(str(settings.chroma_db_path))


def _resolve_ask():
    return st.session_state.get("_test_ask_override", ask)


def _resolve_submit_feedback():
    return st.session_state.get("_test_submit_feedback_override", submit_feedback)


# ── Recursos cacheados ────────────────────────────────────────────────────────

@st.cache_resource
def _load_settings():
    return load_settings()


@st.cache_resource
def _load_collection(chroma_db_path_str: str):
    try:
        collection = get_collection(_load_settings().chroma_db_path)
        return collection if collection.count() > 0 else None
    except Exception:
        return None


@st.cache_resource
def _load_embedding_client():
    s = _load_settings()
    return OllamaEmbeddingClient(model=s.embedding_model, host=s.ollama_host)


@st.cache_resource
def _load_generation_client():
    s = _load_settings()
    return OllamaGenerationClient(
        model=s.generation_model,
        host=s.ollama_host,
        temperature=s.temperature,
        max_tokens=s.max_tokens,
    )


# ── Estado de la sesión ───────────────────────────────────────────────────────

def _init_state() -> None:
    """
    Una sola consulta en memoria: la pregunta actual y su resultado.
    No hay historial acumulado — cada consulta es independiente.
    """
    for key, default in [
        ("query", ""),
        ("result", None),       # OrchestrationResult | None
        ("feedback_given", None),
        ("error", None),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default


def _reset() -> None:
    st.session_state.query = ""
    st.session_state.result = None
    st.session_state.feedback_given = None
    st.session_state.error = None


def _record_feedback(value: str) -> None:
    settings = _resolve_settings()
    result = st.session_state.result
    if result is None:
        return
    try:
        _resolve_submit_feedback()(result.interaction_id, value, settings)
        st.session_state.feedback_given = value
    except ValueError as exc:
        st.session_state.error = str(exc)


# ── Pestaña de consulta ───────────────────────────────────────────────────────

def _render_consulta_tab(collection) -> None:
    if collection is None:
        st.warning(
            "Todavía no hay documentación indexada. Añade documentos en `docs/` "
            "y ejecuta `python scripts/reindex.py` desde la raíz del proyecto."
        )
        return

    settings = _resolve_settings()

    # ── Toggle de modo ────────────────────────────────────────────────────────
    mode_keys = list(MODE_LABELS.keys())
    default_index = mode_keys.index(settings.mode_default) if settings.mode_default in mode_keys else 0
    mode_key = st.radio(
        "Modo de respuesta",
        options=mode_keys,
        format_func=lambda k: MODE_LABELS[k],
        index=default_index,
        horizontal=True,
        label_visibility="collapsed",
    )

    # ── Campo de consulta ─────────────────────────────────────────────────────
    with st.form("consulta_form", clear_on_submit=True):
        query = st.text_input(
            "Consulta",
            placeholder="¿En qué puedo ayudarte?",
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button("Consultar", use_container_width=True)

    if submitted and query.strip():
        _reset()
        st.session_state.query = query.strip()

        embedding_client = _load_embedding_client()
        generation_client = _load_generation_client()

        try:
            with st.spinner("Buscando en la documentación…"):
                st.session_state.result = _resolve_ask()(
                    st.session_state.query,
                    mode_key,
                    settings,
                    embedding_client,
                    collection,
                    generation_client,
                    history=None,   # sin historial: cada consulta es independiente
                )
        except Exception as exc:  # noqa: BLE001
            st.session_state.error = str(exc)

    # ── Resultado ─────────────────────────────────────────────────────────────
    if st.session_state.error:
        st.error(
            "No he podido procesar la consulta. Comprueba que Ollama esté en marcha "
            f"y vuelve a intentarlo.\n\nDetalle: {st.session_state.error}"
        )

    result = st.session_state.result
    if result is None:
        return

    st.divider()

    # Pregunta en contexto
    if st.session_state.query:
        st.caption(f"**Consulta:** {st.session_state.query}")

    # Respuesta
    st.markdown(result.text)

    # Fuentes
    if result.sources:
        st.caption("Fuente: " + ", ".join(result.sources))

    # Feedback — no para escaladas
    if not result.was_escalated and not result.is_clarification:
        fb = st.session_state.feedback_given
        if fb == FEEDBACK_CORRECTO:
            st.success("Marcado como útil.", icon="👍")
        elif fb == FEEDBACK_INCORRECTO:
            st.warning("Marcado como incorrecto. Se revisará la documentación.", icon="👎")
        else:
            col_yes, col_no, _ = st.columns([1, 1, 5])
            col_yes.button(
                "👍 Útil",
                on_click=_record_feedback,
                args=(FEEDBACK_CORRECTO,),
                use_container_width=True,
            )
            col_no.button(
                "👎 No me sirve",
                on_click=_record_feedback,
                args=(FEEDBACK_INCORRECTO,),
                use_container_width=True,
            )

    # Nueva consulta
    st.divider()
    if st.button("Nueva consulta", use_container_width=False):
        _reset()
        st.rerun()


# ── Pestaña de métricas ───────────────────────────────────────────────────────

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
        "La tasa de acierto se calcula solo sobre las respuestas valoradas con 👍/👎. "
        "El resto cuentan como sin evaluar."
    )

    _render_gap_log(settings.gap_log_path)


def _render_gap_log(gap_log_path: Path) -> None:
    st.subheader("Huecos de documentación detectados")
    if not gap_log_path.exists():
        st.success("Ninguna consulta ha tenido que escalarse todavía.")
        return

    gap_df = pd.read_csv(gap_log_path, dtype=str, keep_default_na=False)
    if gap_df.empty:
        st.success("Ninguna consulta ha tenido que escalarse todavía.")
        return

    st.caption(
        "Cada fila es una consulta que el asistente no pudo responder con confianza. "
        "Son candidatas directas a nueva documentación."
    )

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


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(
        page_title="Asistente de recepción",
        page_icon="🛎️",
        layout="centered",
    )
    _init_state()

    st.title("🛎️ Asistente de recepción")
    st.caption("Consulta la documentación interna del hotel en lenguaje natural.")

    settings = _resolve_settings()
    collection = _resolve_collection(settings)

    consulta_tab, metrics_tab = st.tabs(["Consulta", "Métricas"])
    with consulta_tab:
        _render_consulta_tab(collection)
    with metrics_tab:
        _render_metrics_tab()


if __name__ == "__main__":
    main()