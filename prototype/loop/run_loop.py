"""FormaStat learning loop — orchestrator (the Curriculum-driver role).

For each curriculum problem:
  formalize+prove (driver) -> verify (lean) -> [repair ⟲ N] -> [gap-fill] ->
  faithfulness gate -> checkpoint (write .lean + register import + store row).

The corpus grows as verified theorems accumulate; the retriever feeds them back
as context to later problems. Metrics (per-tier success, $/theorem) are written
to metrics/report.md — the grant's Q1 pilot deliverable in miniature.

Usage:
  python run_loop.py --tiers 0,1 --driver gemini --max-rounds 4
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml

from faithfulness import gate
from lean_verify import verify_snippet
from llm import Gemini
from retriever import build_context
from store import Attempt, Store
from ulam_adapter import Candidate, make_driver, module_name_for

ROOT = Path(__file__).resolve().parents[1]
LEAN = ROOT / "lean"
GEN_DIR = LEAN / "FormaStat" / "Generated"
ROOT_MODULE = LEAN / "FormaStat.lean"
IMPORT_MARKER = "-- FORMASTAT-GENERATED-IMPORTS"


def load_problems(tiers: set[int] | None) -> list[dict]:
    data = yaml.safe_load((ROOT / "curriculum" / "problems.yaml").read_text())
    probs = data["problems"]
    return [p for p in probs if tiers is None or p["tier"] in tiers]


def write_generated(problem_id: str, code: str) -> str:
    GEN_DIR.mkdir(parents=True, exist_ok=True)
    module = module_name_for(problem_id)
    (GEN_DIR / f"{module}.lean").write_text(code.rstrip() + "\n", encoding="utf-8")
    register_import(module)
    return module


def register_import(module: str) -> None:
    line = f"import FormaStat.Generated.{module}"
    text = ROOT_MODULE.read_text(encoding="utf-8")
    if line in text:
        return
    # Anchor to the WHOLE marker line so the import lands on its own line below
    # it (the marker line has a trailing parenthetical we must not splice into).
    text = re.sub(
        rf"^({re.escape(IMPORT_MARKER)}.*)$",
        lambda m: f"{m.group(1)}\n{line}",
        text, count=1, flags=re.M,
    )
    ROOT_MODULE.write_text(text, encoding="utf-8")


# Strong symbolic closer for residual `sorry`s (Milestone-1 fallback for
# LeanCopilot's `search_proof`): aesop is the general workhorse; the rest cover
# the arithmetic / linear / positivity goals common in the early tiers.
GAP_TACTIC = "first | aesop | simp_all | norm_num | nlinarith | omega | positivity"


def gap_fill(candidate: Candidate) -> Candidate | None:
    """Close residual `sorry`s with a symbolic tactic combinator. Returns a new
    candidate to re-verify, or None if nothing to fill. The combinator is a
    TACTIC: `by sorry` → `by <combinator>`; a term-position `:= sorry` →
    `:= (by <combinator>)` (not a nested `by (by …)`)."""
    if "sorry" not in candidate.code:
        return None
    code = candidate.code
    code = re.sub(r"\bby\s+sorry\b", f"by {GAP_TACTIC}", code)        # inline tactic
    code = re.sub(r"(?m)^(\s*)sorry\s*$", rf"\1{GAP_TACTIC}", code)   # sorry line in a by-block
    code = re.sub(r"\bsorry\b", f"(by {GAP_TACTIC})", code)           # remaining term-position
    return Candidate(code, candidate.theorem_name, model=candidate.model)


def split_statement_proof(code: str, name: str) -> tuple[str, str]:
    # Split at the ':=' that BEGINS the proof (followed by by/fun/λ/⟨), not the
    # first ':=' — statements legitimately contain ':=' in let-bindings and
    # structure-instance literals `{ f := ... }`.
    m = re.search(r":=\s*(by\b|fun\b|λ|⟨)", code)
    idx = m.start() if m else code.rfind(":=")
    if idx == -1:
        return code.strip(), ""
    return code[:idx].strip(), code[idx + 2:].strip()


def solve(problem, driver, store, judge, max_rounds, do_gap_fill) -> Attempt:
    tier, pid = problem["tier"], problem["id"]
    context = build_context(problem, store)
    cand = driver.formalize_and_prove(problem, context)
    in_tok, out_tok = cand.input_tokens, cand.output_tokens

    last_errors: list[str] = []
    repairs_done = 0  # actual driver.repair() calls (gap-fill rounds don't count)
    for rnd in range(max_rounds + 1):
        vr = verify_snippet(cand.code, print_axioms_of=cand.theorem_name)
        if vr.clean:
            stmt, proof = split_statement_proof(cand.code, cand.theorem_name)
            f = gate(problem["latex"], stmt, proof, cand.theorem_name, vr, llm=judge)
            status = "verified" if f.accept else "rejected"
            if f.accept:
                write_generated(pid, cand.code)
            return Attempt(
                problem_id=pid, tier=tier, status=status, model=cand.model or driver.name,
                latex=problem["latex"], lean_statement=stmt, lean_proof=proof,
                axioms=vr.axioms, repair_rounds=repairs_done, input_tokens=in_tok,
                output_tokens=out_tok, faithfulness=f.__dict__,
            )

        # not clean: try gap-fill once (sorry present), else repair from errors
        if do_gap_fill and vr.compiles and vr.used_sorry:
            gf = gap_fill(cand)
            if gf is not None:
                cand = gf
                continue
        last_errors = vr.errors or ["did not compile cleanly"]
        if rnd < max_rounds:
            cand = driver.repair(problem, cand, last_errors, context)
            repairs_done += 1
            in_tok += cand.input_tokens
            out_tok += cand.output_tokens

    return Attempt(
        problem_id=pid, tier=tier, status="failed", model=cand.model or driver.name,
        latex=problem["latex"], lean_statement=cand.code, repair_rounds=repairs_done,
        input_tokens=in_tok, output_tokens=out_tok, error="; ".join(last_errors[:5]),
    )


def write_report(store: Store, path: Path) -> None:
    lines = ["# FormaStat pilot report\n", "## Per-tier results\n",
             "| tier | attempts | verified | rejected | success % | total $ | avg rounds |",
             "|---|---|---|---|---|---|---|"]
    grand_cost = 0.0
    for s in store.tier_stats():
        att, ver = s["attempts"] or 0, s["verified"] or 0
        cost = s["total_cost"] or 0.0
        grand_cost += cost
        pct = (100 * ver / att) if att else 0
        lines.append(
            f"| {s['tier']} | {att} | {ver} | {s['rejected'] or 0} | "
            f"{pct:.0f}% | ${cost:.3f} | {(s['avg_rounds'] or 0):.1f} |"
        )
    verified = store.verified()
    per_thm = (grand_cost / len(verified)) if verified else 0.0
    lines += ["", f"**Total verified:** {len(verified)}",
              f"**Total cost:** ${grand_cost:.3f}",
              f"**Marginal cost / theorem:** ${per_thm:.2f}  (grant target < $30)"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tiers", default=None, help="comma list, e.g. 0,1,2")
    ap.add_argument("--driver", default="gemini", choices=["gemini", "ulam"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--max-rounds", type=int, default=4)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--no-gap-fill", action="store_true")
    ap.add_argument("--db", default=str(ROOT / "metrics" / "results.sqlite"))
    ap.add_argument("--force", action="store_true", help="re-run already-verified problems")
    args = ap.parse_args()

    tiers = {int(t) for t in args.tiers.split(",")} if args.tiers else None
    problems = load_problems(tiers)
    if args.limit is not None:
        problems = problems[: args.limit]

    store = Store(args.db)
    driver = make_driver(args.driver, model=args.model)
    judge = Gemini(model="gemini-3-flash")  # cheap back-translation judge

    for p in problems:
        if not args.force and store.already_verified(p["id"]):
            print(f"[skip] {p['id']} (already verified)")
            continue
        try:
            a = solve(p, driver, store, judge, args.max_rounds, not args.no_gap_fill)
        except Exception as e:  # keep the loop going; record the failure
            a = Attempt(problem_id=p["id"], tier=p["tier"], status="failed",
                        model=driver.name, latex=p["latex"], error=f"{type(e).__name__}: {e}")
        store.record(a)
        mark = {"verified": "✓", "rejected": "✗(faithfulness)", "failed": "✗"}[a.status]
        print(f"[{mark}] {p['id']:28s} rounds={a.repair_rounds} ${a.cost_usd:.3f}")

    report = ROOT / "metrics" / "report.md"
    write_report(store, report)
    store.close()
    print(f"\nReport written to {report}")


if __name__ == "__main__":
    main()
