# Setup and Run Guide

UAV Pilot Assistant — the steps needed to run the project from scratch.

## Requirements

- **Python 3.10+** (the core system uses only the standard library — NO extra
  installation REQUIRED).
- LLM mode is **optional**; if it is not set up, the system automatically falls
  back to the offline **rule-based** parser.

## 1. Command-line assistant (REPL)

```bash
cd IHA-LLM-Pilot-Assistant
python main.py            # rule-based (offline) mode — no setup needed
python main.py --llm      # LLM mode (see step 4)
```

Type commands in natural language (Turkish): `20 metreye kalk` ("take off to
20 m"), `12,23 noktasını 10 m çapında dolaşıp gözlemle` ("circle and observe
point 12,23 with a 10 m diameter"), `eve dön` ("return home"), `şarj et`
("recharge"). Type `harita` for the map and `exit` to quit.

## 2. Live web dashboard (map + animation + voice)

```bash
python web_app.py                 # http://127.0.0.1:8000
python web_app.py --port 8080     # different port
python web_app.py --llm           # with LLM
```

Open `http://127.0.0.1:8000` in **Chrome/Edge**. On the left is a live tactical
radar (step-by-step animation); on the right are telemetry + the command console
and chat history. Use 🎙 for **voice commands** and 🔊 for **spoken replies**
(microphone permission required).

## 3. Tests and showcase

```bash
python test_scenarios.py             # 23 scenarios + 8 original-feature tests
python test_llm_scenarios.py         # scores 42 human-style scenarios (rule-based)
python test_llm_scenarios.py --llm   # measures the same set with the LLM (comparison)
python demo_showcase.py              # 8-block capability showcase
python demo_showcase.py --pause      # presentation mode (waits for Enter on each command)
```

All mission records are written to `logs/mission_log.csv` and `.json`.

## 4. (Optional) Connecting a real LLM

The `--llm` flag uses the first reachable provider; if none is available it
falls back to rule-based mode.

| Provider | Setup | Environment variable |
|----------|-------|----------------------|
| **Ollama** (local, free) | `ollama serve` + `ollama pull qwen2.5` | `OLLAMA_HOST` |
| **Anthropic** | `pip install anthropic` | `ANTHROPIC_API_KEY` |
| **OpenAI** | `pip install openai` | `OPENAI_API_KEY` |

Provider: `UAV_LLM_PROVIDER=auto|ollama|anthropic|openai`, model: `UAV_LLM_MODEL`.
The safety layer works independently of LLM mode; if the LLM produces untrusted
output, the system automatically falls back to the rule-based parser.

## Project structure

```
├── README.md                # project overview and structure
├── SETUP.md                 # this file
├── main.py                  # command-line REPL
├── web_app.py               # live web dashboard (map + animation + voice)
├── test_scenarios.py        # scenario + original-feature tests
├── test_llm_scenarios.py    # human-style evaluation set (rule-based vs LLM)
├── demo_showcase.py         # capability showcase
├── uav_assistant/           # core package
│   ├── simulation.py        # 3D drone simulation, environment, observation orbit
│   ├── safety.py            # safety layer, route planning, energy, fail-safe
│   ├── tools.py             # safe tool functions (single access interface)
│   ├── agent.py             # NLU (rule-based + LLM), mission planning
│   ├── logger.py            # CSV/JSON logging
│   ├── scenario_generator.py # random scenario generator
│   └── visualize.py         # static map (optional)
└── logs/                    # mission_log.csv / .json
```
