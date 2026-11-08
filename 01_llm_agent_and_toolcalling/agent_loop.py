"""用图书馆场景演示 Responses API 的多工具 Agent Loop。"""

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError

## 给出用户问题模版
QUESTION = (
    'I want to borrow "Python Basics". Where is it, is it available now, and how many days can I borrow it? '
    "If it is unavailable, recommend one available book on the same topic and tell me that book's shelf and loan period."
)
MISSING_QUESTION = (
    'I want to borrow "The Missing Book". Where is it, is it available now, and how many days can I borrow it? '
    "If it is unavailable, recommend one available book on the same topic and tell me that book's shelf and loan period."
)

## 实验参数: 最大循环轮数
MAX_ROUNDS = 8

## 模型指令，要求模型在回答前使用工具验证事实，避免凭训练知识直接回答。
INSTRUCTIONS = (
    "You are a library assistant. Choose tools as needed and verify facts before answering. "
    "Use book IDs only when they came from tool results; never invent an ID. "
    "Find the requested book, then verify availability and loan duration as needed. "
    "If it is unavailable, look for a book on the same topic, but verify a candidate with "
    "check_availability before recommending it. Also use get_loan_policy for the recommended book. "
    "Recommend at most one alternative. "
    "If the requested book is not found, say its details cannot be confirmed; do not invent "
    "an ID, shelf, availability, loan duration, or alternative. "
    "State a loan duration only when get_loan_policy returned it. "
    "Do not say an unavailable book can currently be borrowed. Answer in English."
)

def tool_schema(name, description, parameter):
    """
    定义“工具接口模式”或“工具调用契约”（使用 JSON Schema）
        - name: 工具名称，模型调用时使用
        - description: 工具用途描述
        - parameter: 工具参数名称
    """
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": {parameter: {"type": "string"}},
            "required": [parameter],
            "additionalProperties": False,
        },
        "strict": True,
    }


TOOLS = [
    tool_schema(
        "find_book",
        "Find a book by its exact title. Returns its ID and shelf, or an error.",
        "title"
    ),
    tool_schema(
        "check_availability",
        "Check whether a known book ID is currently available to borrow.",
        "book_id"
    ),
    tool_schema(
        "get_loan_policy",
        "Get the borrowing period in days for a known book ID.",
        "book_id"
    ),
    tool_schema(
        "find_similar_books",
        "Find books on the same topic as an unavailable book. Returns candidate titles, IDs, and shelves; availability is not verified.",
        "book_id",
    ),
]


def make_executors(books):
    """创建本地模拟工具，工具读取传入的图书数据。"""

    def book_by_id(book_id):
        return next((book for book in books.values() if book["book_id"] == book_id), None)

    def find_book(title):
        book = books.get(title)
        if book is None:
            return {"error": "Book not found"}
        return {"book_id": book["book_id"], "shelf": book["shelf"]}

    def check_availability(book_id):
        book = book_by_id(book_id)
        return {"available": book["available"]} if book else {"error": "Invalid book ID"}

    def get_loan_policy(book_id):
        book = book_by_id(book_id)
        return {"loan_days": book["loan_days"]} if book else {"error": "Invalid book ID"}

    def find_similar_books(book_id):
        target = book_by_id(book_id)
        if target is None:
            return {"error": "Invalid book ID"}
        # 这里只按主题筛选；是否可借仍要单独调用 check_availability。
        candidates = [
            {"title": title, "book_id": book["book_id"], "shelf": book["shelf"]}
            for title, book in books.items()
            if book["topic"] == target["topic"] and book["book_id"] != book_id
        ]
        return {"books": candidates}

    return {
        "find_book": find_book,
        "check_availability": check_availability,
        "get_loan_policy": get_loan_policy,
        "find_similar_books": find_similar_books,
    }


def books_for_experiment(experiment):
    """为每次实验创建独立数据，避免前一次运行修改下一次的状态。"""
    books = {
        "Python Basics": {
            "book_id": "bk-102", "shelf": "3F, Section A", "available": True,
            "topic": "Python", "loan_days": 30,
        },
        "Practical Python": {
            "book_id": "bk-208", "shelf": "3F, Section B", "available": True,
            "topic": "Python", "loan_days": 21,
        },
        "Advanced Python": {
            "book_id": "bk-305", "shelf": "4F, Section A", "available": False,
            "topic": "Python", "loan_days": 30,
        },
        "Introduction to Algorithms": {
            "book_id": "bk-410", "shelf": "2F, Section C", "available": True,
            "topic": "Algorithms", "loan_days": 30,
        },
    }
    question = MISSING_QUESTION if experiment == "B" else QUESTION
    if experiment == "A":
        books["Python Basics"]["available"] = False
    return question, books


