"""用一个本地 SQLite 文件保存会话、长期记忆和文档切片。"""

import sqlite3
from pathlib import Path


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                profile TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES sessions(session_id),
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS memories (
                profile TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (profile, key)
            );
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY,
                source TEXT NOT NULL,
                heading TEXT NOT NULL,
                content TEXT NOT NULL
            );
            """
        )

    def close(self):
        self.db.close()

    def ensure_session(self, session_id: str, profile: str):
        """同一个 session_id 不允许被另一个 profile 误用。"""
        row = self.db.execute(
            "SELECT profile FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row and row["profile"] != profile:
            raise ValueError(f"Session {session_id!r} belongs to another profile")
        if not row:
            with self.db:
                self.db.execute(
                    "INSERT INTO sessions (session_id, profile) VALUES (?, ?)",
                    (session_id, profile),
                )

    def messages(self, session_id: str):
        return [dict(row) for row in self.db.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id", (session_id,)
        )]

    def append_exchange(self, session_id: str, question: str, answer: str):
        """模型成功回答后，再把一对消息一起写入会话。"""
        with self.db:
            self.db.executemany(
                "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
                [(session_id, "user", question), (session_id, "assistant", answer)],
            )

    def remember(self, profile: str, key: str, value: str):
        """相同 key 再次写入时覆盖旧值，演示 Memory 的更新。"""
        with self.db:
            self.db.execute(
                """INSERT INTO memories (profile, key, value) VALUES (?, ?, ?)
                   ON CONFLICT(profile, key) DO UPDATE SET
                   value = excluded.value, updated_at = CURRENT_TIMESTAMP""",
                (profile, key, value),
            )

    def forget(self, profile: str, key: str):
        with self.db:
            cursor = self.db.execute(
                "DELETE FROM memories WHERE profile = ? AND key = ?", (profile, key)
            )
        return cursor.rowcount > 0

    def memories(self, profile: str):
        return [dict(row) for row in self.db.execute(
            "SELECT key, value, updated_at FROM memories WHERE profile = ? ORDER BY key",
            (profile,),
        )]

    def replace_chunks(self, chunks):
        """重新索引时整体替换，避免文档变更后留下旧切片。"""
        with self.db:
            self.db.execute("DELETE FROM chunks")
            self.db.executemany(
                "INSERT INTO chunks (source, heading, content) VALUES (?, ?, ?)", chunks
            )

    def chunks(self):
        return [dict(row) for row in self.db.execute(
            "SELECT id, source, heading, content FROM chunks ORDER BY id"
        )]
