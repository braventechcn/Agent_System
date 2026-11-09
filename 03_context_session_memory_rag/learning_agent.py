"""
观察 Session、Memory 和 RAG 怎样组成单次 LLM Context
"""

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError

from context import INSTRUCTIONS, build_context
from retrieval import index_project, search
from store import Store


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = Path(__file__).resolve().parent / "data" / "learning.sqlite3"


def print_hits(hits):
    for score, chunk in hits:
        preview = chunk["content"].replace("\n", " ")[:150]
        print(f"[{score:.3f}] {chunk['source']} > {chunk['heading']}\n  {preview}")


def ask(args, store: Store):
    """每次只调用一次模型；信息的选取由 Python 明确完成。"""
    store.ensure_session(args.session, args.profile)
    if not store.chunks() and not args.no_rag:
        raise ValueError("Document index is empty; run the 'index' command first")

    history = [] if args.no_session else store.messages(args.session)
    memories = [] if args.no_memory else store.memories(args.profile)
    # 追问可能省略主题；检索时补上本会话上一条用户问题。
    previous_questions = [item["content"] for item in history if item["role"] == "user"]
    query = args.question + (" " + previous_questions[-1] if previous_questions else "")
    hits = [] if args.no_rag else search(store, query, args.top_k)
    plan = build_context(args.question, history, memories, hits, args.budget)

    print(f"Session: {args.session}; profile: {args.profile}")
    print(
        f"Context: {plan.char_count}/{plan.budget} characters; "
        f"history messages {len(plan.selected_history)}; "
        f"memories {len(plan.selected_memories)}; "
        f"document chunks {len(plan.selected_chunks)}"
    )
    if args.trace:
        print("\n=== Instructions sent to model ===\n" + INSTRUCTIONS)
        print("\n=== Input sent to model ===")
        print(json.dumps(plan.messages, ensure_ascii=False, indent=2))

    load_dotenv(ROOT / ".env", override=True)
    model = os.getenv("OPENAI_MODEL")
    if not model or not os.getenv("OPENAI_API_KEY"):
        raise ValueError("Set OPENAI_API_KEY and OPENAI_MODEL in the project's local .env")
    response = OpenAI().responses.create(
        model=model,
        instructions=INSTRUCTIONS,
        input=plan.messages,
    )
    answer = response.output_text.strip()
    if not answer:
        raise ValueError("Model returned no answer; session history was not updated")
    print("\nAnswer:\n" + answer)
    if response.usage:
        print(
            f"Model usage: input {response.usage.input_tokens} tokens; "
            f"output {response.usage.output_tokens} tokens"
        )
    store.append_exchange(args.session, args.question, answer)


def main():
    parser = argparse.ArgumentParser(description="Context, Session, Memory, and RAG learning lab")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Local SQLite database")
    parser.add_argument("--profile", default="student", help="Memory owner / session owner")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("index", help="Chunk and index the three existing project guides")
    find = commands.add_parser("search", help="Inspect retrieval without calling a model")
    find.add_argument("query")
    find.add_argument("--top-k", type=int, default=3)

    remember = commands.add_parser("remember", help="Explicitly save or update a long-term fact")
    remember.add_argument("key")
    remember.add_argument("value")
    forget = commands.add_parser("forget", help="Delete a saved long-term fact")
    forget.add_argument("key")

    show = commands.add_parser("show", help="Inspect session history and saved memories")
    show.add_argument("--session", default="study-a")

    question = commands.add_parser("ask", help="Assemble context and call the LLM")
    question.add_argument("question")
    question.add_argument("--session", default="study-a")
    question.add_argument("--budget", type=int, default=6000, help="Teaching limit in characters, not tokens")
    question.add_argument("--top-k", type=int, default=3)
    question.add_argument("--no-session", action="store_true", help="Omit past messages from this request")
    question.add_argument("--no-memory", action="store_true", help="Omit saved memories from this request")
    question.add_argument("--no-rag", action="store_true", help="Omit retrieved document chunks")
    question.add_argument("--trace", action="store_true", help="Print the exact instructions and input")
    args = parser.parse_args()

    if args.command in {"ask", "search"} and args.top_k < 1:
        parser.error("--top-k must be positive")
    store = Store(args.db)
    try:
        if args.command == "index":
            print(f"Indexed {index_project(store, ROOT)} document chunks into {args.db}")
        elif args.command == "search":
            if not store.chunks():
                raise ValueError("Document index is empty; run 'index' first")
            print_hits(search(store, args.query, args.top_k))
        elif args.command == "remember":
            store.remember(args.profile, args.key, args.value)
            print(f"Saved memory {args.key!r} for profile {args.profile!r}")
        elif args.command == "forget":
            print("Deleted" if store.forget(args.profile, args.key) else "No matching memory")
        elif args.command == "show":
            store.ensure_session(args.session, args.profile)
            print("Session messages:")
            for message in store.messages(args.session):
                print(f"  {message['role']}: {message['content']}")
            print("Saved memories:")
            for memory in store.memories(args.profile):
                print(f"  {memory['key']}: {memory['value']}")
        else:
            ask(args, store)
    except (ValueError, OpenAIError) as exc:
        parser.exit(1, f"Error: {exc}\n")
    finally:
        store.close()


if __name__ == "__main__":
    main()
