# Main Agent

主实验：用完整的 FuncSim-Agent 流程运行 Co2FuLL 数据集。

```powershell
uv run python run.py --help
uv run python run.py --row-limit 10
uv run python evaluate.py
```

默认结果写入 `runs/paper_initial/`，其中包含 `trace/`、`report/` 和 `evaluation/`。
