# 200-pair Ablation

在 200 个高难度样本上进行组件消融。

```powershell
uv run python build_subset.py
uv run python run_variant.py --help
uv run python summarize.py
```

输入来自 main-agent 与 refined-agent 的评估结果，所有消融产物写入 `runs/default/`。
