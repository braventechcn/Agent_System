# Agent System 学习实验

这个项目通过可运行的 Python 小实验学习 Agent：从环境中的观察、决策和执行，逐步走向 LLM 工具调用与 Agent Loop。每个章节都有独立的说明和代码。

## 学习路线图

![Agent 学习路线图：从基本原理、LLM 工具调用，到 Context、Planning、Harness 与评估](images/Agent学习路线图.png)

[查看原尺寸路线图](images/Agent学习路线图.png)

路线图展示了七个学习主题，以及 Agent 与环境之间“感知 → 决策 → 行动 → 反馈”的循环。当前项目已实现前三个主题的实验；图中的后续主题可作为继续扩展的方向。

## 已实现的实验

| 章节 | 内容 | 入口 |
| --- | --- | --- |
| 01 Agent 基本原理 | 六房间清扫 Agent；比较基础策略和最低成本策略，并随机验证 100 组初始状态。 | [实验说明](00_agent_system_basics/README.md) · [代码](00_agent_system_basics/cleaning_agent.py) |
| 02 LLM Agent 的决策与执行机制 | 用 Responses API 实现图书馆工具调用循环，观察模型请求、Python 执行和结果反馈。 | [实验说明](01_llm_agent_and_toolcalling/README.md) · [代码](01_llm_agent_and_toolcalling/agent_loop.py) · [运行对照报告](01_llm_agent_and_toolcalling/instruction_tool_choice_report.md) |
| 03 Agent 外部能力连接 | 虚拟手机日历与备忘录；比较本地函数、直接 REST API 与本地 MCP 三条工具接入路径。 | [实验说明](02_external_capabilities/README.md) · [Agent Loop](02_external_capabilities/agent.py) |

运行命令和环境配置见各章节 README。项目根目录的 `.venv` 用作 Python 虚拟环境；涉及真实模型调用的实验需要在本地 `.env` 中配置可用的 API key 和模型。
