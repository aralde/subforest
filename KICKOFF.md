# Cómo arrancar la sesión

```bash
mkdir subforest && cd subforest
# copiá acá CLAUDE.md, PLAN.md y este KICKOFF.md
git init
claude
```

Pegá esto como primer mensaje en Claude Code:

---

Este repo es **subforest**, una librería MIT en Python que devuelve el sub-bosque estructural inducido por una búsqueda (inspirada en RIT-RAG, arXiv:2610.11370) en vez de chunks sueltos. Leé `CLAUDE.md` y `PLAN.md` completos antes de tocar nada.

Arrancá por **M0**:
1. Repetí en 3–5 líneas los criterios de aceptación de M0 y listá los archivos que vas a crear.
2. Verificá que `subforest` esté libre en PyPI. Si está tomado, frená y avisame.
3. Hacé el scaffold, el modelo de datos, `TreeStore` con ancestros por CTE recursiva, el corpus de fixtures y el CI.
4. Corré `uv run ruff check . && uv run mypy src && uv run pytest`, marcá los checkboxes en `PLAN.md` y hacé commit.

Cuando M0 pase, mostrame un resumen corto y seguí con M1 sin esperar, salvo que una decisión no esté cubierta en `CLAUDE.md` y sea difícil de revertir. Las decisiones chicas anotalas en `docs/decisions.md`.

---

Cuando tengas el repo en GitHub (`aralde/subforest`), agregá el remoto y pusheá después de cada hito.
