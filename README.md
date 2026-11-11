<p align="center">
  <img src="images/agent-system-banner.svg" alt="Agent System Learning Lab: observe, decide, act, and learn" width="100%">
</p>

<p align="center"><strong>Build an agent. Watch it decide. Trace what actually runs.</strong></p>
<p align="center">🧪 7 runnable labs &nbsp;·&nbsp; 🧭 7-module basics track &nbsp;·&nbsp; 🔄 Work in progress / 持续更新中</p>
<p align="center"><a href="https://braventechcn.github.io/Agent_System/"><strong>🌐 Open the learning portal</strong></a> · <a href="https://github.com/braventechcn/Agent_System"><strong>View source on GitHub</strong></a></p>
<p align="center"><a href="#learning-roadmap">Learning roadmap</a> · <a href="#study-notes">Study notes</a> · <a href="#choose-a-lab">Choose a lab</a> · <a href="#inside-the-live-labs">Inside the labs</a> · <a href="#upcoming-projects">Upcoming projects</a> · <a href="#quick-start">Quick start</a></p>

Explore agent systems through seven runnable Python labs, from a six-room cleaner to a daily focus planner and its reliability evaluation. This is the current Agent basics track; more notes, topics, and projects will follow. The detailed guides and code comments are primarily in Chinese.

## Learning Roadmap

![Agent system learning roadmap, from basic principles to reliable autonomous execution](images/Agent学习路线图.png)

The roadmap starts with the agent–environment loop: **observe → decide → act → receive feedback**. Modules 03–05 develop complementary capabilities: connecting tools, organizing information, and planning work. Module 06 brings those capabilities into an observable runtime, while Module 07 evaluates and improves the resulting system. These topics reinforce one another; the diagram is a learning map, not a strict dependency graph.

| Module | Topic | What the experiments cover | Entry points | Status |
| --- | --- | --- | --- | --- |
| 01 | 🧹 Agent fundamentals | Observation, actions, environment state, policies, and action costs in a six-room cleaning agent. | [Guide](00_agent_system_basics/README.md) · [Main code](00_agent_system_basics/cleaning_agent.py) | 🟢 Live |
| 02 | 📚 LLM decisions and the agent loop | Responses API function calls, tool execution, feedback, and the effect of instructions and `tool_choice`. | [Guide](01_llm_agent_and_toolcalling/README.md) · [Main code](01_llm_agent_and_toolcalling/agent_loop.py) | 🟢 Live |
| 03 | 📱 Tools, APIs, function calling, and MCP | Three ways to connect the same virtual phone capabilities: local Python functions, REST API, and MCP. | [Guide](02_external_capabilities/README.md) · [Main code](02_external_capabilities/agent.py) | 🟢 Live |
| 04 | 🧠 Context, sessions, memory, and RAG | Build context from persisted sessions, selected memories, and retrieved project documentation. | [Guide](03_context_session_memory_rag/README.md) · [Main code](03_context_session_memory_rag/learning_agent.py) | 🟢 Live |
| 05 | 🧩 Planning, reflection, and skills | Discover and load a reusable procedure, plan a meeting, revise after a conflict, and repair a failed reminder. | [Guide](04_planning_reflection_skill/README.md) · [Main code](04_planning_reflection_skill/agent.py) · [Skill](04_planning_reflection_skill/skills/schedule-meeting/SKILL.md) | 🟢 Live |
| 06 | ⚙️ Harness and task runtime | Build a daily focus plan with explicit Task/Run/Turn/Step identities, guarded execution, retry, checkpoints, and state transitions. | [Guide](05_harness/README.md) · [Main code](05_harness/harness.py) | 🟢 Live |
| 07 | 🛡️ Verification, evaluation, and reliability | Audit real run artifacts, evaluate eight failure scenarios, and compare recovery, false completion, and safety outcomes. | [Guide](06_evaluation_reliability/README.md) · [Main code](06_evaluation_reliability/evaluate.py) | 🟢 Live |

The roadmap numbers describe the learning sequence. The code directories use `00` through `06`; the entry points above lead to their guides and main scripts.

## Study Notes

The linked Notion notes are **still being written and revised**. They currently accompany modules 01–06, but their coverage is not final; the Harness note in particular will continue to grow. Module 07 has a self-contained lab guide while its separate study note is pending. Return to the code and traces to test each idea.

