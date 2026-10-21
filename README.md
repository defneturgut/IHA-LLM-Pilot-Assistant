# UAV (Drone) LLM Pilot Assistant — Prototype

A prototype UAV pilot assistant built on a large language model (LLM). It is **not** real flight-control software; it is a small, end-to-end working system that demonstrates LLM/agent logic, telemetry awareness, command validation and a safety layer.

**Core safety principle:** the LLM never has access to low-level control (PWM, raw velocity, roll/pitch/yaw). It can only trigger predefined safe functions (`get_telemetry`, `takeoff`, `land`, `return_to_home`, `go_to`, `move`, `get_energy_status`, `avoid_obstacle`), and every command passes through a safety layer before it is executed.

> **Note:** the assistant's natural-language interface understands **Turkish** commands. The examples below show the Turkish input together with its English meaning.

## Architecture

```
Natural-language command
      │
      ▼
┌─────────────────┐   Hybrid NLU (rule-based or optional real LLM)
│  agent.py       │──▶ turns the command into tool calls + multi-step planning
└─────────────────┘
      │
      ▼
┌─────────────────┐   8 safe functions
│  tools.py       │
└─────────────────┘
      │
      ▼
┌─────────────────┐   Rule-based validation (max altitude, battery, state...)
│  safety.py      │──▶ REJECTS unsafe/incomplete commands
└─────────────────┘
      │
      ▼
┌─────────────────┐   3D state: x, y, altitude, mode, battery, in_air
│  simulation.py  │
└─────────────────┘
      │
      ▼
┌─────────────────┐   Records every interaction as JSON + CSV
│  logger.py      │
└─────────────────┘
```

## Modules

| File | Purpose |
|------|---------|
| `uav_assistant/simulation.py` | Simple class-based 3D drone simulation and state management. |
| `uav_assistant/safety.py` | Safety layer: validates tool calls against rules before execution. |
| `uav_assistant/tools.py` | 8 safe tool functions + LLM tool-calling schema. |
| `uav_assistant/agent.py` | Natural-language interface (hybrid NLU) + multi-step mission planning. |
| `uav_assistant/logger.py` | JSON/CSV logging system. |
| `uav_assistant/scenario_generator.py` | Original feature: random scenario generator. |
| `uav_assistant/visualize.py` | Original feature: HTML map of flight path / obstacles / no-fly zones. |
| `demo_showcase.py` | End-to-end capability showcase. |
| `web_app.py` | Original feature: live 2D web dashboard (visual environment in the browser). |
| `main.py` | Interactive command-line interface (REPL). |
| `test_scenarios.py` | 23 natural-language commands + 8 original-feature tests. |
| `test_llm_scenarios.py` | Human-style evaluation set (rule-based vs. LLM). |
| `SETUP.md` | Step-by-step setup and run guide. |

## Installation

Python 3.9+ is enough. **The default (offline) mode needs no external dependencies** — it uses only the standard library.

```bash
git clone https://github.com/defneturgut/IHA-LLM-Pilot-Assistant.git
cd IHA-LLM-Pilot-Assistant
python -m venv .venv            # (optional)
source .venv/bin/activate       # Windows: .venv\Scripts\activate
```

### Real LLM mode (optional)

The system supports three providers, selected with `UAV_LLM_PROVIDER` (default `auto`). Regardless of the provider, the LLM only calls safe functions and the safety layer is always enforced. If no provider is reachable, it automatically falls back to rule-based mode.

**Ollama (local, free, recommended):** no API key required.

```bash
# 1) Install Ollama (https://ollama.com) and pull a model that supports tool calling
ollama pull llama3.1            # or: qwen2.5, mistral
# 2) Run the assistant with Ollama
export UAV_LLM_PROVIDER=ollama  # $env:UAV_LLM_PROVIDER = "ollama"
export UAV_LLM_MODEL=llama3.1   # $env:UAV_LLM_MODEL = "llama3.1"
python main.py --llm
```

**Cloud (optional):**

```bash
pip install anthropic              # or: pip install openai
export ANTHROPIC_API_KEY="..."     # or OPENAI_API_KEY
python main.py --llm
```

