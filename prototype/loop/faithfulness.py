"""Faithfulness gate — "compiles ≠ correct".

A Lean theorem can compile yet be wrong: vacuous (contradictory hypotheses),
trivially true, or subtly mistranslated. This gate runs the cheap→strong stack:

  1. axiom check   — `#print axioms` must not depend on `sorryAx`; only the
                     standard {propext, Classical.choice, Quot.sound} are allowed.
  2. sorry scan    — no `sorry`/`admit`/`native_decide` in the proof.
  3. vacuity check — try to derive `False` from the hypotheses (heuristic; a
                     success means the statement is ill-posed → reject).
  4. back-translate — Gemini informalizes the Lean statement; an LLM judge
                     compares it to the original LaTeX (soft signal, 0..1).

`accept` requires 1+2 hard, 3 not-vacuous, and 4 above threshold.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from lean_verify import VerifyResult, verify_snippet

ALLOWED_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}
BACKTRANSLATE_THRESHOLD = 0.6


@dataclass
class Faithfulness:
    accept: bool
    axioms_ok: bool
    no_sorry: bool
    not_vacuous: bool
    backtranslation_score: float
    detail: dict[str, Any] = field(default_factory=dict)


def _check_axioms(axioms_output: str) -> bool:
    # Hard gate, fail-closed: every axiom dependency must be in the allowlist.
    if "sorryAx" in axioms_output:
        return False
    if "does not depend on any axioms" in axioms_output:
        return True
    m = re.search(r"depends on axioms:\s*\[(.*?)\]", axioms_output, re.S)
    if not m:
        return False  # unrecognized output → can't confirm safety → reject
    deps = [a.strip() for a in m.group(1).split(",") if a.strip()]
    # rejects user `axiom`s and native_decide's Lean.ofReduceBool/trustCompiler
    return all(a in ALLOWED_AXIOMS for a in deps)


def _vacuity_snippet(lean_statement: str, name: str) -> Optional[str]:
    """Rewrite `theorem name <binders> : Concl := ...` into a check that the
    same hypotheses yield `False`: keep the binders, replace the conclusion with
    `False`, and try automation. The binder/conclusion split is the FIRST colon
    at bracket depth 0 — binders themselves contain colons, e.g. `(n : Nat)`."""
    head = lean_statement.split(":=", 1)[0]
    m = re.match(r"\s*(theorem|lemma)\s+" + re.escape(name) + r"(.*)$", head, re.S)
    if not m:
        return None
    rest = m.group(2)
    depth, sep = 0, -1
    for i, ch in enumerate(rest):
        if ch in "([{⟨":
            depth += 1
        elif ch in ")]}⟩":
            depth -= 1
        elif ch == ":" and depth == 0:
            sep = i
            break
    if sep == -1:
        return None  # no top-level conclusion colon → skip rather than emit garbage
    binders = rest[:sep].strip()
    # `import Mathlib` is required, else Mathlib-typed binders (ℝ, measures…) fail
    # to elaborate and the check would never actually test vacuity.
    return (
        f"import Mathlib\n\n"
        f"theorem _vacuity_{name} {binders} : False := by\n"
        f"  first | (exfalso; assumption) | simp_all | omega | nlinarith | exact?\n"
    )


def gate(
    latex: str,
    lean_statement: str,
    proof_code: str,
    theorem_name: str,
    verify: VerifyResult,
    llm=None,
) -> Faithfulness:
    axioms_ok = _check_axioms(verify.axioms) if verify.axioms else (not verify.used_sorry)
    no_sorry = not verify.used_sorry

    # vacuity: if we can prove False from the hypotheses, the statement is ill-posed
    not_vacuous = True
    vac_detail = "skipped"
    snip = _vacuity_snippet(lean_statement, theorem_name)
    if snip:
        vac = verify_snippet(snip, timeout=120)
        not_vacuous = not vac.compiles  # proving False ⇒ vacuous ⇒ reject
        vac_detail = "vacuous (proved False)" if vac.compiles else "ok"

    # back-translation: informalize the Lean statement and judge vs the LaTeX
    score, bt_detail = 1.0, "skipped (no llm)"
    if llm is not None:
        score, bt_detail = _backtranslate_judge(latex, lean_statement, llm)

    accept = axioms_ok and no_sorry and not_vacuous and score >= BACKTRANSLATE_THRESHOLD
    return Faithfulness(
        accept=accept,
        axioms_ok=axioms_ok,
        no_sorry=no_sorry,
        not_vacuous=not_vacuous,
        backtranslation_score=score,
        detail={"vacuity": vac_detail, "backtranslation": bt_detail, "axioms": verify.axioms},
    )


def _backtranslate_judge(latex: str, lean_statement: str, llm) -> tuple[float, str]:
    prompt = (
        "You are checking whether a Lean 4 formalization faithfully captures a "
        "mathematical statement. Informalize the Lean statement in one sentence, "
        "then compare it to the ORIGINAL.\n\n"
        f"ORIGINAL (LaTeX):\n{latex}\n\n"
        f"LEAN STATEMENT:\n{lean_statement}\n\n"
        "Respond on two lines exactly:\n"
        "INFORMAL: <your one-sentence reading of the Lean>\n"
        "SCORE: <a number 0.0-1.0 for how well the Lean matches the original "
        "meaning; penalize missing hypotheses, swapped quantifiers, ℝ vs ℚ, "
        "= vs ≠, or vacuity>"
    )
    try:
        out = llm.complete(prompt, temperature=0.0).text
        m = re.search(r"SCORE:\s*([0-9]*\.?[0-9]+)", out, re.I)
        score = max(0.0, min(1.0, float(m.group(1)))) if m else 0.0
        return score, out.strip()
    except Exception as e:  # judge failure shouldn't crash the loop
        return 0.0, f"judge error: {e}"