| Module | Study notes | Lab guide |
| --- | --- | --- |
| 01 · Agent fundamentals | [Agent 基础 · Agent 与 LLM Agent](https://sphenoid-rhodium-72f.notion.site/Agent-Agent-LLM-Agent-40d9d02716b6802682e9c9ed6b4ba43c) | [Six-room cleaning agent](00_agent_system_basics/README.md) |
| 02 · LLM agent loop | [Agent 基础 · Agent 与 LLM Agent](https://sphenoid-rhodium-72f.notion.site/Agent-Agent-LLM-Agent-40d9d02716b6802682e9c9ed6b4ba43c) | [Library agent](01_llm_agent_and_toolcalling/README.md) |
| 03 · External capabilities | [Agent 基础 · Tool、API、Function Calling 与 MCP](https://sphenoid-rhodium-72f.notion.site/Agent-Agent-Tool-API-Function-Calling-MCP-4109d02716b680f4bb5cc93f9383b68f) | [Virtual phone](02_external_capabilities/README.md) |
| 04 · Context and memory | [Agent 基础 · Context、Session、Memory 与 RAG](https://sphenoid-rhodium-72f.notion.site/Agent-Agent-Context-Session-Memory-RAG-4109d02716b680a8a3f5c6482bf87564) | [Study assistant](03_context_session_memory_rag/README.md) |
| 05 · Planning and skills | [Agent 基础 · Planning、Reflection 与 Skill](https://sphenoid-rhodium-72f.notion.site/Agent-Agent-Planning-Reflection-Skill-4109d02716b680a68216c1bfb3f033da) | [Virtual meeting](04_planning_reflection_skill/README.md) |
| 06 · Harness and task runtime | [Agent 基础 · Harness 与任务运行机制](https://sphenoid-rhodium-72f.notion.site/Agent-Harness-4139d02716b68084925ffe5251428ac7?source=copy_link) | [Daily Focus Planner](05_harness/README.md) |
| 07 · Evaluation and reliability | 📝 To be added / 待更新 | [Reliability diagnosis](06_evaluation_reliability/README.md) |

Notion controls access to these pages. Repository links do not change their sharing permissions; readers need the pages to be published or shared with them.

## Choose a lab

Follow **01 → 07** in order, or pick the topic you want to explore.

<table align="center" width="92%">
  <thead>
    <tr>
      <th align="center" width="8%">Step</th>
      <th align="center" width="23%">Lab</th>
      <th align="left" width="54%">Focus</th>
      <th align="center" width="15%">Open</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td align="center">01</td>
      <td align="center">🧹 Agent fundamentals</td>
      <td>Observe room state, choose and execute cleaning actions, then compare a simple policy with a minimum-cost policy across six rooms.</td>
      <td align="center"><a href="00_agent_system_basics/README.md">Guide</a> · <a href="00_agent_system_basics/cleaning_agent.py">Code</a></td>
    </tr>
    <tr>
      <td align="center">02</td>
      <td align="center">📚 LLM agent loop</td>
      <td>Trace the model's function-call requests, Python's tool execution, feedback to the model, and how instructions affect the loop.</td>
      <td align="center"><a href="01_llm_agent_and_toolcalling/README.md">Guide</a> · <a href="01_llm_agent_and_toolcalling/agent_loop.py">Code</a></td>
    </tr>
    <tr>
      <td align="center">03</td>
      <td align="center">📱 Tool integration</td>
      <td>Connect one virtual phone task through local Python functions, REST API, and MCP; inspect where each tool request travels.</td>
      <td align="center"><a href="02_external_capabilities/README.md">Guide</a> · <a href="02_external_capabilities/agent.py">Code</a></td>
    </tr>
    <tr>
      <td align="center">04</td>
      <td align="center">🧠 Context &amp; memory</td>
      <td>Build a study assistant's model input from session history, saved preferences, and retrieved project guides; inspect the resulting context.</td>
      <td align="center"><a href="03_context_session_memory_rag/README.md">Guide</a> · <a href="03_context_session_memory_rag/learning_agent.py">Code</a></td>
    </tr>
    <tr>
      <td align="center">05</td>
      <td align="center">🧩 Planning &amp; skills</td>
      <td>Discover and load a reusable Skill, plan a meeting, diagnose a calendar conflict and a failed reminder, then verify the repaired result.</td>
      <td align="center"><a href="04_planning_reflection_skill/README.md">Guide</a> · <a href="04_planning_reflection_skill/agent.py">Code</a></td>
    </tr>
    <tr>
      <td align="center">06</td>
      <td align="center">⚙️ Agent Harness</td>
      <td>Use the Daily Focus Planner to trace Task, Run, Turn, and Step; validate actions, retry failures, and resume from a checkpoint.</td>
      <td align="center"><a href="05_harness/README.md">Guide</a> · <a href="05_harness/harness.py">Code</a></td>
    </tr>
    <tr>
      <td align="center">07</td>
      <td align="center">🛡️ Evaluation &amp; reliability</td>
      <td>Audit completed runs, inject faulty decisions and tool failures, compare self-correction with repetition, and generate a diagnosis report.</td>
      <td align="center"><a href="06_evaluation_reliability/README.md">Guide</a> · <a href="06_evaluation_reliability/evaluate.py">Code</a></td>
    </tr>
  </tbody>
</table>

## Inside the live labs

### 🧹 01 · Agent fundamentals

The [six-room cleaning agent](00_agent_system_basics/README.md) separates an agent's chosen action from the environment's execution of that action. It compares a basic policy with a minimum-cost policy and checks 100 randomly selected initial states for completion, valid actions, and bounded execution.

### 📚 02 · LLM decisions and the agent loop

The [library agent](01_llm_agent_and_toolcalling/README.md) lets a model request tools to locate books, check availability, and retrieve loan policies. Python validates and executes each request, returns the result, and calls the model again. A [run comparison report](01_llm_agent_and_toolcalling/instruction_tool_choice_report.md) records how different instructions and tool-choice settings affected actual API responses and tool calls.

### 📱 03 · External capabilities

The [virtual phone lab](02_external_capabilities/README.md) exposes calendar and note operations through three backends while keeping the agent's task comparable. Its diagrams and traces show where function calling ends, where Python executes work, and how REST and MCP requests travel between processes.

### 🧠 04 · Context, Session, Memory & RAG

The [study assistant](03_context_session_memory_rag/README.md) retrieves passages from the project's own guides, keeps session history and reusable preferences in SQLite, and prints the exact context assembled for each model call. Its experiments compare answers with and without history, memory, or retrieved evidence.

### 🧩 05 · Planning, Reflection & Skill

The [virtual meeting lab](04_planning_reflection_skill/README.md) turns a scheduling goal into an explicit plan, injects a calendar conflict and a reminder failure, and traces how feedback changes the next action. Its [sample Skill](04_planning_reflection_skill/skills/schedule-meeting/SKILL.md) exposes a short name and description for discovery, then loads the meeting procedure only when it applies. The Skill guides decisions; Python still executes calendar operations and verifies the saved result. Compare a reproducible offline run with an optional real LLM planner.

### ⚙️ 06 · Harness and task runtime

The [Daily Focus Planner](05_harness/README.md) turns a graduate student's and AI engineer's tasks into a daily plan. Its Harness tracks Task/Run/Turn/Step, enforces state transitions and budgets, guards tool execution, logs each step, and resumes after a pause. Its Markdown plan is useful beyond the experiment; an optional LLM can replace the deterministic decider.

### 🛡️ 07 · Verification, Evaluation & Reliability

The [reliability diagnosis lab](06_evaluation_reliability/README.md) evaluates the real Daily Focus Planner across eight deterministic scenarios. It checks run artifacts independently, catches false completion, compares error feedback with repeated mistakes, and reports how retry and resume affect outcomes and cost.

<a id="upcoming-projects"></a>
## What's next · 待更新

The seven labs form the **current Agent basics track**. The study notes are still in progress, and the existing guides and experiments may be refined as those notes develop. The next projects will take these ideas into longer, more realistic workflows:

### 🔁 Self-Evolving Agent · 自进化 Agent — Planned

What if an Agent could learn from a failed run and propose a better version of its own workflow? This project will let an Agent inspect traces, suggest changes to prompts, tools, or Skills, and test each candidate against a fixed evaluation set. Only improvements that survive regression and safety checks will be kept, so every step of its “evolution” has evidence you can inspect and reproduce.

### 📝 Research Rebuttal Agent · 论文审稿与回复智能体 — Planned

Turn a dense set of reviewer comments into a clear research action plan. The Agent will group concerns, trace each one to claims and evidence in the paper, plan and run targeted experiments, then draft a point-by-point rebuttal with links to the resulting data. The goal is a reviewable path from criticism to experiment to response, with the researcher checking the evidence and approving the final wording.

### ⚡ Jev Decision Model Research · Jev 决策模型研究 — Planned

Can a smaller decision model handle an Agent's clear-cut choices while an LLM focuses on open-ended work? This research track will test Jev-style decisions for tool routing, next-step selection, and when to ask the LLM for help. We will compare task success, latency, cost, and confidence calibration on recorded Agent runs, then make the decision and fallback traces visible. The aim is to discover where this division of work helps and where it fails, with measured results rather than assumed speedups. See the [JevAgentHarness research paper](https://arxiv.org/abs/2610.21412) for background.

More Agent topics and runnable projects will be linked here as they become available.

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

To explore Planning, Reflection, and Skill without an API call, run:

```bash
.venv/bin/python 04_planning_reflection_skill/agent.py
```

The [module guide](04_planning_reflection_skill/README.md) shows how to compare the initial plan, reflection, Skill loading, and the real LLM mode.

To build a local daily task plan and inspect a resumable Harness, run:

```bash
.venv/bin/python 05_harness/harness.py start --fail-once
```

The [Harness guide](05_harness/README.md) explains the generated brief, event log, checkpoint, and optional LLM mode.

To run the offline reliability suite and inspect its report:

```bash
.venv/bin/python 06_evaluation_reliability/evaluate.py suite
```
