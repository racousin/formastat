"""SQLite-backed store for the FormaStat learning loop.

One row per attempt. Verified rows (status='verified') form the growing corpus
that the retriever feeds back as few-shot context — the core of the learning
loop. Also the source of the pilot metrics (success rate, $/theorem).
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

# Per-1M-token USD pricing for cost-per-theorem accounting. Adjust to the
# actual Vertex/AI-Studio rates for the model you run; these are placeholders
# wired so the pilot report computes a real marginal $/theorem.
PRICING_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    # model_substring: (input_per_mtok, output_per_mtok)
    "gemini-3.1-pro": (2.50, 15.00),
    "gemini-3-pro": (2.50, 15.00),
    "gemini-3-flash": (0.30, 2.50),
    "gemini-flash": (0.30, 2.50),
}


def price_for(model: str) -> tuple[float, float]:
    for key, price in PRICING_USD_PER_MTOK.items():
        if key in (model or ""):
            return price
    return (0.0, 0.0)


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    pin, pout = price_for(model)
    return (input_tokens / 1_000_000) * pin + (output_tokens / 1_000_000) * pout


@dataclass
class Attempt:
    problem_id: str
    tier: int
    status: str  # 'verified' | 'failed' | 'rejected'
    model: str
    latex: str = ""
    lean_statement: str = ""
    lean_proof: str = ""
    axioms: str = ""
    repair_rounds: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    faithfulness: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    mathlib_rev: str = "v4.32.0-rc1"
    toolchain: str = "leanprover/lean4:v4.32.0-rc1"
    ts: float = field(default_factory=time.time)

    @property
    def cost_usd(self) -> float:
        return cost_usd(self.model, self.input_tokens, self.output_tokens)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS attempts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ts             REAL,
    problem_id     TEXT,
    tier           INTEGER,
    status         TEXT,
    model          TEXT,
    latex          TEXT,
    lean_statement TEXT,
    lean_proof     TEXT,
    axioms         TEXT,
    repair_rounds  INTEGER,
    input_tokens   INTEGER,
    output_tokens  INTEGER,
    cost_usd       REAL,
    faithfulness   TEXT,
    error          TEXT,
    mathlib_rev    TEXT,
    toolchain      TEXT
);
CREATE INDEX IF NOT EXISTS idx_problem ON attempts(problem_id);
CREATE INDEX IF NOT EXISTS idx_status  ON attempts(status);
"""


class Store:
    def __init__(self, path: str | Path = "metrics/results.sqlite") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def record(self, a: Attempt) -> int:
        d = asdict(a)
        d["faithfulness"] = json.dumps(a.faithfulness)
        d["cost_usd"] = a.cost_usd
        cols = (
            "ts,problem_id,tier,status,model,latex,lean_statement,lean_proof,"
            "axioms,repair_rounds,input_tokens,output_tokens,cost_usd,"
            "faithfulness,error,mathlib_rev,toolchain"
        )
        ph = ",".join("?" for _ in cols.split(","))
        cur = self.conn.execute(
            f"INSERT INTO attempts ({cols}) VALUES ({ph})",
            tuple(d[c] for c in cols.split(",")),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def verified(self) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                "SELECT * FROM attempts WHERE status='verified' ORDER BY ts"
            )
        )

    def verified_for_context(self, exclude_id: str, limit: int = 8) -> list[dict[str, str]]:
        """Verified (latex, lean) pairs used as few-shot retrieval context."""
        rows = self.conn.execute(
            "SELECT latex, lean_statement, lean_proof FROM attempts "
            "WHERE status='verified' AND problem_id != ? ORDER BY ts DESC LIMIT ?",
            (exclude_id, limit),
        )
        return [dict(r) for r in rows]

    def already_verified(self, problem_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM attempts WHERE problem_id=? AND status='verified' LIMIT 1",
            (problem_id,),
        ).fetchone()
        return row is not None

    def tier_stats(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT tier,
                   COUNT(*)                                            AS attempts,
                   SUM(status='verified')                             AS verified,
                   SUM(status='rejected')                             AS rejected,
                   SUM(cost_usd)                                      AS total_cost,
                   AVG(repair_rounds)                                 AS avg_rounds
            FROM attempts GROUP BY tier ORDER BY tier
            """
        )
        return [dict(r) for r in rows]

    def close(self) -> None:
        self.conn.close()
