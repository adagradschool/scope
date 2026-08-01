

# scope

![Scope Dashboard](https://raw.githubusercontent.com/adagradschool/scope/main/docs/assets/hero.png)

**Inicia Claude en sesiones nuevas. Detén la degradación del contexto.**

[![PyPI](https://img.shields.io/pypi/v/scopeai.svg)](https://pypi.org/project/scopeai/)
[![Python](https://img.shields.io/pypi/pyversions/scopeai.svg)](https://pypi.org/project/scopeai/)
[![License](https://img.shields.io/github/license/adagradschool/scope.svg)](https://github.com/adagradschool/scope/blob/main/LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/adagradschool/scope/ci.yml?branch=main)](https://github.com/adagradschool/scope/actions)

> Scope es un **sustrato para crear patrones de orquestación**, no un orquestador en sí mismo. Proporciona primitivas (`spawn`, `wait`, `poll`) y visibilidad: tú construyes la capa de inteligencia.

---

## El Problema

**Tu contexto se está degradando.**

Cada tarea que le das a Claude Code acumula carga: contenido de archivos, intentos fallidos, desviaciones exploratorias. Cuando se activa la compactación, los detalles críticos desaparecen. Tu sesión principal se convierte en un desastre diluido.

```
Main Session Context Over Time:

Start:    [████████████████████████████████████████] 100% relevante
After 3   [████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░] 20% relevante
  tasks:  ↑ lecturas de archivos, callejones sin salida, desviaciones, completados antiguos

After     [██░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░] 5% relevante
compaction: ↑ detalles críticos perdidos en la resumición
```

Esto es **degradación del contexto**. Los flujos de trabajo de sesión única están fundamentalmente rotos.

---

## La Solución

**Genera subagentes con propósito específico y contexto fresco.**

```
With Scope:

Main:     [████████████████████████████████████████] orquestación + resultados únicamente
          ↓ spawn
Subagent: [████████████████░░░░░░░░░░░░░░░░░░░░░░░░] realiza una tarea, devuelve un resumen
          ↑ contexto fresco, tarea enfocada, resultado limpio
```

Cada subagente:
- Comienza con **contexto fresco** (sin carga acumulada)
- Tiene un **propósito único** (sin desviación de alcance)
- Devuelve **solo lo importante** (obtienes el resultado, no el proceso)

Tu sesión principal coordina. Los subagentes ejecutan.

---

## Inicio Rápido (< 5 minutos)

### 1. Instalación (30 segundos)

```bash
# Instalar
uv tool install scopeai

# O ejecutar directamente sin instalar
uvx scopeai
```

### 2. Configuración (1 minuto)

```bash
# Ejecutar configuración (instala hooks, verifica dependencias)
scope setup
```

**Lo que hace esto:**
- Instala los hooks de Claude Code en `~/.claude/settings.json`
- Verifica que `tmux` esté instalado
- Agrega la documentación de Scope para que Claude Code sepa cómo usarlo
- No se necesitan claves API (usa tu autenticación existente de Claude Code)

**Verificar:** Ejecuta `scope` - deberías ver un tablero vacío.

### 3. Primera Sesión (2 minutos)

```bash
# Abrir el tablero de Scope
scope
```

**En el tablero:**
1. Presiona `n` para iniciar una nueva sesión de Claude Code
2. Dale a Claude una tarea de varios pasos de forma natural:
   - "Investiga patrones de autenticación en esta base de código e implementa JWT"
   - "Refactoriza la API para usar async/await"
   - "Agrega pruebas integrales para el módulo de usuario"

**Qué ocurre:**
- Claude analiza la tarea y decide si necesita subagentes
- Para tareas complejas, Claude genera automáticamente subagentes enfocados (investigar, implementar, probar)
- Observa cómo el tablero se actualiza en tiempo real mientras los subagentes inician, ejecutan y completan
- Tu sesión principal se mantiene ligera: solo coordinación y resultados

**No necesitas conocer los comandos `scope spawn`.** Solo habla con Claude de forma natural. El tablero muestra lo que ocurre detrás de escenas.

> **Avanzado:** ¿Quieres control manual? Consulta la sección [Patrones de Orquestación](#example-orchestration-patterns) para el uso de CLI.

### 4. Actualización (cuando quieras)

```bash
# Actualizar a la última versión
scope update

# O instalar una versión específica
scope update 0.1.3
```

**Eso es todo.** Ahora estás orquestando subagentes con visibilidad transparente.

---

## Ejemplos de Patrones de Orquestación

Scope es un protocolo. Aquí hay cómo construir patrones comunes sobre él:

### Secuencial (Cadena de Custodia)

```bash
# Cada tarea depende de la anterior
id1=$(scope spawn "research auth patterns")
scope wait $id1

id2=$(scope spawn "implement auth based on research from session $id1")
scope wait $id2

id3=$(scope spawn "write tests for auth implementation")
scope wait $id3
```

**Patrón:** Pipeline lineal. Cada paso espera al anterior.

---

### Paralelo (Bifurcar-Únir)

```bash
# Generar múltiples tareas independientes
id1=$(scope spawn "audit codebase for security issues")
id2=$(scope spawn "research modern auth patterns")
id3=$(scope spawn "analyze test coverage")

# Esperar a que todas completen
scope wait $id1 $id2 $id3

# Ahora sintetizar resultados
echo "All research complete. Aggregating findings..."
```

**Patrón:** Bifurca múltiples subagentes, únelos cuando todos completen.

---

### DAG (Grafo de Dependencias)

```bash
# Declarar el DAG completo de antemano usando --id y --after
scope spawn "research auth patterns" --id research
scope spawn "audit current codebase" --id audit
scope spawn "implement auth" --id impl --after research,audit
scope spawn "write tests" --id tests --after impl
scope spawn "update docs" --id docs --after impl

# Esperar solo en los nodos hoja—las dependencias se resuelven automáticamente
scope wait tests docs
```

**Patrón:** Grafo acíclico dirigido. `--after` codifica las dependencias. Scope valida el DAG pero no agenda: tu shell se encarga.

**Cómo funciona:**
- `--after research,audit` significa que la sesión `impl` recibe metadatos sobre qué esperar
- **Tu código de orquestación** (bash, o la sesión padre de Claude) aplica la espera
- Scope solo rastrea el estado: no ejecuta un planificador

---

### Map-Reduce

```bash
# Map: Generar N trabajadores
files=$(find src/ -name "*.py")
for file in $files; do
  scope spawn "analyze $file for type errors" --id "worker-$file" &
done

# Reduce: Esperar a todos, agragar resultados
scope wait worker-*
echo "Aggregating type errors from all files..."
cat .scope/sessions/worker-*/result | jq -s 'add'
```

**Patrón:** Genera muchos trabajadores, agraga resultados.

---

### Descomposición Recursiva

Los subagentes pueden generar hijos. Cada hijo obtiene un ID con espacio de nombres.

```bash
# Dentro de la sesión 0, esto crea 0.0
scope spawn "Extract JWT helpers"

# Dentro de la sesión 0.0, esto crea 0.0.0
scope spawn "Parse token format"
```

**Estructura de árbol:**
```
0           ← nivel superior
├ 0.0       ← hijo de 0
│ └ 0.0.0   ← nieto
└ 0.1       ← hijo de 0
```

**Reglas:**
- Una sesión se completa solo cuando todos los hijos completan
- Abortar un padre aborta a todos los descendientes
- Cada sesión es conectable de forma independiente

**Patrón:** Descomposición fractal. Deja que Claude descomponga recursivamente tareas complejas.

---

## Scope es un Sustrato

**Scope NO es un orquestador.** No agenda tareas, gestiona dependencias ni paraleliza automáticamente el trabajo.

**Scope ES un sustrato** que proporciona:
- `spawn` — Inicia un subagente, obtén un ID
- `wait` — Bloquea hasta completar
- `poll` — Verifica estado (no bloqueante)
- Visibilidad — Tablero en tiempo real de todas las sesiones
- Control — Conecta, dirige, aborta en cualquier momento

**Tú construyes la capa de orquestación** usando estas primitivas. Scope es el medio. Tu código (o el razonamiento de Claude) es la inteligencia.

### Por Qué Esto Importa

Otras herramientas (Task, Explore) son orquestadores opacos: deciden cómo paralelizar, cuándo generar, qué pasar entre pasos. Obtienes una caja negra.

Scope te da **bloques de construcción transparentes**. ¿Quieres programación DAG? Codifícalo tú mismo con `--after`. ¿Quieres map-reduce? Genera N subagentes y agraga resultados. ¿Quieres modelo de actores? Cada sesión es un actor.

**El patrón de orquestación es TU código, no el de Scope.**

---

## Interfaz Humana: El Tablero

Mientras Claude usa `spawn`/`wait`/`poll`, tú observas y controlas a través del tablero:

```bash
scope
```

```
┌─ scope ────────────────────────────────────────────────── 3 running ─┐
│                                                                      │
│  ▼ 0   Refactor auth to JWT        ● running   waiting on children   │
│    ├ 0.0  Extract JWT helpers      ● running   editing token.ts      │
│    └ 0.1  Update middleware        ✓ done      ─                     │
│  ▶ 1   Write tests for user module ● running   jest --watch          │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│  n new   ↵ attach   x abort   d hide done                            │
└──────────────────────────────────────────────────────────────────────┘
```

| Tecla | Acción |
|-----|--------|
| `n` | Nueva sesión (abre Claude Code en panel dividido) |
| `enter` | Conectar a la sesión seleccionada |
| `x` | Abortar seleccionada (y descendientes) |
| `j/k` | Navegar |
| `h/l` | Colapsar/expandir |
| `d` | Alternar sesiones completadas |

**Punto clave:** El tablero es una **observación de solo lectura** del estado que reside en `.scope/sessions/`. Scope no orquesta: renderiza.

---

## Scope vs Herramienta Task

Para usuarios de Claude Code que se preguntan por qué no usar los agentes Task/Explore integrados:

| | Herramienta Task | Scope |
|---|---|---|
| **Visibilidad** | Caja negra opaca | Tablero en tiempo real |
| **Intervención** | Ninguna—espera y confía | Conecta, dirige, aborta en cualquier momento |
| **Contexto** | Comparte contexto del padre | Contexto fresco por agente |
| **Paralelismo** | Solo secuencial | Genera muchos en paralelo |
| **Anidación** | Limitada | Jerarquía ilimitada |
| **Depuración** | Solo resultados | Inspección completa de sesión |
| **Filosofía** | Orquestador (con opiniones) | Sustrato (trae tu propia lógica) |

Task es un orquestador con opiniones propias. Scope es un **protocolo transparente** para construir orquestación.

---

## Ejemplo Antes/Después

**Sin Scope (sesión única):**

```
Task 1: "Refactor auth module to use JWT"

Context after completion:
├─ Your original request:           2K tokens
├─ File reads (15 files):          45K tokens  ← bloat
├─ Failed approach 1:              12K tokens  ← bloat
├─ Successful implementation:      18K tokens
├─ Test code:                       8K tokens
└─ Total:                          85K tokens

Result: Implementation works ✓

─────────────────────────────────────────────

Task 2: "Now add rate limiting"

Context before this task:
├─ Compacted summary:              25K tokens  ← auth details lost!
├─ Your new request:                2K tokens
└─ Total available:                27K tokens

Problem: Critical JWT implementation details were summarized away.
Claude has to re-read files and re-explore the auth system.
```

**Con Scope (subagentes orquestados):**

```
Task 1: "Refactor auth module to use JWT"

Main session context:
├─ Your original request:           2K tokens
├─ Orchestration commands:          1K tokens
├─ Subagent results (concise):      5K tokens  ← only the essentials
└─ Total:                           8K tokens

Each subagent runs independently with fresh 200K context.
Main session never sees the 15 file reads, failed attempts, or exploration.

Result: Implementation works ✓ + main session stays lean ✓

─────────────────────────────────────────────

Task 2: "Now add rate limiting"

Main session context:
├─ Full task 1 context:             8K tokens  ← nothing lost!
├─ Your new request:                2K tokens
└─ Total:                          10K tokens

Claude has complete context of JWT implementation via clean results.
No re-reading. No re-exploration. Just forward progress.
```

**La diferencia:** SIN Scope, tu segunda tarea comienza con 27K de contexto fragmentado. CON Scope, comienza con 10K de contexto completo y relevante.

---

## Cómo Funciona

- **Cada sesión** es un proceso real de Claude Code en tmux
- **El estado reside** en `.scope/sessions/` (inspeccionable con `cat`, `tail`, `watch`)
- **Los hooks rastrean la actividad** automáticamente a través del sistema de hooks de Claude Code (PostToolUse, Stop)
- **El tablero** observa `.scope/sessions/` en busca de cambios y se actualiza instantáneamente
- **La anidación** es automática a través de la variable de entorno `SCOPE_SESSION_ID`

**Puedes inspeccionar el estado directamente:**
```bash
cat .scope/sessions/0/task           # ¿Qué está haciendo?
cat .scope/sessions/0/state          # running | done | aborted
tail -f .scope/sessions/0/activity   # Flujo de actividad en vivo
cat .scope/sessions/0/result         # Salida final
```

Todo el kit de herramientas de Unix funciona. **El sistema de archivos es la capa de IPC.**

Consulta [docs/02-architecture.md](docs/02-architecture.md) para detalles técnicos.

---

## Filosofía

### 1. Transparencia sobre magia
Sin cajas negras. El estado del subagente es tu estado. `.scope/sessions/` es legible por todos.

### 2. Control sobre autonomía
La intervención es una característica de primera clase, no una salida de emergencia. Conecta y dirige en cualquier momento.

### 3. Sustrato sobre orquestador
Scope proporciona primitivas. Tú codificas la inteligencia.

### 4. Minimalismo sobre ceremonias
Un solo comando para generar (`scope spawn`). Una sola interfaz para observar (`scope`). Cero configuración para comenzar.

Consulta [docs/00-philosophy.md](docs/00-philosophy.md) para la filosofía de diseño completa.

---

## Cronograma de Integración

**5 minutos:** Instalar → configurar → primera generación → ver resultado
**15 minutos:** Generaciones paralelas → dependencias DAG → dominio del tablero
**30 minutos:** Integración de hooks → descomposición recursiva → flujos de trabajo personalizados

---

## Cuándo NO usar Scope

- **Tareas atómicas únicas** — No generes subagentes para una lectura rápida de archivo o una corrección de una línea. Hazlo en línea.
- **Diálogo estrecho de ida y vuelta** — Si la tarea requiere refinamiento iterativo, manténla en tu sesión principal.
- **Tareas que requieren tu estado en ejecución** — Si el subagente necesita acceso a variables o estado en tu contexto actual, no generes.

**Regla general:** Si la tarea consumiría >30% de tu ventana de contexto, genera. De lo contrario, hazlo tú mismo.

---

## Solución de Problemas

### `tmux: command not found`

Scope requiere tmux para gestionar sesiones en segundo plano.

**Instalar tmux:**
- **macOS:** `brew install tmux`
- **Ubuntu/Debian:** `sudo apt install tmux`
- **Arch:** `sudo pacman -S tmux`

Luego vuelve a ejecutar `scope setup`.

### Hooks no funcionan / Claude no conoce Scope

**Verifica que los hooks estén instalados:**
```bash
cat ~/.claude/settings.json | grep scope
```

Deberías ver los hooks `PostToolUse` y `Stop` apuntando a `scope hook`.

**Solución:**
```bash
scope setup  # Vuelve a ejecutar la configuración para reinstalar los hooks
```

### Sesión atascada en estado "running"

Si una sesión aparece como en ejecución pero Claude se ha bloqueado:

```bash
scope  # Abrir tablero
# Navegar a la sesión atascada y presionar 'x' para abortar
```

O manualmente:
```bash
cat .scope/sessions/0/tmux_session  # Obtener nombre de la sesión tmux
tmux kill-session -t scope-0        # Eliminarla manualmente
```

### Tablero no se actualiza

El tablero observa `.scope/sessions/` en busca de cambios. Si está congelado:

1. Presiona `Ctrl+C` para salir y vuelve a ejecutar `scope`
2. Verifica permisos de archivos: `ls -la .scope/sessions/`
3. Verifica que los hooks estén ejecutándose: `tail -f .scope/sessions/*/activity`

### El subagente no puede encontrar el contexto de la sesión padre

Al usar `--after`, asegúrate de que las sesiones padre hayan escrito sus resultados:

```bash
# Esperar dependencias antes de generar
scope wait research audit
scope spawn "implement based on research + audit" --id impl
```

---

## Requisitos

- Python 3.10+
- tmux
- Claude Code

---

## Licencia

MIT
