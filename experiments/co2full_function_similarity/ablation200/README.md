# 200-Pair Targeted Ablation

This experiment evaluates the contribution of the specialist-agent decomposition
on a diagnostic 200-pair stress subset. The subset is intentionally enriched with
initial false positives, initial false negatives, remaining refined errors, and
low-confidence correct cases; it is not a random benchmark sample.

Run every command below from the repository root.

## 1. Build the subset

The builder reuses predictions from the initial and refined full runs:

```text
experiments/co2full_function_similarity/data/eval/predictions.csv
experiments/co2full_function_similarity/data/refine_eval/predictions.csv
```

```bash
uv run python -m experiments.co2full_function_similarity.ablation200.build_subset
```

Outputs:

- `data/ablation200/subset.csv`
- `data/ablation200/subset_summary.json`

## 2. Run ablation variants

```bash
uv run python -m experiments.co2full_function_similarity.ablation200.run_variant --variant single_agent
uv run python -m experiments.co2full_function_similarity.ablation200.run_variant --variant wo_diffprobe
uv run python -m experiments.co2full_function_similarity.ablation200.run_variant --variant wo_noiselens
```

Each command writes traces and reports to
`data/ablation200/<variant>/`. Existing reports are skipped, so interrupted runs
can be resumed. Use `--force` only to recompute completed rows, and use `--dry-run`
to inspect the selected row indices without calling the model.

## 3. Summarize

```bash
uv run python -m experiments.co2full_function_similarity.ablation200.summarize
```

Outputs:

- `data/ablation200/metrics.csv`
- `data/ablation200/bucket_breakdown.csv`
- `data/ablation200/metrics.json`
- `data/ablation200/metrics.md`
