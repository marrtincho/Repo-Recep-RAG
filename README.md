# Asistente RAG de recepción

Asistente conversacional de uso interno para el equipo de recepción de un
hotel, basado en *Retrieval-Augmented Generation* (RAG) con modelos locales
vía [Ollama](https://ollama.com). Responde dudas operativas — procedimientos,
contactos, ubicaciones de inventario — a partir de documentación fija del
hotel, sin entrenar ni ajustar ningún modelo.

**Alcance v1:** solo conocimiento fijo. No integra novedades del turno ni
sistemas externos (p. ej. Ulyses).

> **Estado:** sistema completo de punta a punta y testeado (más de 200
> tests pasando): ingesta, embeddings/indexado, retrieval, generation,
> orchestration e interfaz Streamlit. El asistente mantiene memoria de
> conversación, puede pedir aclaraciones en vez de adivinar o escalar
> (ADR 0010), e incluye un **caché semántico** que sirve respuestas
> validadas (👍) sin invocar ChromaDB ni el LLM — crítico en hardware de
> baja potencia. Validado con Ollama real en local. El detalle semana a
> semana vive en el historial de commits.

---

## Por qué este enfoque

RAG en vez de fine-tuning: la documentación operativa de un hotel cambia con
frecuencia (procedimientos, contactos, inventario), y un modelo ajustado
quedaría desactualizado en semanas. Con RAG, actualizar el conocimiento del
asistente es tan simple como añadir o editar un documento en `docs/` y
reindexar. El razonamiento completo de esta y otras decisiones técnicas está
documentado en [`docs/decisiones/`](docs/decisiones/).

## Arquitectura

```
Documentos fuente (procedimientos / directorio / inventario)
            ↓
Ingesta y chunking diferenciado por tipo de documento
            ↓
Embeddings (nomic-embed-text vía Ollama)
            ↓
ChromaDB — vectores + metadatos (tipo, categoría, fecha)
            ↓
       Embedding de consulta (una sola vez)
            ↓
  ┌─── Caché semántico (answer_cache.json) ───┐
  │  hit (similitud >= umbral, validado 👍)   │
  │         ↓                                 │
  │  respuesta instantánea (sin LLM)          │
  └────────────────────────────────────────────┘
            │ miss
            ↓
Retrieval + umbral de confianza calibrado
            ↓
     ┌──────┴──────┐
  escala         genera
     ↓               ↓
"no tengo      respuesta + cita de fuente
información"   (modo directo / explicado)
     └──────┬──────┘
            ↓
Registro de métricas (correcta / incorrecta / sin responder)
Feedback 👍 activa entrada en caché; 👎 la desactiva
            ↓
Interfaz Streamlit (chat + toggle + panel de métricas)
```

Cada capa (`ingestion`, `embeddings`, `retrieval`, `generation`,
`orchestration`) es un módulo independiente y testeable por separado.

## Stack

| Capa | Herramienta | Por qué |
|---|---|---|
| Lenguaje | Python 3.11 o 3.12 | Ecosistema maduro para IA local; ver nota de compatibilidad abajo |
| Embeddings | `nomic-embed-text` (Ollama) | Local, gratuito, buen rendimiento en español |
| Modelo generador | Llama 3.1 8B / Mistral 7B (Ollama) | Equilibrio calidad/recursos, sin GPU dedicada |
| Base vectorial | ChromaDB | Embebida, sin servidor adicional |
| Interfaz | Streamlit | Rápida de montar para prototipo |
| Configuración | YAML (`config/settings.yaml`) | Nada hardcodeado: modelo, rutas, umbrales |
| Métricas | CSV/JSON local | Sin infraestructura adicional |

## Estructura del repositorio

```
hotel-recepcion-rag/
├── README.md
├── requirements.txt
├── .gitignore
├── .streamlit/
│   └── config.toml            # tema y opciones de la app Streamlit
├── config/
│   └── settings.yaml          # toda la config ajustable vive aquí
├── docs/
│   ├── procedimientos/        # check-in, reservas, llaves, facturación, parking,
│   │                          # upselling, cuadre de caja, auditoría nocturna…
│   ├── directorios/
│   ├── inventarios/
│   └── decisiones/            # registro de decisiones de diseño (ADRs)
├── src/
│   ├── config.py              # única fuente de verdad para leer settings.yaml
│   ├── ingestion/
│   │   ├── models.py           # Chunk: contrato común hacia embeddings/retrieval
│   │   ├── markdown_parser.py  # parseo genérico: encabezados, tablas, viñetas, metadatos
│   │   ├── text_splitter.py    # división con solape respetando frases e ítems de lista
│   │   ├── table_chunker.py    # directorios + inventarios (misma forma estructural)
│   │   ├── procedure_chunker.py # procedimientos, por subsección, con metadata de modo
│   │   └── pipeline.py         # load_documents(): punto de entrada público de la capa
│   ├── embeddings/
│   │   ├── ollama_client.py     # wrapper sobre el cliente ollama (embeddings)
│   │   └── indexer.py           # genera embeddings y sincroniza ChromaDB (idempotente, con poda)
│   ├── retrieval/
│   │   ├── search.py            # búsqueda en ChromaDB, distancia -> similitud
│   │   ├── confidence.py        # decisión responder/escalar según umbral
│   │   └── pipeline.py          # retrieve(): búsqueda + filtro de modo + confianza
│   ├── generation/
│   │   ├── prompts.py            # plantillas directo/explicado + instrucción de seguridad
│   │   ├── ollama_generator.py   # wrapper sobre ollama.Client().chat()
│   │   └── pipeline.py           # generate_answer(): filtra contexto, arma prompt, llama al modelo
│   └── orchestration/
│       ├── answer_cache.py       # caché semántico: lookup/add/vote por similitud coseno
│       ├── metrics.py            # registro CSV, feedback diferido por interaction_id, agregados
│       └── pipeline.py           # ask(): pipeline completo + caché; submit_feedback()
├── interface/
│   ├── app.py                  # chat (toggle directo/explicado, feedback) + panel de métricas
│   └── logo.png
├── scripts/
│   └── reindex.py              # CLI: reconstruye el índice de ChromaDB desde docs/
├── metrics/                    # solo en local (gitignoreado): contiene datos operativos reales
│   ├── answer_cache.json       # entradas del caché semántico
│   ├── gap_log.csv             # preguntas escaladas sin respuesta
│   ├── feedback_log.csv        # valoraciones 👍/👎 del usuario
│   └── interactions.log        # log de interacciones para auditoría
└── tests/
```

`data/chroma_db/` y `metrics/` quedan fuera del repo (datos operativos reales).
Los documentos de `docs/procedimientos/`, `docs/directorios/` y `docs/referencias/`
también son locales; en el repo solo se versionan los archivos `ejemplo_*.md` de
cada carpeta, que replican la estructura con contenido ficticio para que el sistema
funcione en un clon limpio.

## Instalación

> **Usa Python 3.11 o 3.12.** Este proyecto se desarrolló y testeó con
> 3.12.3. Versiones muy nuevas (p. ej. 3.14) todavía no tienen wheels
> precompilados para algunas dependencias transitivas de ChromaDB (en
> particular `tokenizers`, que requiere compilar un componente en Rust/C), y
> la instalación puede fallar con un error de compilación (`cc ... did not
> execute successfully`). Si te pasa, recrea el venv con `python3.12` en vez
> de `python3` a secas.

```bash
# 1. Clonar y entrar al repo
git clone <url-del-repo>
cd hotel-recepcion-rag

# 2. Entorno virtual (usa explícitamente 3.11 o 3.12, ver nota arriba)
python3.12 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Dependencias
pip install --upgrade pip
pip install -r requirements.txt

# 4. Ollama y modelos locales
#    Instalar Ollama desde https://ollama.com
ollama pull nomic-embed-text
ollama pull llama3.1:8b         # o: ollama pull mistral:7b

# 5. Tests (no requieren Ollama: usan mocks/fakes para esa parte)
pytest
```

## Indexado

Una vez instalado Ollama y descargado `nomic-embed-text`, construir o
reconstruir el índice de ChromaDB a partir de `docs/` es:

```bash
python scripts/reindex.py
```

Es seguro ejecutarlo cuantas veces haga falta: es idempotente (no duplica
chunks ya indexados) y poda del índice cualquier chunk cuyo documento de
origen haya cambiado o desaparecido — ver
[`docs/decisiones/0005-indexado-idempotente-con-poda.md`](docs/decisiones/0005-indexado-idempotente-con-poda.md).

Los tests de `tests/test_indexer.py` no requieren Ollama (usan un cliente de
embeddings fake y ChromaDB en modo efímero). Los de
`tests/test_ollama_client.py` tampoco: mockean la librería `ollama`. La única
validación que sí requiere Ollama real corriendo en local es ejecutar
`scripts/reindex.py` de principio a fin.

## Uso

Con el índice ya construido y Ollama corriendo con el modelo generador
descargado (`ollama pull llama3.1:8b` o `mistral:7b`):

```bash
streamlit run interface/app.py
```

Si todavía no hay nada indexado, la app lo indica claramente en vez de
fallar — no hace falta adivinar qué pasó. `tests/test_app.py` cubre ese
arranque en frío, el flujo de chat y el feedback con
[`streamlit.testing.v1.AppTest`](https://docs.streamlit.io/develop/api-reference/app-testing),
sin necesitar Ollama ni navegador (ver
[`docs/decisiones/0009-session-state-como-costura-de-tests.md`](docs/decisiones/0009-session-state-como-costura-de-tests.md)).

## Caché semántico

El caché evita invocar ChromaDB y el LLM cuando una pregunta ya fue
respondida y validada. El ciclo de vida de una entrada:

1. Cada respuesta generada crea una entrada **tentativa** (`active=False`).
2. Un 👍 la **activa** (`active=True`); a partir de ahí se sirve en
   consultas con similitud coseno >= umbral configurable.
3. Un 👎 incrementa `negative_votes`; si iguala o supera a `positive_votes`,
   la entrada vuelve a `active=False`.

Las preguntas casi idénticas (similitud >= 0.95) se fusionan en la entrada
existente en vez de crear duplicados. El caché se persiste en
`metrics/answer_cache.json` y se configura desde `config/settings.yaml`
(`semantic_cache_similarity_threshold`, `semantic_cache_path`).

## Desarrollo

Las preguntas de validación que se usan para calibrar el sistema viven como
test suite real en `tests/`, no solo como pruebas manuales. Cada interacción
del asistente registra pregunta, fragmento recuperado, confianza, decisión
(responder/escalar) y modo usado — la base del panel de métricas.

Decisiones técnicas relevantes se documentan en
[`docs/decisiones/`](docs/decisiones/) a medida que se toman, no
retroactivamente al final del proyecto.
