# FuncSim-Agent

Official implementation of **FuncSim-Agent: An Agent-Based Framework for Binary
Function Similarity Detection**.

FuncSim-Agent verifies Top-K binary-function candidates produced by a retrieval
model. It combines deterministic pseudocode analysis with three specialist agents
and a supervisor:

- **SemMatch-Agent** collects evidence for semantic equivalence.
- **DiffProbe-Agent** searches for concrete behavioral conflicts.
- **NoiseLens-Agent** distinguishes compiler, architecture, and decompiler variation.
- **Supervisor/FSA** integrates the evidence and emits an auditable verdict.

The implementation is built with
[DeepAgents](https://github.com/langchain-ai/deepagents) and uses DeepSeek models
through LangChain. The released source contains the refined verification skill used
for the paper's final evaluation.

## Repository layout

```text
.
|-- src/enterprise_agent/
|   |-- agents/
|   |   |-- prompts/          # Supervisor and refinement prompts
|   |   |-- skills/           # FuncSim Verification Skill
|   |   |-- subagents/        # Three specialist agent definitions
|   |   |-- tools/            # Deterministic pseudocode analysis
|   |   `-- backends/         # DeepAgents Docker sandbox adapter
|   `-- domain/               # Input and verdict schemas
|-- experiments/co2full_function_similarity/
|   |-- run_batch.py          # Initial/final Top-K verification driver
|   |-- evaluate_reports.py   # P, R, F2, Nv, and error analysis
|   |-- skill_evolution/      # Offline failure analysis and materialization
|   `-- ablation200/          # Targeted 200-pair component ablation
|-- tests/                    # Tests that do not call an LLM
|-- compose.yaml              # Reproducible DeepAgents sandbox
|-- .env.example              # Runtime configuration template
`-- pyproject.toml
```

Datasets, model traces, reports, and generated refinement artifacts are intentionally
excluded from Git.

## Requirements

- Python 3.13
- [uv](https://docs.astral.sh/uv/)
- Docker with Docker Compose
- A DeepSeek API key for LLM-based runs
- The Co2FuLL/BinKit-derived Top-K candidate data used by the paper

## Installation

```bash
git clone <repository-url>
cd funcsim-agent
uv sync --dev
```

Copy the environment template and add your API key:

```bash
cp .env.example .env
```

On PowerShell:

```powershell
Copy-Item .env.example .env
```

At minimum, set:

```dotenv
DEEPSEEK_API_KEY=your_api_key
LLM_MODEL=deepseek:deepseek-v4-flash
```

Start the sandbox used by DeepAgents:

```bash
docker compose up -d
```

Stop it after the experiment with `docker compose down`.

## Dataset layout

The data are not redistributed in this repository. After obtaining the dataset from
its original source, arrange it as follows:

```text
experiments/co2full_function_similarity/data/
`-- dbs/
    |-- xm-full_top5-250515.csv
    `-- Binkit-1.0-normal-strip-top_k_code/
        `-- <project>/
            `-- <binary-name>.json
```

The pair CSV must contain at least these columns:

```text
bin_name_1,fva_1,bin_name_2,fva_2,label
```

Each binary JSON file maps a function address to an object containing
`pseudo_code`. Use `--csv-path` and `--db-root` to select a different layout.

## Quick validation without an API

Run the unit tests:

```bash
uv run pytest
```

Run a small deterministic-only batch to validate the dataset loader and output
layout without calling an LLM:

```bash
uv run python -m experiments.co2full_function_similarity.run_batch \
  --row-limit 2 \
  --max-workers 1 \
  --deterministic-only
```

## Run FuncSim-Agent

Start with a small LLM-backed smoke test:

```bash
uv run python -m experiments.co2full_function_similarity.run_batch \
  --row-limit 2 \
  --max-workers 1
```

Run the complete candidate set:

```bash
uv run python -m experiments.co2full_function_similarity.run_batch \
  --row-limit 5001 \
  --max-workers 32
```

The command writes one JSON trace and one normalized report per candidate pair:

```text
data/trace/                 # Complete DeepAgents execution traces
data/report/                # Normalized similarity verdicts
```

These paths are relative to `experiments/co2full_function_similarity/`. Existing
reports are skipped, so an interrupted run can be resumed. Pass `--overwrite` only
when a completed pair should be recomputed.

> **Cost warning:** LLM-backed batch runs incur API charges. Validate the setup with
> `--row-limit 2 --max-workers 1` before starting the full benchmark.

List all batch options with:

```bash
uv run python -m experiments.co2full_function_similarity.run_batch --help
```

## Evaluate reports

Evaluate the default report directory:

```bash
uv run python -m experiments.co2full_function_similarity.evaluate_reports
```

This produces `metrics.json`, `metrics.md`, `predictions.csv`, and `errors.csv` in
`data/eval/`. For a refined full run:

```bash
uv run python -m experiments.co2full_function_similarity.evaluate_reports \
  --report-dir experiments/co2full_function_similarity/data/refinement_full/report \
  --eval-dir experiments/co2full_function_similarity/data/refine_eval
```

The D1 evaluation uses 500 target queries as the recall denominator. Override it
with `--total-target-queries` for another benchmark.

## Offline skill refinement

FuncSim-Agent turns failed judgments into reusable verification guidance in three
steps.

1. Analyze incorrect reports and produce structured failure records:

   ```bash
   uv run python -m experiments.co2full_function_similarity.skill_evolution.run_error_analysis
   ```

2. Materialize an updated prompt/skill package in the Docker sandbox:

   ```bash
   uv run python -m experiments.co2full_function_similarity.skill_evolution.run_package_materializer
   ```

3. Review the sandbox output, apply the accepted package, and run the full benchmark
   into separate output directories:

   ```bash
   uv run python -m experiments.co2full_function_similarity.run_batch_refinement \
     --row-limit 5001 \
     --max-workers 32
   ```

The online verifier never receives ground-truth labels. Labels are used only by the
offline failure-analysis stage.

## Component ablation

Build the targeted 200-pair stress subset:

```bash
uv run python -m experiments.co2full_function_similarity.ablation200.build_subset
```

Run the new variants:

```bash
uv run python -m experiments.co2full_function_similarity.ablation200.run_variant --variant single_agent
uv run python -m experiments.co2full_function_similarity.ablation200.run_variant --variant wo_diffprobe
uv run python -m experiments.co2full_function_similarity.ablation200.run_variant --variant wo_noiselens
```

Summarize the ablation:

```bash
uv run python -m experiments.co2full_function_similarity.ablation200.summarize
```

See [the ablation notes](experiments/co2full_function_similarity/ablation200/README.md)
for subset construction and output details.

## Paper results

| Configuration | Precision | Recall | F2 | Nv |
|---|---:|---:|---:|---:|
| FuncSim-Agent | 91.8 | 96.6 | 95.6 | 526 |
| FuncSim-Agent (refined) | **97.0** | 96.0 | **96.2** | **495** |

The table reports the 4,994 valid candidate-pair evaluations described in the paper.
Exact results depend on the model endpoint and provider behavior.

## Reproducibility notes

- The repository defaults to `deepseek:deepseek-v4-flash`, matching the paper.
- Full reports are excluded because they contain large model traces and derived
  dataset content.
- The Docker sandbox makes tool execution and skill paths consistent across hosts.
- Randomness and provider-side model updates may cause small differences between
  reruns.
- Do not place API keys in source files. `.env` is ignored by Git.

## Citation

If this code is useful in your research, please cite the FuncSim-Agent paper. Formal
BibTeX and `CITATION.cff` metadata will be added when the author list and publication
record are finalized.

## License

A public software license has not yet been selected. Add a `LICENSE` file before the
GitHub release so that reuse conditions are explicit.
