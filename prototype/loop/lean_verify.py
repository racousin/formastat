"""Ground-truth Lean verification.

Compiles a snippet against the pinned Mathlib + LeanCopilot project by running
`lake env lean` on a temp file inside `lean/`. Returns structured diagnostics.

Decision rule (mirrors the Lean REPL contract):
  any error           -> compiles = False
  no errors, no sorry -> compiles = True, clean
  `sorry`/`admit`     -> compiles may be True but incomplete (not accepted)

We use `lake env lean <file>` rather than the REPL to avoid an extra dependency
and to reuse the project's olean cache directly. `lean-interact` is a drop-in
alternative if you prefer a long-lived server (see README).
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

LEAN_PROJECT = Path(__file__).resolve().parents[1] / "lean"

_ERR_RE = re.compile(r"^(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+): (?P<sev>error|warning): (?P<msg>.*)$")
# whole-token match (Lean idents may contain apostrophes, e.g. foo')
_SORRY_RE = re.compile(r"(?<![A-Za-z0-9_'])(sorry|admit|native_decide)(?![A-Za-z0-9_'])")


@dataclass
class VerifyResult:
    compiles: bool
    clean: bool                      # compiles AND no sorry/admit/native_decide
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    used_sorry: bool = False
    axioms: str = ""                 # output of `#print axioms` if requested
    raw: str = ""


def _strip_lean_comments(code: str) -> str:
    """Drop `-- line` and nested `/- block -/` comments so the sorry scan
    doesn't false-positive on prose like `-- no sorry needed`."""
    out: list[str] = []
    i, n, depth = 0, len(code), 0
    while i < n:
        if depth == 0 and code.startswith("--", i):
            j = code.find("\n", i)
            i = n if j == -1 else j
        elif code.startswith("/-", i):
            depth += 1
            i += 2
        elif depth > 0 and code.startswith("-/", i):
            depth -= 1
            i += 2
        else:
            if depth == 0:
                out.append(code[i])
            i += 1
    return "".join(out)


def _scan_sorry(code: str) -> bool:
    return _SORRY_RE.search(_strip_lean_comments(code)) is not None


def verify_snippet(
    code: str,
    *,
    project: Path = LEAN_PROJECT,
    print_axioms_of: str | None = None,
    timeout: int = 300,
) -> VerifyResult:
    """Compile `code` in the Lean project. If `print_axioms_of` is given, append
    a `#print axioms <name>` and capture its output for the faithfulness gate."""
    body = code
    if print_axioms_of:
        body = f"{code}\n\n#print axioms {print_axioms_of}\n"

    with tempfile.NamedTemporaryFile(
        "w", suffix=".lean", dir=str(project), delete=False, encoding="utf-8"
    ) as f:
        f.write(body)
        tmp = Path(f.name)

    try:
        proc = subprocess.run(
            ["lake", "env", "lean", tmp.name],
            cwd=str(project),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        tmp.unlink(missing_ok=True)
        return VerifyResult(False, False, errors=[f"timeout after {timeout}s"])
    finally:
        # `lake env lean` may also drop a .olean next to the temp; clean both
        tmp.unlink(missing_ok=True)
        Path(str(tmp).replace(".lean", ".olean")).unlink(missing_ok=True)

    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    errors, warnings, axioms_lines = [], [], []
    in_axioms = False  # true while inside a multi-line `[...]` axiom list
    name = print_axioms_of or ""
    for line in out.splitlines():
        m = _ERR_RE.match(line)
        if m:
            (errors if m["sev"] == "error" else warnings).append(
                f'{m["line"]}:{m["col"]} {m["msg"]}'
            )
            in_axioms = False
            continue
        if print_axioms_of:
            starts = (
                "depends on axioms" in line
                or "does not depend on any axioms" in line
                or line.lstrip().startswith(f"'{name}'")
            )
            if starts:
                axioms_lines.append(line.strip())
                in_axioms = "[" in line and "]" not in line
            elif in_axioms:
                axioms_lines.append(line.strip())
                if "]" in line:
                    in_axioms = False

    used_sorry = _scan_sorry(code)
    compiles = proc.returncode == 0 and not errors
    return VerifyResult(
        compiles=compiles,
        clean=compiles and not used_sorry,
        errors=errors,
        warnings=warnings,
        used_sorry=used_sorry,
        axioms="\n".join(axioms_lines).strip(),
        raw=out,
    )
