# FormaStat prototype — build & run. (run targets from prototype/)

IMAGE   ?= formastat-proto
COMPOSE  = docker compose -f docker/docker-compose.yml
TIERS   ?= 0,1
DRIVER  ?= gemini

.PHONY: build sanity shell run report lean-build clean help

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN{FS=":.*?## "}{printf "  %-16s %s\n", $$1, $$2}'

build:          ## Build the image (heavy: bakes Mathlib oleans + LeanCopilot model)
	docker build --platform linux/amd64 -f docker/Dockerfile -t $(IMAGE) .

sanity:         ## Milestone-1 gate: Mathlib + toolchain compile (FormaStat.Sanity)
	docker run --rm $(IMAGE) bash -lc 'cd lean && lake build FormaStat.Sanity'

shell:          ## Interactive shell in the container
	docker run --rm -it -v $(PWD)/metrics:/app/metrics $(IMAGE) bash

run:            ## Run the loop  (make run TIERS=0,1 DRIVER=gemini ; needs GEMINI_API_KEY)
	$(COMPOSE) run --rm app python loop/run_loop.py --tiers $(TIERS) --driver $(DRIVER)

lean-build:     ## Build the full corpus (Sanity + all generated theorems)
	docker run --rm -v $(PWD)/lean/FormaStat/Generated:/app/lean/FormaStat/Generated \
	  $(IMAGE) bash -lc 'cd lean && lake build'

report:         ## Show the latest pilot report
	@cat metrics/report.md 2>/dev/null || echo "no report yet — run the loop"

clean:          ## Drop local metrics DB + report (keeps generated Lean)
	rm -f metrics/results.sqlite metrics/report.md
