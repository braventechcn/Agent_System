<p align="center">
  <img src="images/agent-system-banner.svg" alt="Agent System Learning Lab: observe, decide, act, and learn" width="100%">
</p>

# Agent System Learning Lab

<p align="center"><strong>Build an agent. Watch it decide. Trace what actually runs.</strong></p>
<p align="center">🧪 3 runnable labs &nbsp;·&nbsp; 🧭 7-module roadmap &nbsp;·&nbsp; 🔄 Actively updated / 持续更新中</p>
<p align="center"><a href="#choose-a-lab">Choose a lab</a> · <a href="#learning-roadmap">Explore the roadmap</a> · <a href="#quick-start">Quick start</a></p>

Follow an agent from a simple room-cleaning policy to LLM tool decisions and a virtual phone connected through local functions, REST, and MCP. Each completed module pairs runnable Python with an experiment guide. The detailed guides and code comments are primarily in Chinese.

## Choose a lab

> [!TIP]
> Start with **01** to see the agent–environment loop without an LLM. Jump to **02** to inspect function calls, then use **03** to compare tool connection paths.

| 🧹 01 · Agent fundamentals | 📚 02 · LLM agent loop | 📱 03 · External capabilities |
| --- | --- | --- |
| Separate an agent's **chosen action** from the environment's **execution**. Compare cleaning policies and costs across six rooms. | Inspect the model's **function-call requests**, Python's tool execution, and the results returned to the model. | Run the same virtual phone task through **local functions**, **REST API**, and **MCP**. |
| [Experiment guide](00_agent_system_basics/README.md) · [Main code](00_agent_system_basics/cleaning_agent.py) | [Experiment guide](01_llm_agent_and_toolcalling/README.md) · [Main code](01_llm_agent_and_toolcalling/agent_loop.py) · [Trace report](01_llm_agent_and_toolcalling/instruction_tool_choice_report.md) | [Experiment guide](02_external_capabilities/README.md) · [Main code](02_external_capabilities/agent.py) |

## Learning Roadmap

![Agent system learning roadmap, from basic principles to reliable autonomous execution](images/Agent学习路线图.png)

The roadmap starts with the agent–environment loop: **observe → decide → act → receive feedback**. Modules 03–05 develop complementary capabilities: connecting tools, organizing information, and planning work. Module 06 brings those capabilities into an observable runtime, while Module 07 evaluates and improves the resulting system. These topics reinforce one another; the diagram is a learning map, not a strict dependency graph.

| Module | Topic | What the experiments cover | Entry points | Status |
| --- | --- | --- | --- | --- |
| 01 | 🧹 Agent fundamentals | Observation, actions, environment state, policies, and action costs in a six-room cleaning agent. | [Guide](00_agent_system_basics/README.md) · [Main code](00_agent_system_basics/cleaning_agent.py) | 🟢 Live |
| 02 | 📚 LLM decisions and the agent loop | Responses API function calls, tool execution, feedback, and the effect of instructions and `tool_choice`. | [Guide](01_llm_agent_and_toolcalling/README.md) · [Main code](01_llm_agent_and_toolcalling/agent_loop.py) | 🟢 Live |
| 03 | 📱 Tools, APIs, function calling, and MCP | Three ways to connect the same virtual phone capabilities: local Python functions, REST API, and MCP. | [Guide](02_external_capabilities/README.md) · [Main code](02_external_capabilities/agent.py) | 🟢 Live |
| 04 | 🧠 Context, sessions, memory, and RAG | Managing conversation state, retrieving relevant information, and grounding answers in retrieved evidence. | — | 🟣 Planned |
| 05 | 🧩 Planning, reflection, and skills | Breaking down tasks, revising plans from feedback, and reusing procedures. | — | 🟣 Planned |
| 06 | ⚙️ Harness and task runtime | Coordinating execution, state, limits, and monitoring around an agent. | — | 🟣 Planned |
| 07 | 🛡️ Verification, evaluation, and reliability | Checking outcomes, measuring performance, handling failures, and improving robustness. | — | 🟣 Planned |

The roadmap numbers describe the learning sequence. The existing code directories use `00`, `01`, and `02`; the entry points above lead to their guides and main scripts.

## Inside the live labs

### 🧹 01 · Agent fundamentals

The [six-room cleaning agent](00_agent_system_basics/README.md) separates an agent's chosen action from the environment's execution of that action. It compares a basic policy with a minimum-cost policy and checks 100 randomly selected initial states for completion, valid actions, and bounded execution.

### 📚 02 · LLM decisions and the agent loop

The [library agent](01_llm_agent_and_toolcalling/README.md) lets a model request tools to locate books, check availability, and retrieve loan policies. Python validates and executes each request, returns the result, and calls the model again. A [run comparison report](01_llm_agent_and_toolcalling/instruction_tool_choice_report.md) records how different instructions and tool-choice settings affected actual API responses and tool calls.

### 📱 03 · External capabilities

The [virtual phone lab](02_external_capabilities/README.md) exposes calendar and note operations through three backends while keeping the agent's task comparable. Its diagrams and traces show where function calling ends, where Python executes work, and how REST and MCP requests travel between processes.

## Coming next

- **🧠 04 · Context and memory:** Compare an agent that sees only the current request with one that carries session state and retrieves relevant records. Inspect what enters the model context and how retrieved evidence supports an answer.
- **🧩 05 · Planning and skills:** Give an agent a multi-step task, make its plan visible, and examine how feedback changes later steps. Extract a repeatable procedure into a reusable skill.
- **⚙️ 06 · Harness and runtime:** Put the agent inside a controlled execution loop with explicit state, limits, logs, and monitoring so a complete run can be inspected and reproduced.
- **🛡️ 07 · Evaluation and reliability:** Define success criteria, build repeatable test cases, and study incorrect tool use, recovery, and self-correction across varied inputs.

These are planned learning objectives, not completed experiments. New code and guides will appear here as each module is built.

## Quick start

Create a virtual environment if you do not already have one, then run the first experiment from the repository root:

```bash
python3 -m venv .venv
.venv/bin/python 00_agent_system_basics/cleaning_agent.py
```

The LLM experiments require dependencies and an API key. Install the requirements for the module you want to run, copy the example configuration, and set your own `OPENAI_API_KEY` and `OPENAI_MODEL` in the local `.env` file:

```bash
.venv/bin/python -m pip install -r 01_llm_agent_and_toolcalling/requirements.txt
test -f .env || cp .env.example .env
.venv/bin/python 01_llm_agent_and_toolcalling/agent_loop.py baseline --trace
```

The virtual phone lab has [additional dependencies and setup steps](02_external_capabilities/README.md), including separate local services for its REST and MCP backends. The `.env` file and `.venv` directory are ignored by Git. Follow each module's README for its full setup, exercises, and expected observations.
