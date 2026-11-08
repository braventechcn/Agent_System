# LLM Agent 与工具调用：图书馆 Agent Loop

## 背景：为什么需要 Agent Loop

规则式 Agent 根据预设条件选择动作，任务流程和分支通常由开发者写在代码里。新增需求往往需要调整这些规则。

LLM Agent 则可以结合用户目标与工具返回的信息，动态决定下一步调用哪个工具，以及何时给出回答。

以图书馆为例，用户可能同时问一本书的位置、当前是否可借、借阅期限；如果原书不可借，还希望得到可借的同主题备选。模型无法仅凭训练时的知识知道这些本地数据。程序需要向模型说明有哪些工具；模型返回**工具调用请求**，Python 执行对应函数，再把结果交回模型。这个过程可能重复多轮，直到模型形成回答。

这个过程可以拆成“观察 → 决策 → 执行”：

- 用户问题和工具结果是模型观察到的信息；
- 模型（做决策）决定调用哪个工具；
- Python 程序负责校验工具名、执行本地函数并回传结果。

注意：**模型提出请求并不等于工具已经执行。** [OpenAI 官方 Function calling 文档](https://developers.openai.com/api/docs/guides/function-calling)将其描述为“模型请求 → 应用执行 → 回传结果 → 模型继续”的流程。

## 实验目标与工具

实现一个使用 OpenAI Responses API 的多工具 Agent Loop。

图书馆数据保存在 `agent_loop.py` 的本地字典中；每次运行可选择一个实验场景。模型应按需调用工具，而不是由 Python 代码写死调用顺序。

功能示例：查询《Python Basics》的位置、可借状态和借阅天数；如果不可借，推荐一本同主题且已经核实可借的书，并说明备选书的位置和借阅天数。**程序中的任务文本、图书数据、工具结果、终端输出和模型回答都使用英文；代码注释与本文说明使用中文。**

| 本地工具 | 输入 | 返回 | 用途 |
| --- | --- | --- | --- |
| `find_book` | 书名 | 图书编号、书架位置，或 `error` | 确认目标书是否存在。 |
| `check_availability` | 图书编号 | `available`，或 `error` | 核实目标书或备选书是否可借。 |
| `get_loan_policy` | 图书编号 | `loan_days`，或 `error` | 查询借阅天数。 |
| `find_similar_books` | 图书编号 | 同主题候选书名、编号、位置，或 `error` | 原书不可借时找备选；候选结果**不代表可借**。 |

字典中有三本 Python 主题的书和一本算法主题的书。其中《Practical Python》可借 21 天，《Advanced Python》当前不可借。这样模型需要对候选书再次调用 `check_availability`，不能把“主题相同”当成“当前可借”。

一条可能的调用链如下。实际顺序和一轮内的调用数量由模型决定：

```text
查找目标书 → 核实目标书是否可借
  ├─ 可借：查询借阅天数 → 回答位置、状态和期限
  ├─ 不可借：找同主题候选 → 核实候选是否可借 → 查询可借候选的期限 → 回答
  └─ 未找到：说明无法确认，不编造位置、库存或备选书
```

## 准备

在项目根目录运行，使用已有的 `.venv`：

```bash
source .venv/bin/activate
python -m pip install -r 01_llm_agent_and_toolcalling/requirements.txt
```

若尚未创建本地配置文件，可执行 `cp .env.example .env` 和 `chmod 600 .env`。然后在项目根目录的 `.env` 中填入**完整**密钥和可用模型，例如：

```dotenv
OPENAI_API_KEY=your_full_api_key
OPENAI_MODEL=gpt-6-luna
```

脚本会自动读取 `.env`；若文件存在，其中的值优先于当前终端的同名环境变量。`.env` 已加入项目根目录的 `.gitignore`，`.env.example` 不含真实密钥，可以保留作模板。请不要把完整密钥发到聊天里，也不要写进 Python 代码。

运行脚本会向 OpenAI API 发起真实请求，模型的工具调用顺序和措辞可能每次略有不同。四个工具只读取本地模拟数据，没有连接真实图书馆。
当前环境使用 SOCKS 代理，因此依赖文件也包含 `socksio`；其他环境通常只需 `openai`。
如果 API 返回 `429` 且提示 `no credits remaining`，需要先为 API 账户开通可用额度；这与 Python 代码和本地工具无关。

## 运行四个场景

以下命令都在项目根目录执行：

```bash
python 01_llm_agent_and_toolcalling/agent_loop.py baseline --trace
python 01_llm_agent_and_toolcalling/agent_loop.py A --trace
python 01_llm_agent_and_toolcalling/agent_loop.py B --trace
python 01_llm_agent_and_toolcalling/agent_loop.py C
```

| 场景 | 改动 | 观察与验证标准 |
| --- | --- | --- |
| `baseline` | 《Python Basics》在 `3F, Section A`，可借 30 天。 | 应核实位置、可借状态和期限；无需推荐备选。 |
| `A`：动态决策 | **问题不变**，只把《Python Basics》的 `available` 改为 `False`。 | 应说明原书当前不可借；可推荐核实后确实可借的《Practical Python》，并正确说明其位置和 21 天期限。不能把《Advanced Python》当成可借。 |
| `B`：错误反馈 | 改为查询《The Missing Book》。 | `find_book` 返回 `error`；应说明未查到、无法确认，不得编造编号、位置、库存、期限或备选书。 |
| `C`：调用链 | 使用基线数据和问题，自动打印完整轨迹。 | 区分模型 API 调用次数、工具请求次数和实际执行次数；能看到每次请求的工具名、参数和执行结果。 |

`--trace` 可用于任何场景；`C` 相当于默认开启轨迹的基线实验。模型输出可能不同，因此上面的调用链是观察参考，不是固定脚本。A 场景里模型也可能先检查一个不可借候选，再继续检查其他候选。

## 指令与 `tool_choice` 的真实对照报告

想深入看模型 API 返回什么、Python 在何时执行工具，以及不同指令与工具选择设置的实际影响，可阅读 [真实运行对照报告](instruction_tool_choice_report.md)。报告基于 36 组主对照和 1 组每轮强制调用的边界实验；[逐轮 JSON 记录](comparison_runs.json)保存了模型请求、工具结果、计数与最终回答。

`agent_loop.py` 保持为独立的核心教学脚本：始终使用完整指令和 `tool_choice="auto"`，让模型自主决定调用哪个工具以及何时回答。[compare_settings.py](compare_settings.py)才负责切换指令与 `tool_choice`，不会改变主脚本的运行方式。要重新生成对照数据，在项目根目录执行：

```bash
python 01_llm_agent_and_toolcalling/compare_settings.py
```

这会实际调用 API 并覆盖 `comparison_runs.json`；由于模型输出可能变化，静态报告仍对应其标注时间的那次运行。

## 看代码时重点关注

1. `TOOLS` 是向模型提供的工具说明；`make_executors()` 中的 Python 函数才会实际读取本地数据。
2. `client.responses.create(...)` 发起一次模型 API 调用。模型可能请求一个或多个工具，也可能直接给出最终回答。
3. `executors.get(call.name)` 只允许执行已登记的工具。工具请求、实际工具执行和模型 API 调用分别计数。
4. `history.extend(response.output)` 保留模型输出，包括推理项和工具请求；`function_call_output` 使用相同的 `call_id` 回传结果。这样下一轮能接着刚才的结果决策。[OpenAI 官方推理模型文档](https://developers.openai.com/api/docs/guides/reasoning)也建议在工具调用后保留这些输出项。
5. 循环最多调用模型 8 轮，防止持续请求工具；达到上限会明确提示没有得到最终回答。

开启 `--trace` 后，`Model output (raw)` 会展示模型本轮输出的结构。工具调用轮次的 `response.output_text` 可能为空，因为模型此时返回的是 `function_call`，并没有生成给用户看的正文。`response.output` 中的项目是 SDK 对象，打印 JSON 前需先用 `model_dump()` 转成字典。

这些场景需要同时查看**最终回答**和**调用轨迹**。脚本提供工具和循环，不会自动判定模型回答的语义是否完全正确；遇到不符合验证标准的回答，可以从轨迹判断是选错工具、漏查库存，还是错误理解了工具结果。
