# Main Agent

主实验：用完整的 FuncSim-Agent 流程运行 Co2FuLL 数据集。

`original_v1/` 保存第一次技能演化前的原始 v1.0 提示词、Skill、参考规则和
三个子代理提示词。历史 `runs/paper_initial/` 结果对应这套原始推理包。

当前 `run.py` 调用的是 `src/enterprise_agent/agents/` 下的活动增强版实现，
不会自动加载 `original_v1/`。该快照目前用于历史审计和发布留档；确定性工具
在精炼前后完全相同，因此没有在快照中重复保存。

```powershell
uv run python run.py --help
uv run python run.py --row-limit 10
uv run python evaluate.py
```

默认结果写入 `runs/paper_initial/`，其中包含 `trace/`、`report/` 和 `evaluation/`。
