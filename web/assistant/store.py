"""Conversations, messages and usage, in the database.

Messages are kept as displayed (names restored), with the tool calls made to
answer them, so a person can see how every answer was worked out. With
``assistant.logging.keep_conversations: false`` only usage counts are kept.
Conversations older than ``assistant.logging.retention_days`` are deleted.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from portfolio.db import Database, utcnow


class ConversationStore:
    def __init__(self, db: Database):
        self.db = db

    # -- conversations -------------------------------------------------------
    def list(self, owner: str) -> list[dict]:
        return self.db.query("SELECT * FROM assistant_conversations WHERE owner = :o"
                             " ORDER BY updated_at DESC, id DESC", {"o": owner})

    def get(self, owner: str, cid: int) -> dict | None:
        return self.db.one("SELECT * FROM assistant_conversations WHERE id = :i AND owner = :o",
                           {"i": cid, "o": owner})

    def create(self, owner: str, title: str) -> int:
        now = utcnow()
        with self.db.tx() as c:
            return Database.insert(c, "INSERT INTO assistant_conversations (owner, title,"
                                      " created_at, updated_at) VALUES (:o, :t, :n, :n)",
                                   {"o": owner, "t": title[:120], "n": now})

    def delete(self, owner: str, cid: int) -> None:
        with self.db.tx() as c:
            Database.run(c, "DELETE FROM assistant_messages WHERE conversation_id IN (SELECT id"
                            " FROM assistant_conversations WHERE id = :i AND owner = :o)",
                         {"i": cid, "o": owner})
            Database.run(c, "DELETE FROM assistant_conversations WHERE id = :i AND owner = :o",
                         {"i": cid, "o": owner})

    def messages(self, owner: str, cid: int) -> list[dict]:
        if not self.get(owner, cid):
            return []
        rows = self.db.query("SELECT * FROM assistant_messages WHERE conversation_id = :c"
                             " ORDER BY id", {"c": cid})
        for r in rows:
            r["tool_calls"] = json.loads(r["tool_calls"] or "[]")
        return rows

    def add(self, cid: int, role: str, content: str, tool_calls=None, tokens_in: int = 0,
            tokens_out: int = 0, model: str = "") -> None:
        now = utcnow()
        with self.db.tx() as c:
            Database.run(c, "INSERT INTO assistant_messages (conversation_id, role, content,"
                            " tool_calls, tokens_in, tokens_out, model, created_at)"
                            " VALUES (:c, :r, :t, :tc, :i, :o, :m, :n)",
                         {"c": cid, "r": role, "t": content, "tc": json.dumps(tool_calls or []),
                          "i": tokens_in, "o": tokens_out, "m": model, "n": now})
            Database.run(c, "UPDATE assistant_conversations SET updated_at = :n WHERE id = :c",
                         {"n": now, "c": cid})

    def prune(self, days: int) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self.db.tx() as c:
            Database.run(c, "DELETE FROM assistant_messages WHERE conversation_id IN (SELECT id"
                            " FROM assistant_conversations WHERE updated_at < :d)", {"d": cutoff})
            return Database.run(c, "DELETE FROM assistant_conversations WHERE updated_at < :d",
                                {"d": cutoff}).rowcount

    # -- usage and limits ------------------------------------------------------
    def count(self, owner: str, tokens: int = 0) -> None:
        with self.db.tx() as c:
            Database.run(c, "INSERT INTO assistant_usage (day, owner, questions, tokens)"
                            " VALUES (:d, :o, 1, :t) ON CONFLICT (day, owner) DO UPDATE SET"
                            " questions = assistant_usage.questions + 1,"
                            " tokens = assistant_usage.tokens + excluded.tokens",
                         {"d": date.today().isoformat(), "o": owner, "t": tokens})

    def add_tokens(self, owner: str, tokens: int) -> None:
        with self.db.tx() as c:
            Database.run(c, "UPDATE assistant_usage SET tokens = tokens + :t"
                            " WHERE day = :d AND owner = :o",
                         {"t": tokens, "d": date.today().isoformat(), "o": owner})

    def questions_last_hour(self, owner: str) -> int:
        since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        return int(self.db.scalar(
            "SELECT COUNT(*) FROM assistant_messages m JOIN assistant_conversations c"
            " ON c.id = m.conversation_id WHERE c.owner = :o AND m.role = 'user'"
            " AND m.created_at >= :s", {"o": owner, "s": since}, 0))

    def tokens_today(self) -> int:
        return int(self.db.scalar("SELECT COALESCE(SUM(tokens), 0) FROM assistant_usage"
                                  " WHERE day = :d", {"d": date.today().isoformat()}, 0))

    def usage_today(self, owner: str) -> dict:
        r = self.db.one("SELECT questions, tokens FROM assistant_usage WHERE day = :d AND owner = :o",
                        {"d": date.today().isoformat(), "o": owner})
        return dict(questions=r["questions"] if r else 0, tokens=r["tokens"] if r else 0)
