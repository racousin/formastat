# FormaStat prototype — LaTeX → Lean 4 autoformalization learning loop

A minimal, functional prototype of the FormaStat autoformalization loop: take a
mathematical-statistics statement in LaTeX, have **Gemini** formalize + prove it
in **Lean 4 / Mathlib**, **verify it with the real Lean compiler**, repair on
compiler feedback, gate for faithfulness, and accumulate a growing verified
corpus — measuring **cost-per-theorem** along the way.

This is the Q1 pilot of the grant in miniature. It runs as a single Docker
container locally and is designed to lift onto the provisioned GCP infra
(Cloud Run / GKE Job, GCS bucket `formastat-app-bucket-eu`, Artifact Registry
`formastat-docker`).

## Stack

| Layer | Choice |
|---|---|
| Harness / driver | **UlamAI** (`ulam`, Gemini-native) — or the built-in **Gemini driver** (default, runnable today) |
| Gap-filler | symbolic tactics (`aesop`/`nlinarith`/`simp_all`/…) — LeanCopilot deferred (build cycle, see lakefile) |
| Model | **Vertex AI Gemini 3** (grant-billed) — start on an AI-Studio key |
| Lean | Lean 4 + Mathlib, **pinned**: `leanprover/lean4:v4.32.0-rc1`, mathlib `v4.32.0-rc1`, LeanCopilot `v4.31.0` |
| Verify | real `lake env lean` compile → errors / open goals |
| Faithfulness | `#print axioms` (no `sorryAx`) + sorry scan + vacuity + back-translation judge (Gemini Flash) |

## Roles & process (per problem)

```
Formalize (Gemini/UlamAI) → Retrieve (corpus + decl hints) → Prove
   → verify (lake) ⟲ Repair on Lean errors (N rounds) → Gap-fill (symbolic: aesop/nlinarith/…)
   → Faithfulness gate → Checkpoint: write FormaStat/Generated/<id>.lean + store row
```

The **learning loop**: each verified `(latex, lean)` pair is added to the corpus
and fed back as few-shot context to later, harder problems — so success should
rise across tiers. Metrics land in `metrics/report.md`.

## Quickstart

```bash
cd prototype
cp .env.example .env          # add GEMINI_API_KEY (AI-Studio, to start)

# 1) Build the runtime (heavy ~25 GB: bakes Mathlib oleans + LeanCopilot model)
make build

# 2) Milestone-1 gate — toolchain is coherent
make sanity                   # Mathlib + toolchain compile (FormaStat.Sanity)

# 3) Run the loop on the easy tiers
GEMINI_API_KEY=$GEMINI_API_KEY make run TIERS=0,1

# 4) See the pilot report
make report
```

## Drivers

- `--driver gemini` (default): drives Gemini directly over the OpenAI-compatible
  endpoint. Fully runnable; owns formalize + repair prompting.
- `--driver ulam`: shells out to the UlamAI CLI. Set `FORMASTAT_ULAM_CMD` to the
  exact headless invocation (confirm UlamAI's command surface in-container;
  placeholders `{latex_file} {name} {out_file}`).

## Grant-billed Vertex path

The default AI-Studio key bills outside the `formastat` project. To measure the
grant's real $/theorem, route through Vertex AI:

1. Enable `aiplatform.googleapis.com` on `formastat`; confirm Gemini 3 region/quota.
2. Bring up the LiteLLM proxy (uncomment the `litellm` service in
   `docker/docker-compose.yml`, which mounts your ADC and uses `litellm/config.yaml`).
3. Set `ULAM_GEMINI_BASE_URL=http://litellm:4000/v1`.

## Curriculum

`curriculum/problems.yaml` — tiers 0→4, simple→hardest:
Tier 0 trivial · Tier 1 analysis/algebra · Tier 2 probability foundations
(`Var`, `IndepFun.variance_add`, Chebyshev, `mgf`) · Tier 3 named results
(Chernoff, Gaussian, `strong_law_ae_real`) · Tier 4 frontier (Cramér–Rao,
M-estimators, k-NN/Stone, minimax, **CLT** — not yet in Mathlib; expected
failures are recorded, not hidden).

## Outputs

- `lean/FormaStat/Generated/<id>.lean` — verified theorems (the corpus).
- `lean/FormaStat.lean` — auto-maintained imports of the corpus (`make lean-build` checks it all still compiles).
- `metrics/results.sqlite` — every attempt (status, axioms, tokens, $, faithfulness).
- `metrics/report.md` — per-tier success rate + marginal $/theorem.

## Scale to GCP (post-prototype)

Same image runs as a **GKE Job** (16–32 GB nodes; PersistentVolume for a warm
`.lake`) or **Cloud Run Job** (bake oleans into the image — mind the 32 GiB
tmpfs ceiling). Push to `europe-west1-docker.pkg.dev/formastat/formastat-docker/`.
Corpus + Mathlib-cache tarballs → the `formastat-app-bucket-eu` bucket. Metadata
→ Postgres + pgvector for semantic search (grant architecture).

## Known limitations / things to confirm at run time

- **UlamAI CLI surface:** its exact non-interactive command is confirmed in the
  container; the adapter is templated (`FORMASTAT_ULAM_CMD`) until then. The
  Gemini driver is the runnable default meanwhile.
- **LeanCopilot deferred (build cycle):** LeanCopilot v4.31.0 can't co-build with
  Mathlib v4.32.0-rc1 — it forces `:shared` precompiled builds that hit a Lake
  cycle (`batteries:shared ↔ BatteriesRecycling:shared ↔ LeanCopilot.Models.Registry`)
  because Mathlib's pinned batteries (`954dbc9`) predates the batteries#1868 fix,
  and overriding batteries would force a from-source Mathlib rebuild (cache miss).
  Gap-filling uses symbolic tactics instead (`run_loop.GAP_TACTIC`); re-add
  LeanCopilot when a tag builds against cache-backed Mathlib. Separately,
  `require mathlib` must be **last** in the lakefile or `cache get` mis-hashes.
- **UlamAI license:** MIT by intent (in `pyproject`) but no LICENSE file upstream
  — review before redistribution.
- **Vacuity check** is a heuristic (rewrites the conclusion to `False`); treat as
  a signal, not proof of correctness.
