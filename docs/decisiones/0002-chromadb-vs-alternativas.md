# 0002 — ChromaDB como base vectorial

## Contexto

El sistema necesita almacenar embeddings de los fragmentos documentales junto
con sus metadatos (tipo de documento, categoría, fecha) y poder hacer
búsqueda por similitud sobre ellos. El volumen esperado es bajo: 10-12
documentos fuente para el prototipo.

## Decisión

Se usa ChromaDB en modo embebido (sin servidor separado), persistida en
`data/chroma_db/`.

## Razonamiento

- **Sin infraestructura adicional.** ChromaDB corre embebida en el propio
  proceso Python, sin necesidad de levantar un servicio aparte (a diferencia
  de Qdrant o Weaviate en modo servidor, o de Postgres+pgvector, que exigirían
  gestionar una base de datos completa para un volumen de datos mínimo).
- **Volumen del proyecto.** Con un puñado de documentos, las ventajas de
  bases vectoriales pensadas para millones de vectores (Pinecone, Milvus) no
  aportan nada aquí; sí añaden complejidad operativa y, en el caso de
  servicios gestionados, una dependencia externa que rompe el requisito de
  "todo corre en local".
- **Metadatos nativos.** ChromaDB permite adjuntar metadatos arbitrarios
  (tipo de documento, categoría, fecha) a cada vector y filtrar por ellos en
  la búsqueda, que es exactamente lo que necesita el chunking diferenciado
  por tipo de documento.
- **Fricción de desarrollo.** API simple en Python, sin configuración previa
  más allá de elegir una carpeta de persistencia — coherente con el resto del
  stack, pensado para minimizar piezas móviles en un prototipo.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| FAISS | Más bajo nivel: no gestiona persistencia ni metadatos de forma nativa, habría que construir esa capa a mano |
| Qdrant / Weaviate (servidor) | Requieren un servicio adicional corriendo; sobredimensionado para 10-12 documentos |
| Pinecone / servicios gestionados | Dependencia externa y de pago; rompe el requisito de funcionar 100% en local |
| Postgres + pgvector | Añade una base de datos relacional completa para un caso de uso que no la necesita |

## Consecuencias

- Si el volumen de documentos creciera significativamente más allá del
  alcance de este prototipo, convendría revisar esta decisión.
- La persistencia en disco (`data/chroma_db/`) debe excluirse del control de
  versiones y reconstruirse desde `docs/` en cada entorno nuevo.
