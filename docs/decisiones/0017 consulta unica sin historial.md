# 0017 — Paradigma de consulta única: eliminar el historial conversacional

## Contexto

El sistema se construyó originalmente con un paradigma de chat acumulado:
cada turno añadía el mensaje del usuario y la respuesta del asistente a un
historial que se pasaba tanto al retrieval (para enriquecer la consulta de
búsqueda) como a la generación (para que el modelo entendiera preguntas de
seguimiento como "¿y si se niega?").

Con el uso real se observaron dos problemas que el historial causaba:

1. **Contaminación semántica entre preguntas de temas distintos.** El
   historial de los turnos anteriores se concatenaba a la query actual antes
   de buscar en el índice. Si los turnos anteriores hablaban de parking y el
   usuario preguntaba sobre facturación, la query de búsqueda real contenía
   "parking... factura a nombre de empresa", y el documento de parking podía
   seguir puntuando alto. El log de feedback mostró esto empíricamente:
   "cómo facturar a empresa" recuperaba `Parking.md` después de una consulta
   de parking.

2. **El paradigma de chat no refleja el patrón de uso real.** En recepción,
   las preguntas son consultas puntuales: alguien llega con un ticket de
   parking, lo resuelve, y la siguiente pregunta es sobre una factura de
   empresa sin ninguna relación. El interfaz de chat con historial visible
   no solo no añadía valor — añadía confusión para el usuario final y
   complejidad de código innecesaria.

## Decisión

Se abandona el paradigma de chat acumulado en favor de **consulta única**:
- La interfaz (`interface/app.py`) muestra una sola consulta y su resultado
  a la vez. Campo de texto grande, respuesta debajo, feedback, y "Nueva
  consulta" para empezar limpio.
- `ask()` en `src/orchestration/pipeline.py` mantiene el parámetro `history`
  en la firma por compatibilidad de llamadas externas, pero lo ignora: siempre
  pasa `history=None` a `retrieve()` y `generate_answer()`.
- Se elimina la lógica de `_contextualize_query` (que concatenaba historial a
  la query de retrieval) del camino de ejecución efectivo.

## Razonamiento

- **La ganancia del historial era menor que su coste.** El historial ayudaba
  con preguntas de seguimiento dentro del mismo tema ("¿y si se niega?"),
  pero el patrón de uso real muestra que esto es raro comparado con cambios
  de tema entre consultas. La contaminación semántica era más frecuente que
  el beneficio del seguimiento.
- **El retrieval ahora es más predecible y más fácil de diagnosticar.** Sin
  historial, la query que llega a ChromaDB es exactamente lo que escribió el
  usuario. Esto simplifica el diagnóstico (el script de evaluación es más
  claro) y reduce la superficie de fallos.
- **La interfaz de consulta única es más apropiada para el contexto.** Un
  recepcionista con prisa no necesita ver el historial de sus últimas cinco
  preguntas — necesita una respuesta rápida a su duda actual. La interfaz
  sin historial visible es más limpia y más intuitiva para ese caso de uso.
- **`allow_clarification: false` (ADR anterior) ya había eliminado el caso
  de uso más valioso del historial.** Las aclaraciones (donde el historial
  era crítico para que el modelo recuerde qué había preguntado) están
  desactivadas para los modelos pequeños. Sin aclaraciones, el historial en
  generación era código activo pero sin caso de uso real.

## Consecuencias

- Se simplifica significativamente el código de orquestación, retrieval y la
  interfaz: desaparece `_contextualize_query`, el bloque de historial en
  `build_history_block`, y toda la lógica de `session_state.messages` como
  lista acumulada.
- Los tests de historial en orchestration se invierten: ahora verifican que
  `CONVERSACIÓN PREVIA` NO aparece en el prompt (en vez de que sí aparezca).
- Si en el futuro se quiere reactivar el historial (por ejemplo, con un
  modelo más capaz que gestione bien los cambios de tema), el parámetro
  `history` ya está en la firma de `ask()` y `generate_answer()` — solo hay
  que volver a pasarlo desde la interfaz y descomentarlo en el pipeline.