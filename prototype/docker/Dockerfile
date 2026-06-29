# FormaStat prototype runtime — Lean 4 + Mathlib (baked) + LeanCopilot + UlamAI + loop.
#
# Heavy image (~25 GB: Mathlib oleans baked at build time so the container starts
# cold-cache-free). Build for linux/amd64 (LeanCopilot's CTranslate2 backend).
#
#   (run from prototype/)  docker build --platform linux/amd64 -f docker/Dockerfile -t formastat-proto .
#
# Milestone-1 gate (after build):
#   docker run --rm formastat-proto bash -lc 'cd lean && lake build FormaStat.Sanity'
#   docker run --rm formastat-proto bash -lc 'cd lean && lake build FormaStat.CopilotSmoke'

FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl git ca-certificates build-essential \
        python3.12 python3-pip python3-venv \
        libgmp-dev libstdc++6 \
        libopenblas-dev libgomp1 \
    && rm -rf /var/lib/apt/lists/*
# libopenblas + libgomp: LeanCopilot's CTranslate2 backend loads libopenblas.so.0
# (BLAS) and OpenMP at Lean elaboration time.

# elan (Lean toolchain manager) + uv (Python)
RUN curl -fsSL https://elan.lean-lang.org/elan-init.sh | sh -s -- -y
ENV PATH="/root/.elan/bin:/root/.local/bin:${PATH}"
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

WORKDIR /app

# --- Lean layer (cached unless the pin changes) ------------------------------
# Copy only the pin + lakefile first so the expensive Mathlib cache layer is
# reused across source edits.
COPY lean/lean-toolchain lean/lakefile.toml /app/lean/
WORKDIR /app/lean
# Heavy layer: resolve deps + download Mathlib oleans (cached unless pins change).
RUN lake update && lake exe cache get

# --- FormaStat Lean sources + sanity build -----------------------------------
COPY lean/ /app/lean/
RUN lake build FormaStat.Sanity

# Ubuntu ships only `python3`; the loop/compose/Makefile invoke `python`.
RUN ln -sf /usr/bin/python3 /usr/local/bin/python

# --- UlamAI ------------------------------------------------------------------
# UlamAI has no PyPI release; install from source. (No LICENSE file upstream —
# MIT by intent in pyproject; review before redistribution.)
WORKDIR /app
# Non-fatal: UlamAI pulls heavy deps (PyPantograph, LeanDojo) that may not build
# in every base; the default --driver gemini does not need it, so don't block the
# image. `--driver ulam` checks for the binary at runtime and errors cleanly.
RUN (git clone --depth 1 https://github.com/ulamai/ulamai.git /opt/ulamai \
     && cd /opt/ulamai \
     && (./install.sh || pip install --break-system-packages -e .)) \
    || echo "WARN: UlamAI install failed — optional; default --driver gemini still works"

# --- Loop (Python) -----------------------------------------------------------
COPY loop/requirements.txt /app/loop/requirements.txt
RUN pip install --break-system-packages -r /app/loop/requirements.txt
COPY loop/ /app/loop/
COPY curriculum/ /app/curriculum/

ENV PYTHONUNBUFFERED=1
WORKDIR /app
CMD ["bash"]
