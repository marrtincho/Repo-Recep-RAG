# 0007 — Filtro de modo con `$or`, para no excluir directorios/inventarios

## Contexto

ADR 0003 estableció que cada chunk de `procedimientos` lleva metadata
`modo` (directo / explicado / ambos). Los chunks de `directorios` e
`inventarios` no tienen ese campo en absoluto — no es que valga "ambos", es
que la clave no existe.

Una búsqueda en modo directo necesita filtrar los chunks de procedimientos
por `modo in {directo, ambos}`, pero debe seguir pudiendo recuperar
normalmente cualquier chunk de directorios o inventarios (una pregunta como
"¿dónde están las almohadas extra?" no tiene "modo", y no debería verse
afectada por el filtro).

## Decisión

El filtro de modo se construye como:

```python
{
    "$or": [
        {"doc_type": {"$ne": "procedimientos"}},
        {"modo": {"$in": [modo_actual, "ambos"]}},
    ]
}
```

Es decir: "o no es un procedimiento, o su modo coincide" — nunca un filtro
plano `{"modo": {"$in": [...]}}` aplicado a toda la colección.

## Razonamiento

- **Filtrar por una clave de metadata que no existe en un documento excluye
  ese documento en ChromaDB** (igual que en SQL filtrar por una columna nula
  con una condición de igualdad no la matchea). Un filtro plano de `modo`
  haría desaparecer silenciosamente todos los chunks de directorios e
  inventarios de cualquier búsqueda en modo directo o explicado — un
  resultado muy distinto del esperado, y difícil de detectar sin pensar
  explícitamente en este caso.
- **La alternativa de añadir `modo: "ambos"` a todos los chunks de
  directorios/inventarios se descartó** porque mezclaría un concepto que
  pertenece exclusivamente a la capa de generación de procedimientos
  (ver ADR 0003) con tipos de documento que no tienen ese concepto en
  absoluto — añadiría una metadata sin significado real solo para evitar un
  `$or`, complejidad real a cambio de evitar una construcción de filtro que
  ChromaDB ya soporta de forma nativa.

## Consecuencias

- Cualquier función que construya este filtro (`build_mode_filter` en
  `src/retrieval/search.py`) es el único lugar que debe conocer esta regla.
  El resto del sistema solo pasa un `mode` y recibe un `where` ya correcto.
- Si en el futuro se añaden más tipos de documento sin campo `modo`, no
  hace falta tocar este filtro: la condición `doc_type != "procedimientos"`
  ya los deja pasar sin filtrar, sin necesidad de enumerarlos explícitamente.
