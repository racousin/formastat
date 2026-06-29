"""Autoformalization driver(s) — the Formalizer + Prover + Repair roles.

Two interchangeable backends behind one interface:

* GeminiDriver  — drives Gemini directly over the OpenAI-compatible endpoint
                  (UlamAI's same base_url). Fully runnable today; owns the
                  formalize + repair prompting. Default.

* UlamDriver    — shells out to the UlamAI CLI (`ulam`). UlamAI's exact
                  non-interactive command surface is confirmed at run time
                  inside the container, so the invocation is a configurable
                  template (env FORMASTAT_ULAM_CMD). Select with --driver ulam.

Both return a `Candidate` (a full compilable Lean snippet) that the orchestrator
verifies with `lean_verify` and gates with `faithfulness`.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from llm import Gemini

NAMING_GOTCHAS = (
    "Mathlib naming gotchas (Mathlib v4.32.0-rc1): expectation is the integral "
    "`∫ x, X x ∂μ` or notation `𝔼[X]`/`μ[X]` (there is NO `expectation`); the "
    "strong law is `ProbabilityTheory.strong_law_ae` / `strong_law_ae_real` "
    "(NO `strong_law_of_large_numbers`); conditional expectation is "
    "`MeasureTheory.condExp` (camelCase); use `MemLp` not `Memℒp`; "
    "`poissonMeasure` not `poissonPMF`; variance is `ProbabilityTheory.variance` "
    "/ notation `Var[X]`; independence is `ProbabilityTheory.IndepFun`."
)

SYSTEM = (
    "You are an expert Lean 4 + Mathlib autoformalizer. You translate a "
    "mathematical statement into a single Lean 4 `theorem` that type-checks "
    "against Mathlib, and you prove it. Output ONLY one fenced ```lean code "
    "block: the necessary `import`s followed by exactly one `theorem`. Never "
    "use `sorry`, `admit`, or `native_decide`. Prefer Mathlib lemmas and the "
    "tactics `simp`, `ring`, `nlinarith`, `positivity`, `exact?`, `aesop`.\n"
    + NAMING_GOTCHAS
)


@dataclass
class Candidate:
    code: str                 # full snippet: imports + theorem
    theorem_name: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    error: str = ""


def theorem_name_for(problem_id: str) -> str:
    # problem ids are already [a-z0-9_]; valid Lean identifiers
    return problem_id


def module_name_for(problem_id: str) -> str:
    return "".join(p.capitalize() for p in re.split(r"[_\W]+", problem_id) if p)


def _extract_lean(text: str) -> str:
    # Collect ALL fenced blocks and concatenate in order (LLMs sometimes split
    # imports and the theorem across separate ```lean blocks); fall back to raw.
    blocks = re.findall(r"```(?:lean)?\s*(.*?)```", text, re.S)
    return ("\n".join(b.strip() for b in blocks) if blocks else text).strip()


class GeminiDriver:
    name = "gemini"

    def __init__(self, model: str | None = None) -> None:
        self.llm = Gemini(model=model)

    def formalize_and_prove(self, problem: dict, context: str) -> Candidate:
        name = theorem_name_for(problem["id"])
        prompt = (
            f"{context}\n\n"
            f"Formalize and prove the following as `theorem {name}`.\n\n"
            f"STATEMENT:\n{problem['latex']}\n"
        )
        if problem.get("target_mathlib_decls"):
            prompt += f"\nRelevant Mathlib declarations: {', '.join(problem['target_mathlib_decls'])}\n"
        c = self.llm.complete(prompt, system=SYSTEM)
        return Candidate(_extract_lean(c.text), name, c.input_tokens, c.output_tokens, c.model)

    def repair(self, problem: dict, prev: Candidate, errors: list[str], context: str) -> Candidate:
        prompt = (
            f"{context}\n\n"
            f"Your previous Lean attempt failed to compile. Fix it. Output ONLY "
            f"the corrected ```lean block (imports + the single theorem "
            f"`{prev.theorem_name}`), no `sorry`.\n\n"
            f"PREVIOUS:\n```lean\n{prev.code}\n```\n\n"
            f"LEAN ERRORS:\n" + "\n".join(f"- {e}" for e in errors[:12]) + "\n"
        )
        c = self.llm.complete(prompt, system=SYSTEM)
        return Candidate(
            _extract_lean(c.text), prev.theorem_name, c.input_tokens, c.output_tokens, c.model
        )


class UlamDriver:
    """Drives the UlamAI CLI. UlamAI's headless command is confirmed in-container;
    set FORMASTAT_ULAM_CMD to the exact invocation. Placeholders available:
      {latex_file}  path to a file containing the LaTeX statement
      {name}        desired theorem name
      {out_file}    path where the driver should read the produced Lean from
    The command must write the final Lean snippet to {out_file} (or stdout)."""

    name = "ulam"
    DEFAULT_CMD = "ulam prove --input {latex_file} --name {name} --out {out_file}"

    def __init__(self, model: str | None = None) -> None:
        if not _on_path("ulam"):
            raise RuntimeError(
                "`ulam` not on PATH. Install UlamAI (brew install ulamai, or "
                "git clone github.com/ulamai/ulamai && ./install.sh) or use "
                "--driver gemini."
            )
        self.cmd_tmpl = os.environ.get("FORMASTAT_ULAM_CMD", self.DEFAULT_CMD)
        self.model = model or os.environ.get("ULAM_GEMINI_MODEL", "gemini-3.1-pro-preview")

    def formalize_and_prove(self, problem: dict, context: str) -> Candidate:
        name = theorem_name_for(problem["id"])
        with tempfile.TemporaryDirectory() as d:
            latex_file = Path(d) / "statement.tex"
            out_file = Path(d) / "out.lean"
            latex_file.write_text(problem["latex"], encoding="utf-8")
            cmd = self.cmd_tmpl.format(latex_file=latex_file, name=name, out_file=out_file)
            proc = subprocess.run(
                shlex.split(cmd), capture_output=True, text=True, timeout=1800
            )
            code = out_file.read_text(encoding="utf-8") if out_file.exists() else proc.stdout
            err = "" if proc.returncode == 0 else (proc.stderr or "ulam returned nonzero")
            return Candidate(_extract_lean(code), name, model=self.model, error=err)

    def repair(self, problem: dict, prev: Candidate, errors: list[str], context: str) -> Candidate:
        # UlamAI runs its own internal repair loop; re-invoking is the simplest
        # orchestrator-level retry. Override via FORMASTAT_ULAM_CMD if it exposes
        # an explicit repair subcommand.
        return self.formalize_and_prove(problem, context)


def _on_path(exe: str) -> bool:
    from shutil import which
    return which(exe) is not None


def make_driver(name: str, model: str | None = None):
    return {"gemini": GeminiDriver, "ulam": UlamDriver}[name](model=model)
