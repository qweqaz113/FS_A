# Refined Agent

使用优化后提示词与技能包运行完整基准。

```powershell
uv run python run.py --help
uv run python run.py --row-limit 10
uv run python evaluate.py
```

默认结果写入 `runs/default/`。该入口始终运行完整评测范围，不提供只挑错误样本重跑的流程。
