# 0012 — Nuevo tipo de documento "referencias" (tablas de consulta)

## Contexto

`mapeo_conceptos_facturacion.md` no encaja en ninguno de los dos tipos de
documento existentes: no es un procedimiento paso a paso (no tiene
"Resumen rápido" / "Procedimiento detallado", y su bloque de metadatos usa
claves distintas — "Última revisión" y "Responsable de mantener
actualizado", no "Categoría" / "Última actualización" / "Validado por").
Tampoco es exactamente un directorio de contactos ni un inventario de
ubicaciones, aunque comparte su misma forma estructural real: título,
secciones H2, una tabla markdown por sección, una sección final de notas.

Forzarlo dentro de la plantilla de procedimientos habría sido contraproducente: la tabla
es justo lo que lo hace útil (una recepcionista busca "¿qué concepto uso
para X?", no sigue una secuencia de pasos), y convertirla en viñetas de
"Resumen rápido" habría sido una transformación con pérdida, no un cambio
de formato.

## Decisión

Se añade un cuarto tipo de documento, `"referencias"`, con su propia
carpeta (`docs/referencias/`) y su propio perfil de chunking en
`settings.yaml`, pero reutilizando **el mismo** `chunk_table_document()`
que ya usan `directorios` e `inventarios` — la lógica de chunking (tabla
por sección H2, fila con datos reales = un chunk, viñetas como fallback
para secciones sin tabla) es exactamente la misma; solo cambia el
propósito semántico de la carpeta y, por las filas más largas de este
documento concreto, el `chunk_size`.

`chunk_size` de `referencias` se fija en 450 (frente a 200 de
directorios/inventarios), calibrado empíricamente: las filas reales de
`mapeo_conceptos_facturacion.md` miden 358-369 caracteres, porque tienen 5
columnas de texto libre en vez de 2-3 columnas cortas tipo nombre/teléfono.
Con 200, cada fila se partía en 2-3 chunks y el retrieval podía devolver
solo una mitad de la fila (p. ej. "cuándo aplica" sin el "concepto a
utilizar"), perdiendo precisión justo en el tipo de pregunta para el que
existe este documento.

## Razonamiento

- **Por qué un cuarto doc_type y no meter esto dentro de "directorios".**
  Aunque la lógica de chunking es idéntica, la carpeta "directorios" debe
  seguir significando "directorio de contactos" para quien mantenga el
  proyecto después — meter ahí una tabla de conceptos de facturación sería
  confuso a futuro, aunque hoy funcionara. El coste de un doc_type nuevo es
  bajo (cuatro líneas en config.py, una entrada en settings.yaml) frente al
  coste de una carpeta con un nombre que ya no describe lo que contiene.
- **Por qué un chunk_size distinto solo para referencias, sin tocar
  directorios/inventarios.** Esos dos ya están validados con datos reales y
  funcionando — cambiar su chunk_size de forma especulativa para
  "unificar" habría sido un riesgo sin beneficio. Cada doc_type tiene su
  propio perfil en `settings.yaml` precisamente para que esto sea posible
  sin tocar código ni arriesgar lo que ya funciona.
- **Por qué se corrigió el aviso silencioso en el mismo cambio.** Al probar
  `mapeo_conceptos_facturacion.md` se descubrió que una sección H2 sin
  tabla NI viñetas (un párrafo en prosa normal) generaba 0 chunks sin
  ningún log — a diferencia de una tabla vacía de plantilla, que sí avisa
  ("no tiene filas con datos reales"). Es el mismo principio que ya regía
  el resto del proyecto (nunca fallar en silencio): se corrigió en el mismo
  chunker que motivó encontrarlo, no se aplazó a un cambio aparte.

## Consecuencias

- Cualquier documento de consulta directa futuro (tablas de equivalencias,
  mapeos, listas de referencia que no son ni procedimiento ni contacto ni
  inventario) tiene ya dónde vivir: `docs/referencias/`, sin necesitar más
  cambios de infraestructura.
- Si una sección de un futuro documento de `referencias` está en prosa
  narrativa y se quiere que se indexe, hay que convertirla a viñetas — el
  chunker ahora avisa de esto con claridad en vez de descartarla en
  silencio, pero sigue sin "entender" prosa libre.