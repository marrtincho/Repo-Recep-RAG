"""
Tests de interface/app.py usando el framework nativo de Streamlit (AppTest).

No requieren Ollama ni navegador. El backend se sustituye vía session_state
("_test_*_override"), no con unittest.mock.patch: AppTest ejecuta el script
en un namespace propio y aislado en cada `.run()`, así que un patch sobre el
módulo ya importado en el proceso de test no llega a afectar esa ejecución.
session_state sí es compartido — ver el comentario en interface/app.py.

Lo que se valida aquí es el comportamiento de la interfaz (estados de
arranque, render de mensajes, feedback), no el backend, que ya tiene sus
propios tests.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

from streamlit.testing.v1 import AppTest

from src.orchestration.metrics import RESULTADO_RESPONDIDA, log_interaction

APP_PATH = str(Path(__file__).resolve().parent.parent / "interface" / "app.py")


def _default_test_settings() -> SimpleNamespace:
    """
    Settings mínimas y aisladas para tests de interfaz.

    Apuntan a un directorio temporal nuevo en cada llamada, para que ningún
    test dependa (ni contamine) los logs reales de metrics/ del repo. Solo
    incluye los atributos que interface/app.py realmente lee directamente
    (el resto de la lógica de negocio ya tiene sus propios tests con la
    Settings real — ver tests/test_orchestration_pipeline.py).
    """
    base = Path(tempfile.mkdtemp(prefix="hotel_rag_test_"))
    return SimpleNamespace(
        feedback_log_path=base / "feedback_log.csv",
        gap_log_path=base / "gap_log.csv",
        mode_default="directo",
        log_level="WARNING",
        log_file=base / "test.log",
        semantic_cache_path=base / "answer_cache.json",
        semantic_cache_similarity_threshold=0.85,
    )


class FakeCollection:
    """Colección mínima: solo necesita responder a count() para las comprobaciones de la UI."""

    def __init__(self, count: int) -> None:
        self._count = count

    def count(self) -> int:
        return self._count


class FakeOrchestrationResult:
    def __init__(self, text, sources, interaction_id, was_escalated, is_clarification=False, confidence=0.9, mode="directo", was_cached=False):
        self.text = text
        self.sources = sources
        self.interaction_id = interaction_id
        self.was_escalated = was_escalated
        self.is_clarification = is_clarification
        self.confidence = confidence
        self.mode = mode
        self.was_cached = was_cached


def _make_app(collection=None, ask_fn=None, submit_feedback_fn=None, settings=None) -> AppTest:
    at = AppTest.from_file(APP_PATH)
    at.session_state["_test_collection_override"] = collection
    at.session_state["_test_settings_override"] = settings or _default_test_settings()
    if ask_fn is not None:
        at.session_state["_test_ask_override"] = ask_fn
    if submit_feedback_fn is not None:
        at.session_state["_test_submit_feedback_override"] = submit_feedback_fn
    return at


def _submit_query(at: AppTest, query: str) -> AppTest:
    """Rellena el campo de texto y envía el formulario."""
    at.text_input[0].set_value(query)
    next(b for b in at.button if b.label == "Consultar").click().run()
    return at


class TestColdStart:
    def test_shows_index_missing_notice_when_no_collection(self):
        at = _make_app(collection=None).run()
        assert not at.exception
        warnings = " ".join(w.value for w in at.warning)
        assert "reindex.py" in warnings

    def test_no_query_input_rendered_without_an_index(self):
        at = _make_app(collection=None).run()
        assert len(at.text_input) == 0

    def test_metrics_tab_shows_empty_state_with_no_interactions(self):
        at = _make_app(collection=None).run()
        assert not at.exception
        infos = " ".join(i.value for i in at.info)
        assert "consultas registradas" in infos.lower()

    def test_metrics_tab_shows_real_numbers_when_interactions_exist(self):
        """
        Regresión: cada test usa settings aisladas (un directorio temporal nuevo cada vez), así
        que datos de un test no deben filtrarse a otro, ni tampoco los datos reales del repo.
        """
        settings = _default_test_settings()
        log_interaction(settings.feedback_log_path, settings.gap_log_path, "pregunta", RESULTADO_RESPONDIDA, 0.9, ["a.md"], "directo")

        at = _make_app(collection=None, settings=settings).run()

        assert not at.exception
        infos = " ".join(i.value for i in at.info)
        assert "consultas registradas" not in infos.lower()
        metric_values = [m.value for m in at.metric]
        assert "1" in metric_values


class TestChatFlow:
    def test_user_message_triggers_ask_and_renders_response(self):
        fake_result = FakeOrchestrationResult(
            text="Para gestionar un overbooking, verifica disponibilidad en Ulyses.",
            sources=["overbooking.md"],
            interaction_id="abc-123",
            was_escalated=False,
        )
        at = _make_app(collection=FakeCollection(10), ask_fn=lambda *a, **k: fake_result).run()

        _submit_query(at, "¿cómo gestiono un overbooking?")

        assert not at.exception
        markdowns = " ".join(m.value for m in at.markdown)
        assert "overbooking" in markdowns.lower()

    def test_sources_shown_after_response(self):
        fake_result = FakeOrchestrationResult(
            text="Respuesta.", sources=["overbooking.md", "contactos.md"], interaction_id="x", was_escalated=False,
        )
        at = _make_app(collection=FakeCollection(10), ask_fn=lambda *a, **k: fake_result).run()
        _submit_query(at, "pregunta")

        markdowns = " ".join(m.value for m in at.markdown)
        assert "overbooking.md" in markdowns
        assert "contactos.md" in markdowns

    def test_escalated_response_shows_no_feedback_buttons(self):
        fake_result = FakeOrchestrationResult(
            text="No tengo información suficiente sobre esto, consulta con tu responsable.",
            sources=[],
            interaction_id="esc-1",
            was_escalated=True,
        )
        at = _make_app(collection=FakeCollection(10), ask_fn=lambda *a, **k: fake_result).run()
        _submit_query(at, "algo que no está documentado")

        assert not at.exception
        button_labels = [b.label for b in at.button]
        assert not any("Útil" in label for label in button_labels)

    def test_answered_response_shows_feedback_buttons(self):
        fake_result = FakeOrchestrationResult(text="Respuesta.", sources=["a.md"], interaction_id="x", was_escalated=False)
        at = _make_app(collection=FakeCollection(10), ask_fn=lambda *a, **k: fake_result).run()
        _submit_query(at, "pregunta")

        button_labels = [b.label for b in at.button]
        assert any("Útil" in label for label in button_labels)
        assert any("No me sirve" in label for label in button_labels)

    def test_feedback_button_calls_submit_feedback_with_correct_id(self):
        fake_result = FakeOrchestrationResult(text="Respuesta.", sources=["a.md"], interaction_id="fb-1", was_escalated=False)
        calls = []
        at = _make_app(
            collection=FakeCollection(10),
            ask_fn=lambda *a, **k: fake_result,
            submit_feedback_fn=lambda interaction_id, value, settings: calls.append((interaction_id, value)),
        ).run()
        _submit_query(at, "una consulta")

        yes_button = next(b for b in at.button if "Útil" in b.label)
        yes_button.click().run()

        assert not at.exception
        assert calls == [("fb-1", "correcto")]

    def test_feedback_buttons_disappear_after_voting(self):
        fake_result = FakeOrchestrationResult(text="Respuesta.", sources=["a.md"], interaction_id="fb-2", was_escalated=False)
        at = _make_app(
            collection=FakeCollection(10),
            ask_fn=lambda *a, **k: fake_result,
            submit_feedback_fn=lambda *a, **k: None,
        ).run()
        _submit_query(at, "una consulta")

        yes_button = next(b for b in at.button if "Útil" in b.label)
        yes_button.click().run()

        assert not at.exception
        button_labels = [b.label for b in at.button]
        assert not any("Útil" in label for label in button_labels)

    def test_backend_error_degrades_gracefully(self):
        def _raise(*args, **kwargs):
            raise RuntimeError("Ollama caído")

        at = _make_app(collection=FakeCollection(10), ask_fn=_raise).run()
        _submit_query(at, "una consulta")

        assert not at.exception
        errors = " ".join(e.value for e in at.error)
        assert "Ollama" in errors

    def test_mode_toggle_offers_both_modes(self):
        at = _make_app(collection=FakeCollection(10)).run()
        radio = at.radio[0]
        assert len(radio.options) == 2
        assert any("Directo" in opt for opt in radio.options)
        assert any("Explicado" in opt for opt in radio.options)

    def test_clarification_response_shows_no_feedback_buttons(self):
        fake_result = FakeOrchestrationResult(
            text="¿el huésped ya llegó al hotel?",
            sources=[],
            interaction_id="clar-1",
            was_escalated=False,
            is_clarification=True,
        )
        at = _make_app(collection=FakeCollection(10), ask_fn=lambda *a, **k: fake_result).run()
        _submit_query(at, "tengo un overbooking")

        assert not at.exception
        button_labels = [b.label for b in at.button]
        assert not any("Útil" in label for label in button_labels)
