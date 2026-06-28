"""
Interfaz Streamlit del asistente de recepción.

Paradigma de consulta única (no chat): campo de texto, respuesta, feedback.
Cada consulta es independiente — sin historial acumulado.

Ejecutar con:  streamlit run interface/app.py
"""

from __future__ import annotations

import base64
import html
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import configure_logging, load_settings  # noqa: E402
from src.embeddings.indexer import get_collection, index_documents  # noqa: E402
from src.embeddings.ollama_client import OllamaEmbeddingClient  # noqa: E402
from src.generation.ollama_generator import OllamaGenerationClient  # noqa: E402
from src.orchestration.metrics import (  # noqa: E402
    FEEDBACK_CORRECTO,
    FEEDBACK_INCORRECTO,
    GAP_LOG_COLUMNS,
    compute_summary_metrics,
    get_frequent_questions,
)
from src.orchestration.pipeline import ask, submit_feedback  # noqa: E402

MODE_LABELS = {"directo": "Directo — solo la acción", "explicado": "Explicado — con el porqué"}

_UNSET = object()


# ── Costura de inyección para tests ──────────────────────────────────────────

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
        collection = get_collection(Path(chroma_db_path_str))
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


@st.cache_data(ttl=300)
def _get_frequent_questions(feedback_log_path_str: str, top_n: int = 5) -> list[str]:
    return get_frequent_questions(Path(feedback_log_path_str), top_n=top_n, min_count=2)


@st.cache_data
def _get_logo_b64() -> str | None:
    logo_path = Path(__file__).parent / "logo.png"
    if not logo_path.exists():
        return None
    return base64.b64encode(logo_path.read_bytes()).decode()


# ── Estilos ───────────────────────────────────────────────────────────────────

def _inject_css() -> None:
    st.markdown("""
    <style>
    /* Ocultar chrome genérico de Streamlit */
    #MainMenu, footer, header { visibility: hidden; }
    .stDeployButton { display: none; }

    html, body, [class*="css"] {
        font-family: 'Inter', 'Helvetica Neue', Arial, sans-serif;
    }

    /* Header */
    .sh-header {
        background-color: #1a1a2e;
        padding: 1.2rem 2rem;
        margin: -4rem -4rem 2rem -4rem;
        display: flex;
        align-items: center;
        gap: 1.5rem;
    }
    .sh-header img { height: 48px; width: auto; }
    .sh-header-text h1 {
        color: #ffffff;
        font-size: 1.25rem;
        font-weight: 600;
        margin: 0;
        letter-spacing: 0.02em;
    }
    .sh-header-text p {
        color: #a0a8c0;
        font-size: 0.8rem;
        margin: 0;
        letter-spacing: 0.03em;
    }

    /* Contenido */
    .block-container {
        padding-top: 1rem !important;
        max-width: 780px;
    }

    /* Botón de consultar */
    .stFormSubmitButton > button {
        background-color: #1a1a2e !important;
        color: white !important;
        border: none !important;
        border-radius: 6px !important;
        font-weight: 500 !important;
        letter-spacing: 0.03em !important;
        transition: opacity 0.15s;
    }
    .stFormSubmitButton > button:hover { opacity: 0.85 !important; }

    /* Botones secundarios (feedback, sugerencias, nueva consulta) */
    .stButton > button {
        border-radius: 6px !important;
        border: 1px solid #dde1ea !important;
        font-size: 0.85rem !important;
        color: #3a3f52 !important;
        background: #f8f9fc !important;
        transition: background 0.15s;
    }
    .stButton > button:hover {
        background: #eef0f8 !important;
        border-color: #b0b8d0 !important;
    }

    /* Campo de texto */
    .stTextInput > div > div > input {
        border-radius: 6px !important;
        border: 1px solid #dde1ea !important;
        font-size: 1rem !important;
        padding: 0.6rem 0.9rem !important;
    }
    .stTextInput > div > div > input:focus {
        border-color: #1a1a2e !important;
        box-shadow: 0 0 0 2px rgba(26,26,46,0.12) !important;
    }

    /* Bloque de respuesta */
    .sh-respuesta {
        background: #f8f9fc;
        border-left: 3px solid #1a1a2e;
        border-radius: 0 6px 6px 0;
        padding: 1rem 1.2rem;
        margin: 0.5rem 0 0.75rem 0;
        color: #1a1f33;
        line-height: 1.6;
    }

    /* Fuente */
    .sh-fuente {
        font-size: 0.75rem;
        color: #8892a4;
        margin-bottom: 0.75rem;
    }

    /* Label de frecuentes */
    .sh-frecuentes-label {
        font-size: 0.72rem;
        color: #8892a4;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin-bottom: 0.3rem;
    }

    /* Métricas */
    [data-testid="metric-container"] {
        background: #f8f9fc;
        border: 1px solid #eaecf2;
        border-radius: 8px;
        padding: 0.75rem 1rem;
    }
    </style>
    """, unsafe_allow_html=True)


