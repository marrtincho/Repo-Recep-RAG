# 0003 — Chunking de procedimientos por subsección, con metadata de modo

## Contexto

La plantilla de procedimientos (`docs/procedimientos/`) define explícitamente
que la subsección "Resumen rápido" alimenta el modo directo del asistente, y
"Procedimiento detallado" alimenta el modo explicado. Esto no es un detalle
de redacción: es información estructural sobre cómo debe funcionar el
sistema, presente en el propio formato del documento fuente.

## Decisión

El chunking de `procedimientos` divide cada procedimiento por sus
subsecciones H3 (Resumen rápido, Procedimiento detallado, Casos especiales,
Cuándo escalar, Preguntas habituales, Notas internas), nunca por ventanas de
caracteres ciegas a la estructura. Cada chunk resultante lleva en su metadata
un campo `modo` con tres valores posibles:

- `"directo"` — proviene de "Resumen rápido"
- `"explicado"` — proviene de "Procedimiento detallado"
- `"ambos"` — proviene de cualquier otra subsección (casos especiales, cuándo
  escalar, preguntas habituales, notas internas)

Si una subsección supera el `chunk_size` configurado, se subdivide con
solape (`split_with_overlap`), pero la metadata de modo se mantiene idéntica
en todos los sub-fragmentos resultantes.

## Razonamiento

- **El modo no es un parámetro de presentación, es un filtro de retrieval.**
  Si en modo directo el sistema recupera un fragmento de "Procedimiento
  detallado" lleno de razonamiento y contexto, la respuesta corta que se
  espera en ese modo se contamina con explicación que el usuario no pidió, y
  viceversa: en modo explicado, recuperar solo el resumen deja al usuario sin
  el porqué. Separar por subsección permite filtrar en la capa de retrieval
  (`where={"modo": {"$in": [modo_actual, "ambos"]}}` en ChromaDB) antes
  siquiera de generar la respuesta.
- **Por qué no ventanas de caracteres ciegas.** Una subsección de 800
  caracteres partida a la mitad por una ventana de 500 caracteres mezclaría,
  por ejemplo, el final de "Resumen rápido" con el inicio de "Procedimiento
  detallado" en el mismo chunk — exactamente la mezcla de modos que se quiere
  evitar. Respetar los límites de subsección primero, y solo subdividir
  dentro de una subsección cuando hace falta, preserva la frontera de modo
  siempre.
- **El umbral de confianza opera por chunk, no por documento completo.** Si
  el "Resumen rápido" de un procedimiento es claro pero su "Procedimiento
  detallado" tiene una redacción ambigua, el sistema puede responder con
  confianza en modo directo y escalar en modo explicado para ese mismo
  procedimiento — una granularidad que se pierde si el chunk es el documento
  entero.

## Consecuencias

- Cualquier documento de procedimiento que no siga la plantilla (sin
  subsecciones H3 reconocibles) no aporta chunks utilizables — el chunker
  registra un aviso y omite el bloque en vez de indexarlo mal estructurado.
  Esto hace que seguir la plantilla no sea opcional: es un requisito para que
  un procedimiento sea indexable.
- Un archivo `.md` puede mezclar contenido de plantilla genérica (sin
  metadatos rellenados) con procedimientos reales sin contaminar el índice:
  el chunker exige metadatos completos (categoría, última actualización,
  validado por) inmediatamente después del título del procedimiento para
  considerarlo real, y omite cualquier bloque que no los tenga.
