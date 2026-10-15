"""Histórico de execuções e textos gerados pela LLM (SQLite, sem servidor).

O histórico é o que permite gerar relatórios diários/semanais consolidados.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from rotavital.config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    scenario_name TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS llm_outputs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    kind TEXT NOT NULL,
    target TEXT,
    provider TEXT,
    model TEXT,
    content TEXT NOT NULL,
    evaluation TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at);
"""


class HistoryStore:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path or settings.database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    # ---------------------------------------------------------------- runs
    def save_run(self, run: dict) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO runs (id, created_at, scenario_id, scenario_name, payload)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    run["id"],
                    run["criado_em"],
                    run["cenario"]["id"],
                    run["cenario"]["nome"],
                    json.dumps(run, ensure_ascii=False),
                ),
            )

    def get_run(self, run_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM runs WHERE id = ?", (run_id,)).fetchone()
        return json.loads(row["payload"]) if row else None

    def list_runs(self, limit: int = 50) -> List[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        out = []
        for row in rows:
            run = json.loads(row["payload"])
            out.append(
                {
                    "id": run["id"],
                    "criado_em": run["criado_em"],
                    "cenario": run["cenario"]["nome"],
                    "cenario_id": run["cenario"]["id"],
                    "kpis": {k: v for k, v in run["solucao"].items() if k != "rotas"},
                    "ga": {k: run["ga"][k] for k in ("geracoes", "motivo_parada", "tempo_s")},
                }
            )
        return out

    def runs_since(self, days: int) -> List[dict]:
        since = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM runs WHERE created_at >= ? ORDER BY created_at", (since,)
            ).fetchall()
        return [json.loads(r["payload"]) for r in rows]

    # --------------------------------------------------------- llm outputs
    def save_llm_output(
        self,
        run_id: Optional[str],
        kind: str,
        content: str,
        provider: str,
        model: str,
        target: Optional[str] = None,
        evaluation: Optional[dict] = None,
    ) -> int:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO llm_outputs (run_id, kind, target, provider, model, content,"
                " evaluation, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    kind,
                    target,
                    provider,
                    model,
                    content,
                    json.dumps(evaluation, ensure_ascii=False) if evaluation else None,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            return int(cur.lastrowid)

    def list_llm_outputs(self, run_id: Optional[str] = None, limit: int = 50) -> List[dict]:
        query = "SELECT * FROM llm_outputs"
        params: tuple = ()
        if run_id:
            query += " WHERE run_id = ?"
            params = (run_id,)
        query += " ORDER BY id DESC LIMIT ?"
        with self._connect() as conn:
            rows = conn.execute(query, params + (limit,)).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["evaluation"] = json.loads(item["evaluation"]) if item["evaluation"] else None
            out.append(item)
        return out
