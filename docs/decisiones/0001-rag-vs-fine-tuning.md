# 0001 — RAG en vez de fine-tuning

## Contexto

El asistente necesita responder con precisión sobre documentación operativa
del hotel: procedimientos, directorio de contactos, ubicaciones de
inventario. Esta documentación cambia con regularidad — un procedimiento se
actualiza, un contacto cambia de número, el inventario se reorganiza.

## Decisión

Se implementa mediante Retrieval-Augmented Generation (RAG) sobre un modelo
local vía Ollama, en vez de hacer fine-tuning de un modelo sobre el contenido
del hotel.

## Razonamiento

- **Actualización del conocimiento.** Con RAG, actualizar el asistente es
  añadir o editar un archivo en `docs/` y reindexar. Con fine-tuning, cada
  cambio de documentación implicaría reentrenar el modelo: coste de tiempo,
  cómputo y riesgo de degradar capacidades generales del modelo (catastrophic
  forgetting), inasumible para un prototipo mantenido por una sola persona.
- **Trazabilidad de la respuesta.** RAG permite citar la fuente exacta que
  respalda cada respuesta. Un modelo fine-tuned mezcla el conocimiento
  aprendido con el resto de sus pesos: no hay forma de señalar "esta
  respuesta viene de este documento", algo que el equipo de recepción
  necesita para confiar en el sistema.
- **Volumen de datos.** El fine-tuning rinde con datasets grandes y
  consistentes. Aquí hablamos de 10-12 documentos fuente: insuficiente para
  un fine-tuning útil, perfectamente suficiente para un índice RAG.
- **Coste y recursos.** Fine-tuning, incluso eficiente (LoRA/QLoRA), requiere
  GPU y tiempo de los que este prototipo no dispone ni necesita. RAG con
  modelos locales vía Ollama corre en hardware modesto.

## Consecuencias

- La calidad de las respuestas depende directamente de la calidad del
  chunking y del retrieval, no solo del modelo generador — de ahí que el
  chunking diferenciado por tipo de documento (ver estructura del proyecto)
  sea una pieza central, no un detalle menor.
- El sistema necesita un umbral de confianza explícito para decidir cuándo
  escalar en vez de inventar una respuesta (alucinación), ya que el modelo
  generador no "sabe" qué sabe — eso lo decide la capa de retrieval.
