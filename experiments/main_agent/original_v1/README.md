# Original FuncSim-Agent v1.0 Snapshot

This directory preserves the exact prompt, skill, reference, and specialist-subagent
files that were used before the first skill-evolution/materialization pass.

Source snapshot:

`experiments/skill_evolution/runs/default/materializer_runs/run_20260601T121455Z/raw/`

The source snapshot is under an ignored `runs/` directory. This checked-in copy exists
so the original reasoning package is not lost when the repository is cloned elsewhere.

## Scope

- `prompts/supervisor.md`: original supervisor prompt.
- `skills/function_similarity/SKILL.md`: original function-similarity skill.
- `skills/function_similarity/references/`: original confidence and decompiler-noise
  references.
- `subagents/`: original prompts for the three specialist subagents.

The deterministic tools are not duplicated here because their SHA-256-identical
implementation is still available under `src/enterprise_agent/agents/tools/`; the
skill-evolution changelogs confirm that neither refinement pass changed tool code.

## Runtime Status

This is an archival snapshot and is not selected automatically by `run.py`. The current
`main_agent` and `refined_agent` entry points both use the active refined package under
`src/enterprise_agent/agents/`. Historical results under `runs/paper_initial/` correspond
to this original v1.0 reasoning package.