def _render_header() -> None:
    logo_b64 = _get_logo_b64()
    logo_html = f'<img src="data:image/png;base64,{logo_b64}" alt="Singular Hotel">' if logo_b64 else ""
    st.markdown(f"""
    <div class="sh-header">
        {logo_html}
        <div class="sh-header-text">
            <h1>Asistente de recepción</h1>
            <p>Singular Hotel · Consulta interna de procedimientos</p>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ── Estado ────────────────────────────────────────────────────────────────────

def _init_state() -> None:
    for key, default in [
        ("query", ""),
        ("result", None),
        ("feedback_given", None),
        ("error", None),
        ("suggested_query", None),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default


def _reset() -> None:
    st.session_state.query = ""
    st.session_state.result = None
    st.session_state.feedback_given = None
    st.session_state.error = None
    st.session_state.suggested_query = None


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


def _launch_suggestion(pregunta: str) -> None:
    _reset()
    st.session_state.suggested_query = pregunta


# ── Pestaña de consulta ───────────────────────────────────────────────────────

def _render_consulta_tab(collection, settings) -> None:
    if collection is None:
        st.warning(
            "Todavía no hay documentación indexada. Añade documentos en `docs/` "
            "y ejecuta `python scripts/reindex.py` desde la raíz del proyecto."
        )
        return

    # Consultas frecuentes
    frecuentes = _get_frequent_questions(str(settings.feedback_log_path))
    if frecuentes:
        st.markdown('<p class="sh-frecuentes-label">Consultas frecuentes</p>', unsafe_allow_html=True)
        cols = st.columns(len(frecuentes))
        for col, pregunta in zip(cols, frecuentes):
            col.button(
                pregunta,
                key=f"sug_{pregunta[:30]}",
                on_click=_launch_suggestion,
                args=(pregunta,),
                use_container_width=True,
            )
        st.write("")

    # Campo de consulta
    with st.form("consulta_form", clear_on_submit=True):
        query = st.text_input(
            "Consulta",
            placeholder="¿En qué puedo ayudarte?",
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button("Consultar", use_container_width=True)

    # Toggle de modo — debajo del campo para que el flujo sea natural
    mode_keys = list(MODE_LABELS.keys())
    default_index = mode_keys.index(settings.mode_default) if settings.mode_default in mode_keys else 0
    mode_key = st.radio(
        "Modo de respuesta",
        options=mode_keys,
        format_func=lambda k: MODE_LABELS[k],
        index=default_index,
        horizontal=True,
    )

    if submitted and query.strip():
        _reset()
        st.session_state.query = query.strip()

    if st.session_state.suggested_query:
        st.session_state.query = st.session_state.suggested_query
        st.session_state.suggested_query = None

    # Ejecutar la consulta (formulario o sugerencia)
    if st.session_state.query and st.session_state.result is None and not st.session_state.error:
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
                    history=None,
                    use_cache=st.session_state.get("cache_enabled", True),
                )
        except Exception as exc:  # noqa: BLE001
            st.session_state.error = str(exc)

    # Error
    if st.session_state.error:
        st.error(
            "No he podido procesar la consulta. Comprueba que Ollama esté en marcha "
            f"y vuelve a intentarlo.\n\nDetalle: {st.session_state.error}"
        )

    # Resultado
    result = st.session_state.result
    if result is None:
        return

    st.divider()

    if st.session_state.query:
        st.caption(f"**Consulta:** {st.session_state.query}")

    # Respuesta en bloque con estilo
    st.markdown(
        f'<div class="sh-respuesta">{html.escape(result.text)}</div>',
        unsafe_allow_html=True,
    )

    if result.sources:
        st.markdown(
            f'<p class="sh-fuente">📄 {", ".join(result.sources)}</p>',
            unsafe_allow_html=True,
        )

    if result.was_cached:
        st.caption("⚡ Respuesta desde caché validada")

    # Feedback
    if not result.was_escalated and not result.is_clarification:
        fb = st.session_state.feedback_given
        if fb == FEEDBACK_CORRECTO:
            st.success("Marcado como útil.", icon="👍")
        elif fb == FEEDBACK_INCORRECTO:
            st.warning("Marcado como incorrecto. Se revisará la documentación.", icon="👎")
        else:
            col_yes, col_no, _ = st.columns([1, 1, 5])
            col_yes.button("👍 Útil", on_click=_record_feedback, args=(FEEDBACK_CORRECTO,), use_container_width=True)
            col_no.button("👎 No me sirve", on_click=_record_feedback, args=(FEEDBACK_INCORRECTO,), use_container_width=True)

    st.divider()
    if st.button("Nueva consulta"):
        _reset()
        st.rerun()


# ── Pestaña de métricas ───────────────────────────────────────────────────────

def _render_metrics_tab(settings) -> None:
    metrics = compute_summary_metrics(settings.feedback_log_path)

    st.subheader("Impacto acumulado")
    if metrics["total_interacciones"] == 0:
        st.info("Aún no hay consultas registradas.")
    else:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Consultas totales", metrics["total_interacciones"])
        col2.metric("Tasa de respuesta", f"{metrics['tasa_respuesta'] * 100:.0f}%")
        col3.metric("Tasa de escalado", f"{metrics['tasa_escalado'] * 100:.0f}%")
        col4.metric("Tasa de acierto", f"{metrics['tasa_acierto'] * 100:.0f}%")
        st.caption("Tasa de acierto calculada sobre respuestas valoradas con 👍/👎.")
        _render_gap_log(settings.gap_log_path)

    st.divider()
    st.subheader("Mantenimiento")

    cache_enabled = st.toggle(
        "Caché semántico activo",
        value=st.session_state.get("cache_enabled", True),
        help=(
            "Cuando está activo, preguntas similares a respuestas validadas (👍) "
            "se sirven sin llamar al LLM. Desactívalo para forzar el pipeline completo."
        ),
    )
    st.session_state["cache_enabled"] = cache_enabled

    st.caption("Actualiza el índice cuando añadas o modifiques documentos en `docs/`.")
    if st.button("Reindexar documentación", use_container_width=True):
        try:
            with st.spinner("Reindexando… puede tardar 1-2 minutos"):
                result = index_documents(settings)
            st.success(
                f"Reindexado completado: {result['upserted']} chunks actualizados, "
                f"{result['deleted']} obsoletos eliminados."
            )
            _load_collection.clear()
        except Exception as exc:  # noqa: BLE001
            st.error(f"Error al reindexar. ¿Ollama está en marcha?\n\nDetalle: {exc}")


def _render_gap_log(gap_log_path: Path) -> None:
    st.subheader("Huecos de documentación detectados")
    if not gap_log_path.exists():
        st.success("Ninguna consulta ha tenido que escalarse todavía.")
        return

    gap_df = pd.read_csv(gap_log_path, dtype=str, keep_default_na=False)
    if gap_df.empty:
        st.success("Ninguna consulta ha tenido que escalarse todavía.")
        return

    st.caption("Consultas que el asistente no pudo responder con confianza — candidatas a nueva documentación.")

    timestamps = pd.to_datetime(gap_df["timestamp"], errors="coerce", utc=True)
    weekly = timestamps.dt.strftime("%Y-S%V").value_counts().sort_index()
    if not weekly.empty:
        st.bar_chart(weekly, x_label="Semana", y_label="Huecos detectados")

    st.dataframe(
        gap_df[GAP_LOG_COLUMNS].rename(columns={
            "timestamp": "Fecha",
            "pregunta": "Consulta",
            "modo": "Modo",
            "confianza_mejor_resultado": "Confianza máx.",
        }),
        width="stretch",
        hide_index=True,
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    settings = _resolve_settings()
    configure_logging(settings)

    st.set_page_config(
        page_title="Asistente de recepción · Singular Hotel",
        page_icon="🛎️",
        layout="centered",
        initial_sidebar_state="collapsed",
    )
    _inject_css()
    _init_state()
    _render_header()

    collection = _resolve_collection(settings)

    consulta_tab, metrics_tab = st.tabs(["Consulta", "Métricas"])
    with consulta_tab:
        _render_consulta_tab(collection, settings)
    with metrics_tab:
        _render_metrics_tab(settings)


if __name__ == "__main__":
    main()