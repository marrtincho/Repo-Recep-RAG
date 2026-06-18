# Asistente RAG de recepción

Asistente conversacional de uso interno para el equipo de recepción de un
hotel, basado en *Retrieval-Augmented Generation* (RAG) con modelos locales
vía [Ollama](https://ollama.com). Responde dudas operativas — procedimientos,
contactos, ubicaciones de inventario — a partir de documentación fija del
hotel, sin entrenar ni ajustar ningún modelo.

**Alcance v1:** solo conocimiento fijo. No integra novedades del turno ni
sistemas externos (p. ej. Ulyses).

> Estado: en desarrollo activo. Este README se actualiza a medida que avanza
> el proyecto; el detalle semana a semana vive en el historial de commits.

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
            ↓
Interfaz Streamlit (chat + toggle + panel de métricas)
```

Cada capa (`ingestion`, `embeddings`, `retrieval`, `generation`,
`orchestration`) es un módulo independiente y testeable por separado.

## Stack

| Capa | Herramienta | Por qué |
|---|---|---|
| Lenguaje | Python 3.11+ | Ecosistema maduro para IA local |
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
├── config/
│   └── settings.yaml          # toda la config ajustable vive aquí
├── docs/
│   ├── procedimientos/
│   ├── directorios/
│   ├── inventarios/
│   └── decisiones/            # registro de decisiones de diseño (ADRs)
├── src/
│   ├── config.py              # única fuente de verdad para leer settings.yaml
│   ├── ingestion/              # carga y chunking diferenciado
│   ├── embeddings/             # generación de vectores
│   ├── retrieval/              # búsqueda y umbral de confianza
│   ├── generation/             # prompts y llamada al modelo
│   └── orchestration/          # decisión escalar/responder + citación
├── interface/
│   └── app.py                  # interfaz Streamlit
├── metrics/
│   ├── gap_log.csv             # preguntas escaladas sin respuesta
│   └── feedback_log.csv        # valoraciones 👍/👎 del usuario
└── tests/
```

`data/chroma_db/` (base vectorial persistida) y cualquier documento real del
hotel quedan fuera del repo — ver `.gitignore`. La versión pública usa
documentos de ejemplo ficticios que replican la estructura sin datos reales.

## Instalación

```bash
# 1. Clonar y entrar al repo
git clone <url-del-repo>
cd hotel-recepcion-rag

# 2. Entorno virtual
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Dependencias
pip install -r requirements.txt

# 4. Ollama y modelos locales
#    Instalar Ollama desde https://ollama.com
ollama pull nomic-embed-text
ollama pull llama3.1:8b         # o: ollama pull mistral:7b

# 5. Tests
pytest
```

## Desarrollo

Las preguntas de validación que se usan para calibrar el sistema viven como
test suite real en `tests/`, no solo como pruebas manuales. Cada interacción
del asistente registra pregunta, fragmento recuperado, confianza, decisión
(responder/escalar) y modo usado — la base del panel de métricas.

Decisiones técnicas relevantes se documentan en
[`docs/decisiones/`](docs/decisiones/) a medida que se toman, no
retroactivamente al final del proyecto.
