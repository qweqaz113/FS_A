# Refined Agent

使用优化后提示词与技能包运行完整基准。

活动增强版位于 `src/enterprise_agent/agents/`，包含两轮错误分析与技能演化
形成的规则。第一次精炼前的原始 v1.0 推理包保存在
`../main_agent/original_v1/`。`main_agent` 和 `refined_agent` 当前共享活动增强版
运行实现；两个目录主要区分历史实验阶段及输出位置。

```powershell
uv run python run.py --help
uv run python run.py --row-limit 10
uv run python evaluate.py
```

默认结果写入 `runs/default/`。该入口始终运行完整评测范围，不提供只挑错误样本重跑的流程。
