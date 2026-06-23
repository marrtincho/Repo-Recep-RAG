# 0011 — Reversión del filtro de modo en retrieval (corrección de ADR 0007)

## Contexto

Una prueba real con Ollama expuso un problema serio: en modo "directo", el
asistente respondía leyendo viñetas sueltas del documento sin explicar nada,
y entraba en un bucle repitiendo la misma pregunta de aclaración varias
veces seguidas hasta acabar escalando de todos modos. Transcripción real:

> un cliente llego y no encuentro la reserva
> → Pide la identificación del cliente así como una confirmación de reserva
> si la tuvo. (fuente: Reserva no encontrada.md)
> y luego que mas?
> → Busca en Ulysse no solo en llegadas... (fuente: Reserva no encontrada.md)
> [...]
> → ¿El cliente ya ha hecho el check-in o todavía está en proceso?
> [el usuario ya había contestado esto tres veces]
> → No tengo información suficiente sobre esto, consulta con tu responsable.

El diagnóstico encontró tres causas distintas, no una sola:

1. La instrucción de aclaración (ADR 0010) incluía un ejemplo concreto
   ("si el huésped ya llegó o no") que el modelo parafraseaba casi literal
   como pregunta real, sin importar si tenía sentido para el documento
   actual — de ahí "¿el cliente ya llegó al hotel?" en un procedimiento que
   no tiene esa rama en absoluto.
2. No había instrucción explícita de no repetir una pregunta ya contestada
   en la conversación.
3. **La causa de fondo**: el filtro de modo en retrieval (ADR 0007) hacía
   que en modo "directo" el retrieval únicamente pudiera devolver chunks
   con `modo` igual a "directo" o "ambos" — es decir, "Procedimiento
   detallado" (modo="explicado") quedaba completamente excluido. El modelo
   no estaba decidiendo no explicar: no tenía acceso a la explicación. Solo
   recibía viñetas de "Resumen rápido", a menudo fragmentadas entre varios
   chunks por el solape del splitter, así que cada turno solo tenía uno o
   dos fragmentos sueltos en su contexto — de ahí la sensación de "buscador
   de texto con más pasos" que describió el usuario.

## Decisión

Se revierten dos piezas y se corrige una tercera:

1. **El retrieval ya no filtra por modo.** `build_mode_filter()` se elimina
   de `src/retrieval/search.py`; `retrieve()` pierde el parámetro `mode`.
   La búsqueda trae los chunks más relevantes para la consulta sin importar
   si son "Resumen rápido" o "Procedimiento detallado". El modo sigue
   existiendo, pero ahora controla EXCLUSIVAMENTE cómo se redacta la
   respuesta en `generation` (longitud, nivel de detalle) — nunca qué
   información puede usar el modelo para construirla.
2. **La instrucción de aclaración (ADR 0010) se reescribe** sin el ejemplo
   de dominio concreto, y con una instrucción explícita de no repetir una
   pregunta ya contestada en la conversación previa.
3. **Nueva instrucción de síntesis**, compartida por ambos modos: prohíbe
   copiar frases del contexto tal cual o enumerarlas una por una, y pide
   explicar con palabras propias "como lo haría un compañero con
   experiencia".

## Razonamiento

- **Por qué retirar el filtro en vez de ajustarlo.** Se consideró una
  versión más permisiva (p. ej. incluir igualmente 1 chunk de
  "Procedimiento detallado" aunque el modo fuera "directo"), pero añadir
  más reglas especiales sobre una idea que la evidencia real ya mostró que
  está mal planteada solo pospone el problema. Más información disponible
  para un modelo razonador es, en general, mejor que menos — el riesgo de
  "demasiado contexto" se mitiga con la instrucción de síntesis y con el
  propio `top_k`, no restringiendo de antemano qué puede leer.
- **ADR 0003 (chunking por subsección con metadata `modo`) sigue siendo
  válido.** Lo que se revierte es solo su uso como filtro excluyente en
  retrieval. La granularidad por subsección (un chunk para el resumen, otro
  para el detalle, etc.) sigue aportando precisión de citación y permite
  que el retrieval encuentre el fragmento más relevante entre varios — el
  error fue usar esa misma etiqueta para decidir qué le está permitido ver
  al modelo, no tener la etiqueta en sí.
- **Por qué un ejemplo concreto en una instrucción es arriesgado con
  modelos locales pequeños.** Los modelos de 7-8B corriendo en local son
  notablemente más propensos que un modelo grande a tratar un ejemplo
  ilustrativo como una plantilla literal a repetir, en vez de generalizar
  el principio detrás de él. La lección general — evitar ejemplos
  concretos de dominio en instrucciones de prompt que deban generalizar —
  aplica a cualquier instrucción futura que se añada a este prompt.
- **Por qué la instrucción de síntesis es independiente del fix de
  retrieval.** Aunque el contexto ahora es más completo, nada impide que un
  modelo perezoso siga copiando texto tal cual si tiene esa opción
  disponible — había que pedírselo explícitamente, no solo dárselo.

## Consecuencias

- `retrieve()` ya no acepta `mode`; `ask()` en orchestration ya no se lo
  pasa. `mode` sigue siendo necesario para `generate_answer()` y
  `build_system_prompt()`, donde ahora cumple su único propósito real.
- El contexto que recibe el modelo en modo "directo" puede ser más largo
  que antes (ya no se descarta nada por modo), lo cual es intencional: se
  prioriza que el modelo tenga lo necesario para sintetizar bien, sobre
  mantener el prompt artificialmente corto.
- Si en el futuro se observa que el modo "directo" sigue sin distinguirse
  lo suficiente del modo "explicado" en la práctica, el ajuste debe hacerse
  en la instrucción de generación (tono, longitud), nunca volviendo a
  filtrar el contexto por modo — esa vía ya se probó y la evidencia real
  mostró que perjudica más de lo que ayuda.
