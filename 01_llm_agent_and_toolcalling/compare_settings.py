"""实际调用 Responses API，保存指令与 tool_choice 对照实验的逐轮记录。"""

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from agent_loop import INSTRUCTIONS, TOOLS, books_for_experiment, make_executors


HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "comparison_runs.json"
SCENARIOS = ("baseline", "A", "B")
CHOICES = ("auto", "omitted", "none", "required-first")
SHORT_INSTRUCTIONS = (
    "Use the available tools to verify library information before answering. "
    "Do not invent book details. Answer in English."
)
INSTRUCTION_MODES = {"full": INSTRUCTIONS, "short": SHORT_INSTRUCTIONS, "none": None}


def run_comparison(client, model, question, books, instructions, choice_mode, max_rounds):
    """仅供对照实验使用：记录每次 API 返回与 Python 工具执行的边界。"""
    history = [{"role": "user", "content": question}]
    executors = make_executors(books)
    rounds = []
    counts = {"model_api": 0, "tool_requests": 0, "tool_executions": 0}
    status = "max_rounds"
    final_answer = None

    for round_number in range(1, max_rounds + 1):
        request = {"model": model, "tools": TOOLS, "input": history}
        if instructions is not None:
            request["instructions"] = instructions
        if choice_mode == "required-first":
            request["tool_choice"] = "required" if round_number == 1 else "auto"
        elif choice_mode != "omitted":
            request["tool_choice"] = choice_mode

        round_record = {
            "round": round_number,
            "request": {
                "instructions_supplied": instructions is not None,
                "tool_choice_sent": request.get("tool_choice", "<omitted>"),
                "history_items_sent": len(history),
            },
            "response": {},
            "tool_results": [],
        }
        response = client.responses.create(**request)
        counts["model_api"] += 1
        history.extend(response.output)

        output_items = []
        for item in response.output:
            if item.type == "function_call":
                output_items.append({
                    "type": item.type, "name": item.name,
                    "arguments": item.arguments, "call_id": item.call_id,
                    "status": getattr(item, "status", None),
                })
            elif item.type == "message":
                text_parts = [
                    part.text for part in getattr(item, "content", [])
                    if getattr(part, "type", None) == "output_text"
                ]
                output_items.append({"type": item.type, "text": "".join(text_parts)})
            else:
                output_items.append({"type": item.type})
        round_record["response"] = {
            "status": getattr(response, "status", None),
            "incomplete_details": response.incomplete_details.model_dump(mode="json", exclude_none=True)
            if getattr(response, "incomplete_details", None) else None,
            "output_items": output_items,
            "output_text": response.output_text or "",
            "usage": response.usage.model_dump(mode="json", exclude_none=True)
            if getattr(response, "usage", None) else None,
        }
        rounds.append(round_record)

        # API 返回 incomplete 时，即使有部分文本，也不能把它当成最终回答。
        if getattr(response, "status", None) != "completed":
            status = f"response_{response.status}"
            break

        calls = [item for item in response.output if item.type == "function_call"]
        if not calls:
            final_answer = response.output_text or ""
            status = "completed" if final_answer else "no_text"
            break

        for call in calls:
            counts["tool_requests"] += 1
            executed = False
            try:
                args = json.loads(call.arguments)
                function = executors.get(call.name)
                if function is None:
                    result = {"error": "Unauthorized tool"}
                else:
                    result = function(**args)
                    counts["tool_executions"] += 1
                    executed = True
            except (ValueError, TypeError) as exc:
                result = {"error": str(exc)}

            round_record["tool_results"].append({
                "call_id": call.call_id, "name": call.name,
                "arguments": call.arguments, "executed": executed, "result": result,
            })
            history.append({
                "type": "function_call_output", "call_id": call.call_id,
                "output": json.dumps(result, ensure_ascii=False),
            })

    return {
        "status": status, "final_answer": final_answer,
        "counts": counts, "rounds": rounds,
    }


def run_one(model, scenario, instruction_mode, choice_mode):
    question, books = books_for_experiment(scenario)
    record = {
        "scenario": scenario,
        "question": question,
        "instruction_mode": instruction_mode,
        "tool_choice_mode": choice_mode,
    }
    try:
        with OpenAI() as client:
            record["run"] = run_comparison(
                client, model, question, books,
                INSTRUCTION_MODES[instruction_mode], choice_mode,
                3 if choice_mode == "required" else 8,
            )
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
    return record


def main():
    load_dotenv(HERE.parent / ".env", override=True)
    model = os.environ["OPENAI_MODEL"]
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY in the project .env")

    configs = [
        (scenario, instruction_mode, choice_mode)
        for scenario in SCENARIOS
        for instruction_mode in INSTRUCTION_MODES
        for choice_mode in CHOICES
    ]
    # 每轮都 required 无法正常给出不含工具调用的结尾，单独运行三轮展示其影响。
    configs.append(("baseline", "full", "required"))
    document = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "instruction_texts": INSTRUCTION_MODES,
        "note": "Each setting was run once against the live Responses API. No API key is stored.",
        "runs": [],
    }

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(run_one, model, *config): config for config in configs
        }
        for future in as_completed(futures):
            record = future.result()
            document["runs"].append(record)
            OUTPUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n")
            name = "/".join((
                record["scenario"], record["instruction_mode"],
                record["tool_choice_mode"],
            ))
            if "error" in record:
                print(f"{len(document['runs']):02d}/{len(configs)} {name}: ERROR {record['error']}", flush=True)
            else:
                run = record["run"]
                print(
                    f"{len(document['runs']):02d}/{len(configs)} {name}: "
                    f"{run['status']}; {run['counts']}", flush=True,
                )


if __name__ == "__main__":
    main()
