# 0008 — interaction_id para feedback diferido; gap_log como log derivado

## Contexto

El panel de métricas (sección 6 del plan de acción) registra cada
interacción con un campo "Feedback del usuario" (👍/👎), pero ese feedback no
llega en el momento de generar la respuesta: el usuario lo da después, al
pulsar un botón en la interfaz, una vez ya ha leído la respuesta. Además, el
plan pide un `gap_log.csv` separado que rastree específicamente las
preguntas escaladas, para medir "cuántos huecos de documentación se
identifican por semana".

## Decisión

Cada interacción registrada en `metrics/feedback_log.csv` recibe un
`interaction_id` (UUID) en el momento de loguearla, con `feedback` inicial
`"sin_evaluar"`. La interfaz guarda ese id junto a la respuesta mostrada; al
pulsar 👍/👎, se llama a `record_feedback(interaction_id, ...)`, que localiza
la fila por id y actualiza solo el campo `feedback`.

`metrics/gap_log.csv` es un log derivado: toda interacción con
`resultado == "escalada"` se escribe tanto en `feedback_log.csv` (el
registro completo) como en `gap_log.csv` (solo las escaladas, con menos
columnas). No es una fuente de verdad independiente, es una vista
filtrada persistida para no tener que reprocesar el log completo cada vez
que se quiera consultar específicamente los huecos de documentación.

## Razonamiento

- **Sin un identificador estable, asociar feedback a la interacción correcta
  es ambiguo.** Buscar por texto de pregunta + timestamp aproximado es
  frágil (dos preguntas idénticas seguidas, o feedback que llega con
  retraso) y no escala incluso a bajo volumen. Un UUID generado en el
  momento del registro elimina la ambigüedad por completo.
- **Por qué CSV con reescritura completa, no una base de datos.** El plan ya
  estableció CSV/JSON local como suficiente para el volumen de un prototipo
  de uso interno (ver sección 6). Actualizar una fila reescribiendo el CSV
  completo (leer con pandas, modificar, volver a escribir) es ineficiente a
  gran escala, pero irrelevante a las decenas o cientos de filas que este
  prototipo va a manejar — añadir una base de datos aquí sería complejidad
  sin beneficio real, igual que se argumentó en el ADR 0002 sobre ChromaDB.
- **Por qué duplicar la escalada en gap_log.csv en vez de filtrar
  feedback_log.csv bajo demanda.** El plan pide explícitamente un archivo
  separado para esto (ver estructura del repositorio, sección 4), y tiene
  sentido operativo: quien revisa huecos de documentación semana a semana
  quiere un archivo que solo contenga eso, sin tener que filtrar ni
  explicar la convención cada vez.

## Consecuencias

- `record_feedback` debe fallar con un error claro si el `interaction_id`
  no existe (en vez de fallar en silencio), porque un id que no matchea
  probablemente indica un bug en la interfaz o un log que se rotó/borró
  entre la respuesta y el feedback.
- Si en algún momento el volumen de interacciones crece lo suficiente para
  que reescribir el CSV completo en cada feedback sea un problema de
  rendimiento real, esta decisión debería revisarse — no antes, sin
  evidencia de que haga falta.
