# 0006 — Métrica coseno para que el umbral de confianza tenga sentido

## Contexto

`config/settings.yaml` define `retrieval.confidence_threshold: 0.65` como un
valor de **similitud** en el rango [0, 1], donde más alto significa más
confianza (ver sección 6 del plan de acción original: "Confianza: Puntaje de
similitud del fragmento recuperado"). ChromaDB, sin embargo, no fija una
métrica de distancia por defecto explícita en su API de alto nivel: si no se
especifica, usa L2 (distancia euclídea), que no tiene ese rango ni esa
dirección ("más bajo" sería mejor, no más alto, y no está acotado a [0, 1]).

## Decisión

La colección de ChromaDB se crea siempre con
`metadata={"hnsw:space": "cosine"}` (ver `get_collection` en
`src/embeddings/indexer.py`), y la capa de retrieval convierte la distancia
coseno que devuelve ChromaDB a similitud con `similitud = 1 - distancia`,
antes de compararla contra `confidence_threshold`.

Si `get_collection` detecta que la colección ya existe con una métrica
distinta a coseno, lanza un error explícito en vez de continuar — ver el
mensaje de error en el propio código para la instrucción de recuperación
(borrar `data/chroma_db/` y reindexar).

## Razonamiento

- **nomic-embed-text, como la mayoría de modelos de embeddings de texto,
  está optimizado para similitud por ángulo, no por magnitud.** La magnitud
  del vector resultante varía con la longitud y densidad del texto sin que
  eso aporte señal semántica; la distancia coseno la ignora por
  construcción (normaliza implícitamente), mientras que L2 la mezcla en el
  resultado. Esto importa especialmente aquí porque el corpus mezcla chunks
  muy cortos (una fila de tabla: "Departamento: Dirección...") con chunks
  más largos (una subsección de procedimiento de varios cientos de
  caracteres) — con L2, esa diferencia de longitud por sí sola sesgaría las
  distancias de forma no relacionada con el significado.
- **Fallar en silencio aquí sería peor que fallar ruidosamente.** Si la
  métrica fuera L2 sin que nadie lo note, el umbral de 0.65 seguiría
  "funcionando" en el sentido de que el código no rompe, pero las
  decisiones de escalar/responder dejarían de tener relación con la
  confianza real del sistema — un fallo silencioso de los más peligrosos
  posibles en un sistema pensado para no inventar respuestas.
- **Por qué fijarlo en la creación de la colección y no en cada consulta.**
  La métrica de distancia de un índice HNSW de ChromaDB es una propiedad de
  la colección, fijada en el momento de su creación — no se puede cambiar
  por consulta. Por eso la validación vive en `get_collection`, el único
  punto donde la colección se crea o se abre.

## Consecuencias

- Cualquier colección de ChromaDB creada antes de este ADR (con la métrica
  por defecto, L2) deja de ser válida: `get_collection` lo detecta y lanza
  un error pidiendo borrar `data/chroma_db/` y reindexar desde cero. No hay
  forma de "migrar" una colección existente a otra métrica en ChromaDB sin
  reconstruir el índice completo, así que no se intenta.
- Toda la capa de retrieval debe asumir que `collection.query()` devuelve
  distancias coseno, y convertirlas a similitud antes de comparar contra
  `confidence_threshold` (nunca comparar la distancia cruda contra el
  umbral directamente).