def run_agent(client, model, question, books, trace=False):
    """
    Agent Loop: 模型根据用户问题和工具结果，决定下一步调用哪个工具或给出回答。循环直到模型不再请求工具。
        - client: OpenAI 客户端
        - model: 可用的模型名称，需支持 function calling
        - question: 用户问题
        - books: 本地图书馆数据，供工具读取
        - trace: 是否打印每轮模型调用、工具请求和工具执行结果
    """
    # Step 0: 初始化对话历史
    #   - 包含用户问题；每轮循环模型可访问前轮输出。
    history = [{"role": "user", "content": question}]
    # 创建工具执行器，供 Python 执行工具请求时调用。
    executors = make_executors(books)
    # 统计调用次数，便于调试和分析
    api_calls = tool_requests = tool_executions = 0

    # Loop: 模型可能多轮调用工具，直到不再请求工具
    for round_number in range(1, MAX_ROUNDS + 1):
        api_calls += 1
        if trace:
            print(f"\n[Round {round_number}] Model API call #{api_calls}")

        # 模型自行决定回答，或请求一个/多个工具；程序没有预写调用顺序。
        response = client.responses.create(
            model=model,
            instructions=INSTRUCTIONS,
            tools=TOOLS,
            tool_choice="auto",  # 模型可自行选择调用哪个工具或直接回答。
            input=history,
        )

        # 保留整轮输出，包括可能的推理项和工具请求，供下轮模型调用使用。
        history.extend(response.output)
        if trace:
            # 工具调用轮次可能没有文本；先将 SDK 对象转成字典，再打印完整输出。
            raw_output = [item.model_dump(mode="json", exclude_none=True) for item in response.output]
            print(f"[Round {round_number}] Model output (raw): {json.dumps(raw_output, ensure_ascii=False)}")
        if response.status != "completed":
            print(f"Model response status: {response.status}; no complete answer was returned.")
            break

        # 解析模型输出，查找工具调用请求；如果没有请求，说明模型已给出最终回答。
        calls = [item for item in response.output if item.type == "function_call"]
        if not calls:
            print("Final answer:", response.output_text or "(The model returned no text)")
            break
        # 处理模型提出的工具调用请求
        # executors = make_executors(books) # 已经在循环外创建，避免每轮都重新创建
        for call in calls:  # 模型可能一次请求多个工具，按顺序执行。
            tool_requests += 1
            if trace:
                print(f"[Round {round_number}] Tool request #{tool_requests}: {call.name}, arguments: {call.arguments}")

            # 模型只提出请求；真正执行哪个函数由白名单 executors 决定。
            executed = False
            try:
                # 解析工具调用参数，执行对应函数，并返回结果；如果工具名不在白名单，返回错误。
                args = json.loads(call.arguments)
                # 根据工具名查找对应的本地函数；如果不在白名单，返回错误。
                function = executors.get(call.name)
                if function is None:
                    result = {"error": "Unauthorized tool"}
                else:
                    # 执行工具函数，返回结果；如果参数不合法，捕获异常并返回错误。
                    result = function(**args)
                    tool_executions += 1
                    executed = True
            except (ValueError, TypeError) as exc:
                result = {"error": str(exc)}

            if trace:
                label = f"Tool execution #{tool_executions}" if executed else "Tool not executed"
                print(
                    f"[Round {round_number}] {label}: {call.name}, "
                    f"arguments: {call.arguments}, result: {json.dumps(result, ensure_ascii=False)}"
                )

            # 使用原始 call_id 把结果送回模型，让它决定下一步。
            history.append({
                "type": "function_call_output",
                "call_id": call.call_id,
                "output": json.dumps(result, ensure_ascii=False),
            })
    else:
        print(f"Reached the maximum of {MAX_ROUNDS} model rounds without a final answer.")

    print(f"Call counts: model API {api_calls}; tool requests {tool_requests}; tool executions {tool_executions}")


def main():
    """命令行入口，选择实验场景，运行 Agent Loop."""
    parser = argparse.ArgumentParser(
        description="Library Tool-calling Agent Loop. ")
    # 实验场景：baseline 仅使用默认问题；A 将《Python Basics》改为不可借；B 查询不存在的书；C 打印每轮模型调用、工具请求和工具执行结果。
    parser.add_argument("experiment", nargs="?", choices=("baseline", "A", "B", "C"), default="baseline")
    parser.add_argument("--trace", action="store_true", help="Print each model round, tool request, and tool result")
    args = parser.parse_args()

    # 自动读取项目根目录的本地 .env；存在时以文件中的值为准。
    #   - 在 .env 中有效的 OPENAI_API_KEY 和 OPENAI_MODEL，程序才能运行。
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)
    model = os.getenv("OPENAI_MODEL")
    if not model:
        parser.error("Set OPENAI_MODEL to a model available to your account that supports function calling")
    if not os.getenv("OPENAI_API_KEY"):
        parser.error("Set OPENAI_API_KEY")

    question, books = books_for_experiment(args.experiment)

    # 运行 Agent Loop
    print(f"Experiment: {args.experiment}; \nAsk: {question}")
    try:
        run_agent(OpenAI(), model, question, books, trace=args.trace or args.experiment == "C")
    except OpenAIError as exc:
        parser.exit(1, f"OpenAI API request failed: {exc}\n")


if __name__ == "__main__":
    main()
