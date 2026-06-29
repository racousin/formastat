"""Retriever — assembles the context the Formalizer/Prover sees.

The learning signal: as the corpus grows, later (harder) problems get more and
better verified few-shot examples, so success should rise across tiers. For the
prototype, retrieval = (a) the problem's Mathlib decl hints + (b) the most
recent verified (latex, lean) pairs from the corpus.

In-Lean premise retrieval (LeanCopilot `select_premises`) complements this at
proof time inside the Lean file; this module covers the prompt-level context.
"""

from __future__ import annotations

from store import Store


def build_context(problem: dict, store: Store, k: int = 6) -> str:
    parts: list[str] = []
    pairs = store.verified_for_context(problem["id"], limit=k)
    if pairs:
        parts.append("Verified examples from the FormaStat corpus (use as style/lemma guidance):")
        for p in pairs:
            stmt = (p["lean_statement"] or "").strip()
            proof = (p["lean_proof"] or "").strip()
            parts.append(f"-- {p['latex'].strip()}\n{stmt}\n{proof}".strip())
    parts.append(
        "Write `import Mathlib` (and `import LeanCopilot` only if you use its "
        "tactics). Keep the statement faithful to the original meaning."
    )
    return "\n\n".join(parts)
