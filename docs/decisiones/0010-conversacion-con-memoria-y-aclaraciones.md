# 0010 — Conversación con memoria y preguntas de aclaración

## Contexto

El sistema original era de un solo turno: cada pregunta se resolvía de
forma aislada, sin memoria de lo ya hablado, y solo tenía dos desenlaces
posibles — responder o escalar a "consulta con tu responsable". Esto
significa que una pregunta incompleta (p. ej. "tengo un overbooking" sin
decir si el huésped ya llegó) se trataba igual que una pregunta sin
documentación: se escalaba, aunque el sistema sí tuviera la información
necesaria una vez se aclarara el detalle que faltaba.

## Decisión

Se añaden dos capacidades, manteniendo intacto el resto de la arquitectura
de seguridad (umbral de confianza + instrucción de no inventar, ver ADR
0006 y la capa de generación):

1. **Memoria de conversación.** `ask()` acepta un `history` (lista de pares
   rol/contenido). Se usa en dos sitios distintos con propósitos distintos:
   - En retrieval, para enriquecer la consulta de búsqueda combinando los
     últimos `max_history_turns` turnos con la pregunta actual (nuevo
     parámetro en `config/settings.yaml`).
   - En generation, como bloque de contexto conversacional en el prompt,
     explícitamente marcado como "solo para entender de qué se habla, los
     HECHOS vienen únicamente del CONTEXTO" — nunca como fuente de verdad.

2. **Preguntas de aclaración.** El system prompt instruye al modelo a
   responder con `"ACLARACIÓN: <pregunta>"` cuando le falta un dato concreto
   que cambiaría la respuesta, en vez de adivinar o escalar de inmediato.
   `generation/pipeline.py` detecta ese prefijo y lo separa en un campo
   `is_clarification`, que se propaga hasta `OrchestrationResult` y se
   registra en métricas como una tercera categoría de resultado
   (`"aclaracion"`), distinta de "respondida" y "escalada".

## Razonamiento

- **Por qué concatenación simple para enriquecer la búsqueda, no una
  llamada extra a Ollama para reescribir la consulta.** Un "query rewriter"
  basado en LLM sería más preciso, pero añade una llamada de generación
  completa antes de cada retrieval — el doble de latencia y de carga sobre
  Ollama en una herramienta donde la rapidez de respuesta en el mostrador
  importa. La concatenación de los últimos turnos es mucho más barata y, en
  la práctica, aporta suficiente señal semántica para que el embedding de
  una pregunta de seguimiento ya no sea ambiguo. Si en uso real resulta
  insuficiente, es una pieza aislada (`_contextualize_query`) que se puede
  sustituir sin tocar el resto del sistema.
- **Por qué un marcador de prefijo y no, por ejemplo, pedirle al modelo una
  respuesta en JSON con un campo `tipo`.** Los modelos locales de 7-8B son
  notablemente menos fiables siguiendo esquemas JSON estrictos que un
  prefijo de texto simple. Un `startswith` tolerante a mayúsculas/minúsculas
  es robusto incluso si el modelo no es perfectamente consistente, y si
  falla la detección, el peor caso es que una aclaración se trate como
  respuesta normal — degradación aceptable, no una excepción no controlada.
- **Por qué las aclaraciones tienen su propia categoría de resultado, en vez
  de contarlas como "respondida" o como "escalada".** Contarlas como
  "respondida" infla artificialmente la tasa de respuesta sin que el
  usuario haya recibido información real todavía. Contarlas como "escalada"
  las mezclaría con huecos genuinos de documentación en el gap log, cuando
  en realidad son parte normal del flujo — de ahí que, a diferencia de una
  escalada, una aclaración nunca se escribe en `gap_log.csv`.
- **Por qué el historial se marca explícitamente como "no es fuente de
  hechos" dentro del propio prompt.** Sin esa instrucción, nada impide que
  el modelo trate su propia respuesta anterior (que podría ser, en el peor
  caso, una alucinación no detectada) como si fuera información verificada
  y construya sobre ella. Mantener la regla "los hechos solo vienen del
  CONTEXTO" intacta, incluso con memoria conversacional, es lo que preserva
  la garantía de no inventar que se construyó en `prompts.py` (capa 2 del
  escalado de dos capas, ver `_SAFETY_INSTRUCTION`).
- **No se le puso límite explícito al número de preguntas de aclaración
  seguidas que el modelo puede hacer.** Se decidió no resolverlo con código
  todavía: limitarlo mal (p. ej. forzar una respuesta tras N aclaraciones)
  podría obligar al sistema a inventar antes que reconocer que necesita más
  información, lo cual sería peor. Si en uso real el modelo encadena
  demasiadas preguntas, es una señal para ajustar el prompt o la
  documentación fuente, no para añadir un límite duro a ciegas.

## Consecuencias

- `compute_summary_metrics` ahora reporta `tasa_aclaracion` además de
  `tasa_respuesta` y `tasa_escalado`; las tres ya no tienen por qué sumar a
  un total con solo dos categorías como antes.
- La interfaz no muestra botones de feedback (👍/👎) para preguntas de
  aclaración, igual que ya no los mostraba para respuestas escaladas: no
  hay una "respuesta" que evaluar como correcta o incorrecta todavía.
- Si en el futuro se quiere medir la calidad de las aclaraciones en sí
  mismas (¿la pregunta que hizo el modelo era la correcta?), haría falta un
  mecanismo de feedback nuevo — no se construyó porque no había una
  necesidad concreta todavía, solo la posibilidad teórica.
