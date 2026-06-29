# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

**FormaStat** is a Lean 4 autoformalization program (SCAI / Sorbonne Université; PI Raphaël Cousin, scientific co-lead Gérard Biau / LPSM). Goal: produce a public, *verified* Lean 4 library of **mathematical statistics** (estimator theory, nonparametric methods, minimax, high-dimensional stats — the van der Vaart / Devroye-Györfi-Lugosi / Giraud tradition), plus a benchmark and web UI. The funding rationale is in `FormaStat_GCP_Request_EN (1).docx`.

The repo has **two independent halves**:

1. **`terraform/`** — GCP infrastructure for the `formastat` project (Cloud Run service, GCS bucket, Artifact Registry, IAM/service account). Local state, applied and live.
2. **`prototype/`** — the **minimal functional autoformalization loop**: take a LaTeX/NL statement → drive an LLM (Gemini, via UlamAI or a direct driver) to produce a Lean 4 theorem + proof → **verify with the real Lean compiler against Mathlib** → repair on compiler errors → faithfulness-gate → accumulate a growing verified corpus, measuring cost-per-theorem. This is the grant's Q1 pilot in miniature.

The design rationale and decisions are captured in the approved plan at `~/.claude/plans/snappy-finding-stonebraker.md` (read it before large changes to `prototype/`).

## Common commands

```bash
# --- Prototype (run from prototype/) ---
make build           # build the Docker image (bakes Mathlib oleans; ~4 GB; one-time ~8 min)
make sanity          # Milestone-1 gate: FormaStat.Sanity compiles against real Mathlib
make run TIERS=0,1   # run the loop on tiers 0-1 (needs GEMINI_API_KEY); DRIVER=gemini|ulam
make report          # print metrics/report.md (per-tier success, $/theorem)
make lean-build      # build the full corpus (Sanity + all generated theorems)
make shell           # interactive shell in the image

# Run the loop directly (inside the container or a matching env):
python loop/run_loop.py --tiers 0,1 --driver gemini --max-rounds 4

# --- Terraform (run from terraform/) ---
terraform plan && terraform apply         # ADC must be admin@scai-sorbonne.fr (see below)

# --- gcloud context switch (targets exist in BOTH repos' Makefiles) ---
make gcp-formastat   # gcloud CLI -> formastat / admin@scai-sorbonne.fr
make gcp-rl          # gcloud CLI -> default config (the other RL project / gmail)
```

There is **no separate lint/test runner**; correctness is established by (a) `make sanity` + the Docker build, and (b) Lean verification inside the loop itself. Python loop modules are plain stdlib + `openai` + `PyYAML`; validate edits with `python3 -m py_compile loop/*.py`.

## Architecture — the autoformalization loop (`prototype/loop/`)

The loop is a pipeline of **roles**, orchestrated by `run_loop.py:solve()` per curriculum problem:

```
Formalize (LLM) → Retrieve (corpus + decl hints) → Prove (LLM)
   → verify (lake env lean) ⟲ Repair on Lean errors (N rounds) → Gap-fill (symbolic tactics)
   → Faithfulness gate → Checkpoint (write Lean file + register import + store row)
```

Understanding it requires these files together:

