# 0005 — Indexado idempotente con poda de chunks obsoletos

## Contexto

El índice de ChromaDB se reconstruye cada vez que cambia la documentación
fuente (`docs/`). Necesitábamos decidir cómo manejar reindexar: ¿se borra
toda la colección y se recrea desde cero cada vez, o se actualiza solo lo
que cambió?

## Decisión

El indexador usa `collection.upsert()` con los `chunk_id` estables y
deterministas de la capa de ingesta (insertar o actualizar, nunca duplicar),
y además compara el conjunto de ids ya presentes en la colección contra el
conjunto de ids del corpus actual: cualquier id que ya no exista en
`docs/` se elimina explícitamente de la colección tras el upsert.

## Razonamiento

- **Borrar y recrear todo en cada reindexado es más lento y más arriesgado
  de lo necesario.** Para un corpus de 10-12 documentos no es un problema de
  rendimiento, pero sí lo es de seguridad operativa: si el indexado falla a
  mitad de proceso, una estrategia "borra todo primero" deja el sistema sin
  índice funcional hasta la siguiente ejecución exitosa. El upsert
  incremental nunca deja el índice en un estado peor que el anterior.
- **El upsert por sí solo no es suficiente.** Si una fila de una tabla se
  borra del documento fuente (p. ej. un contacto que deja de ser válido), su
  chunk_id simplemente no vuelve a generarse en la siguiente ingesta — pero
  upsert no elimina nada, así que esa entrada quedaría huérfana en
  ChromaDB para siempre, y el asistente seguiría pudiendo "recuperarla" y
  citarla como si la documentación actual la respaldara. Eso es
  silenciosamente peor que no tener la información: es tener información
  incorrecta con apariencia de autoridad.
- **Por qué chunk_id determinista importa aquí.** Esta poda solo es posible
  porque el chunk_id se construye de forma estable a partir de la posición
  estructural del contenido (ver `chunk_table_document` y
  `chunk_procedure_document`), no de un UUID aleatorio generado en cada
  ejecución. Sin esa propiedad, cada reindexado parecería "todo es nuevo,
  todo lo anterior es obsoleto" y el upsert degeneraría en duplicación o en
  borrar y recrear todo de todas formas.

## Consecuencias

- `index_chunks` siempre hace una lectura adicional de los ids existentes en
  la colección (`collection.get(include=[])`) tras cada upsert, lo cual es
  barato porque no trae embeddings ni documentos, solo ids.
- Si el chunking de un documento cambia de forma que sus chunk_id ya no
  coinciden con los de la ejecución anterior (p. ej. se reescribe la
  plantilla de IDs), el siguiente reindexado tratará todo como nuevo y
  podará todo lo anterior como obsoleto. Es el comportamiento correcto, pero
  conviene tenerlo presente si se modifica el esquema de IDs más adelante.
