"""从项目已有的 Markdown 指南建立轻量关键词索引并检索。"""

import math
import re
from pathlib import Path


# 使用实际项目文档，不复制一份很快过期的“假知识库”。
SOURCES = (
    "00_agent_system_basics/README.md",
    "01_llm_agent_and_toolcalling/README.md",
    "02_external_capabilities/README.md",
)


def terms(text: str):
    """英文按单词、中文按相邻两字切分，便于不依赖向量服务的双语检索。"""
    stopwords = {"a", "an", "and", "are", "between", "does", "for", "how", "in", "is", "of", "the", "to", "what"}
    english = [word for word in re.findall(r"[a-z][a-z0-9_]+", text.lower()) if word not in stopwords]
    chinese = re.findall(r"[\u4e00-\u9fff]+", text)
    bigrams = [word[i : i + 2] for word in chinese for i in range(len(word) - 1)]
    return set(english + bigrams)


def split_markdown(source: str, text: str, max_chars: int = 750):
    """按标题和段落切片；长段落继续切分，保留可追溯的来源。"""
    heading = "Introduction"
    buffer = ""
    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if not block:
            continue
        if block.startswith("#"):
            match = re.match(r"^#{1,6}\s+(.+)", block)
            if match:
                if buffer:
                    yield (source, heading, buffer)
                    buffer = ""
                heading = match.group(1).strip()
                continue
        # 一个段落过长时优先在换行或句尾切开，保留可阅读的片段。
        while block:
            room = max_chars - len(buffer) - (2 if buffer else 0)
            if room <= 0:
                yield (source, heading, buffer)
                buffer = ""
                room = max_chars
            cut = min(room, len(block))
            if cut < len(block):
                candidates = [block.rfind(mark, max(0, cut - 180), cut) for mark in ("\n", "。", ". ", " ")]
                boundary = max(candidates)
                if boundary > 0:
                    cut = boundary + (1 if block[boundary] in "。\n" else 0)
            part, block = block[:cut].strip(), block[cut:].strip()
            buffer = f"{buffer}\n\n{part}" if buffer else part
            if block:
                yield (source, heading, buffer)
                buffer = ""
    if buffer:
        yield (source, heading, buffer)


def index_project(store, root: Path):
    chunks = []
    for source in SOURCES:
        path = root / source
        chunks.extend(split_markdown(source, path.read_text(encoding="utf-8")))
    store.replace_chunks(chunks)
    return len(chunks)


def search(store, query: str, top_k: int = 3):
    """用简明可见的重合度排序；没有命中时不返回随机段落。"""
    query_terms = terms(query)
    chunks = store.chunks()
    document_frequency = {}
    for chunk in chunks:
        for term in terms(chunk["heading"] + " " + chunk["content"]):
            document_frequency[term] = document_frequency.get(term, 0) + 1
    ranked = []
    for chunk in chunks:
        heading_terms = terms(chunk["heading"])
        document_terms = terms(chunk["content"]) | heading_terms
        overlap = query_terms & document_terms
        if not overlap:
            continue
        # 罕见关键词更有区分度；标题命中额外加权，长片段稍作折扣。
        score = sum(
            math.log(1 + len(chunks) / document_frequency[term])
            * (2 if term in heading_terms else 1)
            for term in overlap
        ) / math.sqrt(max(len(document_terms), 1))
        ranked.append((score, chunk))
    ranked.sort(key=lambda item: (-item[0], item[1]["id"]))
    # 避免同一节的相邻切片占满全部名额，让 Context 有机会包含不同小节。
    results = []
    seen_sections = set()
    for score, chunk in ranked:
        section = (chunk["source"], chunk["heading"])
        if section in seen_sections:
            continue
        seen_sections.add(section)
        results.append((round(score, 3), chunk))
        if len(results) == top_k:
            break
    return results