- **`run_loop.py`** — orchestrator. `solve()` runs the verify→repair loop, applies `gap_fill()` when a proof compiles but contains `sorry`, gates with `faithfulness.gate()`, and on acceptance calls `write_generated()` (writes `lean/FormaStat/Generated/<Module>.lean`) + `register_import()` (appends `import …` under the marker in `lean/FormaStat.lean`, so `lake build` keeps the corpus buildable). Writes `metrics/report.md`.
- **`ulam_adapter.py`** — the **driver abstraction** (Formalizer + Prover + Repair roles). Two interchangeable backends behind one interface: `GeminiDriver` (drives Gemini directly over the OpenAI-compatible endpoint — the runnable default) and `UlamDriver` (shells out to the `ulam` CLI; its exact headless invocation is set via `FORMASTAT_ULAM_CMD`). Both return a `Candidate` (a compilable Lean snippet). The `SYSTEM` prompt carries Mathlib naming gotchas — **keep it current**.
- **`lean_verify.py`** — ground truth. `verify_snippet()` runs `lake env lean` on a temp file inside `lean/` and parses diagnostics. Decision rule: any `error` → not compiling; clean + no `sorry` → accepted; `sorry`/`admit`/`native_decide` → incomplete. Optionally captures `#print axioms`.
- **`faithfulness.py`** — "compiles ≠ correct" gate: `_check_axioms` (fail-closed allowlist `{propext, Classical.choice, Quot.sound}`, rejects `sorryAx`/user axioms/native_decide), vacuity check (rewrites the conclusion to `False` keeping hypotheses — needs `import Mathlib`, so it's a real Lean compile), and a back-translation LLM judge.
- **`store.py`** — SQLite store; verified rows form the corpus. `verified_for_context()` feeds prior `(latex, lean)` pairs back as few-shot context. Cost-per-theorem comes from `PRICING_USD_PER_MTOK`.
- **`retriever.py`** — assembles the prompt context (corpus few-shot + the problem's `target_mathlib_decls`). This few-shot accumulation **is the "learning loop"** (no fine-tuning in v1): later/harder tiers benefit from earlier verified results.
- **`llm.py`** — thin Gemini client over the OpenAI-compatible endpoint (`base_url` overridable for AI-Studio vs Vertex).

The curriculum is `prototype/curriculum/problems.yaml` — tiers 0 (trivial) → 4 (frontier: Cramér-Rao, M-estimators, k-NN/Stone, minimax, **CLT** — these are *not* yet in Mathlib and are expected to fail; failures are recorded, not hidden). Each entry's `target_mathlib_decls` are real, verified-to-exist Mathlib names.

## Critical, non-obvious knowledge (don't relearn these the hard way)

**Lean / Mathlib build (`prototype/lean/`, `prototype/docker/Dockerfile`):**
- Pinned triple: `lean-toolchain` = `leanprover/lean4:v4.32.0-rc1`, mathlib `rev = v4.32.0-rc1`. Do not bump casually.
- In `lakefile.toml`, **`require mathlib` must be LAST** — otherwise `lake exe cache get` computes wrong hashes and can't fetch prebuilt oleans (falls back to a multi-hour from-source build).
- **LeanCopilot is intentionally absent.** LeanCopilot v4.31.0 forces `:shared` precompiled builds that hit a Lake build cycle (`batteries:shared ↔ BatteriesRecycling:shared ↔ LeanCopilot.Models.Registry`) against the batteries commit Mathlib v4.32.0-rc1 pins (`954dbc9`, pre-batteries#1868). Pinning batteries to a fixed commit forces a cache-miss from-source Mathlib rebuild. So gap-filling uses **symbolic tactics** (`run_loop.GAP_TACTIC` = `aesop | simp_all | norm_num | nlinarith | omega | positivity`). Re-add LeanCopilot only when a tag builds against cache-backed Mathlib (see `lakefile.toml` comment).
- Docker: Ubuntu ships `python3` only → the image symlinks `python`. Mathlib oleans are baked at build time; `cache get` is its own layer so it stays cached across edits.
- The corpus root `lean/FormaStat.lean` has a `-- FORMASTAT-GENERATED-IMPORTS` marker; `register_import()` appends below it via a **line-anchored** regex (the marker line has a trailing parenthetical — never splice into it).

**LLM driver:**
- Default `--driver gemini` is fully runnable with a `GEMINI_API_KEY` (AI-Studio). For grant-billed Vertex, point `ULAM_GEMINI_BASE_URL` at the LiteLLM proxy (`prototype/litellm/config.yaml`, the commented `litellm` service in `docker-compose.yml`).
- `--driver ulam` uses the installed `ulam` CLI; confirm its non-interactive command and set `FORMASTAT_ULAM_CMD`. UlamAI's package is `ulam-prover` (CLI `ulam`); upstream has no LICENSE file (MIT by intent) — review before redistribution.

**GCP / infra (`terraform/`):**
- The `formastat` project is owned by **`admin@scai-sorbonne.fr`**, NOT the local gmail account. Terraform authenticates via **Application Default Credentials** set to admin (`gcloud auth application-default login` → admin, then `set-quota-project formastat`). The RL project's Terraform uses a key file and is unaffected.
- The org enforces **Domain Restricted Sharing** (`iam.allowedPolicyMemberDomains`): you **cannot** add gmail principals, and `allUsers` (anonymous public Cloud Run) is blocked. So `allow_unauthenticated` defaults false; grant access via `invoker_members` with in-domain principals (e.g. `domain:scai-sorbonne.fr`). True public browser access would need an org-admin exception or an IAP load balancer.
- Cloud Run `cloud_run.tf` uses `ignore_changes` on the container image — real deploys are driven by `gcloud run deploy` / CI, not Terraform.

## When extending the loop

- Add curriculum problems to `problems.yaml` with real Mathlib `target_mathlib_decls`; check names against current Mathlib (gotchas: expectation is `∫`/`𝔼[X]` not `expectation`; `strong_law_ae`/`strong_law_ae_real` not `strong_law_of_large_numbers`; `MeasureTheory.condExp`; `MemLp`; `poissonMeasure`).
- Keep `lean_verify`/`faithfulness` regex parsers fail-closed: a parse miss should reject (for the gate) or treat as not-compiling, never silently accept.
- New verified theorems must land in `lean/FormaStat/Generated/` AND be reachable from `FormaStat.lean` so `make lean-build` keeps the whole corpus compiling.
