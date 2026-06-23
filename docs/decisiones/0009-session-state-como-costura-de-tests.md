# 0009 — session_state como costura de inyección para testear la interfaz

## Contexto

`interface/app.py` se testea con `streamlit.testing.v1.AppTest`, el
framework de testing nativo de Streamlit. `AppTest.from_file()` ejecuta el
script en un namespace propio y aislado en cada `.run()` — no reutiliza el
módulo que el proceso de test pueda tener ya importado. Esto significa que
`unittest.mock.patch("interface.app.X", ...)`, que sí funciona en el resto
del proyecto (ver tests de `ollama_client.py`, `ollama_generator.py`), no
tiene ningún efecto sobre lo que `AppTest` realmente ejecuta: se confirmó
empíricamente antes de esta decisión, no se asumió.

## Decisión

Tres puntos de extensión (`collection`, `ask`, `submit_feedback`) se
resuelven a través de pequeñas funciones (`_resolve_collection`,
`_resolve_ask`, `_resolve_submit_feedback`) que primero comprueban si hay un
valor inyectado en `st.session_state["_test_*_override"]`, y si no lo hay,
caen al comportamiento real (recursos cacheados con `@st.cache_resource`,
llamada real a `src.orchestration.pipeline`). Los tests en
`tests/test_app.py` preestablecen esas claves de `session_state` antes de
llamar a `.run()` — `session_state` sí es compartido entre el test y la
ejecución de `AppTest`, es el punto de inyección que el propio framework
soporta para esto.

## Razonamiento

- **No vale la pena montar Ollama ni ChromaDB reales solo para testear la
  interfaz.** El backend (retrieval, generation, orchestration) ya tiene su
  propia batería de tests con fakes/mocks; lo que hace falta validar aquí es
  el comportamiento específico de la UI (arranque sin índice, render de
  mensajes, aparición/desaparición de los botones de feedback, degradación
  ante errores) — todo eso es independiente de si el backend funciona de
  verdad o no.
- **Por qué no extraer toda la lógica de interface/app.py a un módulo aparte
  para poder mockear por import normal.** Se consideró, pero hubiera
  separado la lógica de su contexto de Streamlit (session_state, cacheo,
  reactividad) de una forma que no refleja cómo se usa en producción, y este
  patrón de `session_state` como costura es el soportado oficialmente por
  `AppTest` para este caso exacto.
- **Por qué no dejar la app sin tests de interfaz.** El plan exige pruebas
  automatizadas desde el principio, no solo pruebas manuales. La interfaz es
  la capa con más estado implícito del proyecto (qué se muestra, cuándo
  desaparecen los botones, qué pasa si Ollama está caído) — exactamente
  donde más vale la pena tener regresión automática, no menos.

## Consecuencias

- Cualquier nuevo recurso externo o función de orchestration que la interfaz
  necesite llamar directamente debe seguir el mismo patrón
  (`_resolve_<nombre>`) si se quiere poder testear sin dependencias reales.
- Las claves `_test_*_override` son un detalle de testing que vive en
  producción (dentro de `interface/app.py`), no en un módulo de test aparte.
  Es una concesión deliberada: el comentario en el propio código explica por
  qué existen, para que no se confundan con configuración real de la app.
