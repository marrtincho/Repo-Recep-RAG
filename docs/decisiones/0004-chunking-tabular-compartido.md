# 0004 — Chunker tabular compartido entre directorios e inventarios

## Contexto

Al inspeccionar los documentos reales de directorio de contactos y de
ubicaciones de inventario, ambos resultaron tener exactamente la misma forma
estructural: título H1, metadatos, varias secciones H2 que contienen una
tabla markdown (entidad → datos asociados), y una sección final de "Notas de
mantenimiento" sin tabla.

## Decisión

`directorios` e `inventarios` se procesan con el mismo chunker
(`table_chunker.py`). La diferencia entre ambos tipos de documento es solo el
valor de `doc_type` que se les asigna y la carpeta de origen, definida en
`config/settings.yaml` — no hay dos implementaciones de chunking distintas
que mantener en paralelo.

## Razonamiento

- **Duplicar la lógica de parseo de tablas para dos tipos de documento
  estructuralmente idénticos** habría significado mantener dos copias del
  mismo código (parseo de tabla, descarte de filas vacías, conversión de
  fila a texto natural) que solo se diferencian en una etiqueta. Cualquier
  mejora futura (p. ej. un mejor formato de texto por fila) tendría que
  aplicarse dos veces y mantenerse sincronizada.
- **Si en el futuro un tipo de documento diverge estructuralmente** (por
  ejemplo, si "inventarios" pasara a tener un formato distinto, no tabular),
  la solución es separar esa rama en su propio chunker en ese momento, no
  anticipar la divergencia hoy sin evidencia de que vaya a ocurrir.
- **Las filas de plantilla sin rellenar no aportan información recuperable.**
  Se observó en los documentos reales que la mayoría de las filas de tabla
  están vacías (son plantilla, pendientes de completar). El chunker descarta
  cualquier fila donde ninguna columna más allá de la columna clave tenga
  contenido — de lo contrario, el índice se llenaría de fragmentos vacíos sin
  ningún valor semántico para el retrieval.

## Consecuencias

- El chunker tabular acepta una lista cerrada de `doc_type` válidos
  (`directorios`, `inventarios`) y rechaza explícitamente cualquier otro
  valor, para que un error de configuración (p. ej. enrutar `procedimientos`
  por aquí por accidente) falle de forma ruidosa en vez de producir chunks
  mal formados en silencio.
- Si una tabla completa de un documento no tiene ninguna fila con datos
  reales (caso observado en el fixture de inventario, que es una plantilla
  sin rellenar), esa sección legítimamente no aporta chunks. Esto no es un
  error del sistema, es un reflejo fiel de que esa documentación todavía no
  existe — y es exactamente la clase de hueco que el gap log (sección 6 del
  plan de acción) está pensado para detectar una vez el sistema esté en uso.