Relevant environment variables: `UAV_LLM_PROVIDER` (auto/ollama/anthropic/openai), `UAV_LLM_MODEL`, `OLLAMA_HOST` (default http://localhost:11434).

## Running

```bash
python test_scenarios.py                              # 23 scenarios + 8 original (31 tests)
python main.py                                        # interactive (offline)
python main.py --llm                                  # real LLM
python -m uav_assistant.scenario_generator --n 15     # random scenarios
python demo_showcase.py                               # capability showcase
python web_app.py                                     # live 2D web dashboard -> http://127.0.0.1:8000
```

## Example commands

| Command (Turkish) | Meaning | Result |
|-------------------|---------|--------|
| `durum nedir?` | "what's the status?" | ✅ Explains telemetry in natural language |
| `20 metreye kalk` | "take off to 20 m" | ✅ Safe takeoff |
| `30, 40 noktasına git` | "go to point 30, 40" | ✅ Flies to the given position (go_to) |
| `iniş yap` | "land" | ✅ Lands (if airborne) |
| `eve dön` | "return home" | ✅ Return-to-home + landing |
| `kalk, 30 40 noktasına git, durum bildir ve eve dön` | "take off, go to 30 40, report status and return home" | ✅ Multi-step mission plan |
| `500 metreye kalk` | "take off to 500 m" | ⛔ Exceeds max altitude → rejected |
| `kalkış yap` | "take off" | ❓ Altitude ambiguous → asks for clarification |
| `4 sağa git`, `20 yukarı çık` | "move 4 right", "climb 20 up" | ✅ Directional/relative movement (move) |
| `menzil ne kadar, eve dönebilir miyim` | "what's the range, can I make it home?" | ✅ Energy/range estimate |
| `30 30 noktasına git` (obstacle) | "go to point 30 30" | ⛔ Route crosses an obstacle → rejected |
| `önünde 1 metre engel var` | "obstacle 1 m ahead" | 🛟 Autonomous avoidance (move away) or hover |
| `roll açısını 30'a ayarla` | "set roll angle to 30" | ⛔ Low-level control → rejected |

## Safety rules (safety.py)

- The maximum altitude limit (default **120 m**) cannot be exceeded.
- Takeoff is rejected if the battery is below **20%**.
- Horizontal working area limit for `go_to` and `move` is **±500 m**.
- A move is rejected if its route passes through an **obstacle** or a **no-fly zone**.
- Illogical commands, such as taking off while airborne or landing while on the ground, are rejected.
- For ambiguous commands (no altitude/coordinates) **no assumptions are made**; clarification is requested.
- Low-level control attempts (PWM/roll/pitch/yaw/motor) are always rejected.

## Original features

- **Multi-step mission planning:** multiple tasks in a single sentence ("take off, go, report status, return home") are executed in order, each passing through the safety layer.
- **Battery-based automatic return-to-home suggestion:** when the battery drops below 30%, the agent suggests a safe return home without executing any action.
- **Random scenario generator:** automatically tests the system with different phrasing variations.
- **Accent-insensitive NLU:** Turkish variants such as "çık/cik", "iniş/inis", "dön/don" are recognized the same way.
- **Directional/relative movement (move):** commands like "climb 20 up", "move 4 right", "descend 8" update the position correctly.
- **Obstacles + no-fly zones (geofence):** obstacles/no-fly zones in the simulation; the safety layer checks the movement route and rejects colliding/forbidden routes.
- **Energy/range estimation:** remaining range, cost of returning home and a "can I safely make it home?" calculation (`get_energy_status`).
- **Visual map:** a single-file HTML/SVG map showing the flight path, obstacles, no-fly zones and current position (the `harita` ["map"] command in the REPL).
- **Autonomous obstacle avoidance (avoid_obstacle):** on "obstacle ahead / obstacle appeared", the drone makes a safe autonomous decision — moves away if the obstacle is close, hovers if it is far — and explains its reasoning. Phrases like "1 m obstacle" add a dynamic obstacle.
- **LLM "hallucination" guard + rule-based fallback:** if the LLM returns invalid/made-up output, the system falls back to the deterministic rule-based parser.
- **Advanced LLM integration:** automatic selection of the best installed Ollama model, temperature=0, live state context, argument normalization.
- **Live 2D web dashboard (`web_app.py`):** a visual environment in the browser; as you type commands, the drone, obstacles, no-fly zones and flight path update live, with telemetry + decisions shown. Standard library only.

## Logging

Every interaction is recorded in `logs/mission_log.json` and `logs/mission_log.csv`: timestamp, incoming command, interpreted action, arguments, safety decision, success status, message and current telemetry.

## Test coverage

`test_scenarios.py`: 23 scenarios + 8 original-feature tests (multi-step planning, battery suggestion, directional movement, geofence, energy/range, visual map, and more).
