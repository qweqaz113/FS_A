# FuncSim-Agent

FuncSim-Agent 是一个面向二进制函数相似性判断的多智能体实验项目。核心代码、数据集和实验被明确分开：公共能力放在 `src/`，原始数据放在 `datasets/`，每个实验在 `experiments/` 下独立管理脚本与结果。

## 项目结构

```text
study/
├─ src/enterprise_agent/
│  ├─ agents/                       # 智能体、子智能体、提示词、工具和技能
│  ├─ benchmarks/co2full/           # Co2FuLL 公共加载、执行、记录、评估逻辑
│  └─ infra/                        # 模型、配置和运行时基础设施
├─ datasets/co2full/raw/            # 原始 CSV、反编译代码和 few-shot 数据
├─ experiments/
│  ├─ main_agent/                   # 主实验
│  ├─ refined_agent/                # 优化后智能体实验
│  ├─ co2full_v4_baseline/          # 论文式 LLM 基线
│  ├─ ablation_200/                 # 200 样本组件消融
│  └─ skill_evolution/              # 错误分析和技能进化
├─ data/sandbox/                    # Docker 智能体运行沙箱
├─ tests/
├─ compose.yaml
└─ pyproject.toml
```

每个实验遵循同一约定：

```text
experiments/<experiment>/
├─ README.md                        # 该实验目的和命令
├─ experiment.yaml                 # 数据、入口和输出位置
├─ run.py 或专用执行脚本
├─ evaluate.py                     # 需要统一评估时提供
└─ runs/                            # 该实验的历史结果和新结果
```

要运行哪个实验，直接进入对应目录查看 `README.md` 和脚本即可。脚本按自身位置解析路径，不依赖当前工作目录。

## 环境准备

```powershell
uv sync
Copy-Item .env.example .env
```

在 `.env` 中配置模型供应商、模型名和密钥。若使用 Docker 沙箱：

```powershell
docker compose up -d agent-sandbox
```

## 数据集

Co2FuLL 原始数据统一位于 `datasets/co2full/raw/`：

本仓库不重复分发原始数据。请参考
[Co2FuLL 官方项目](https://github.com/GentleCP/Co2FuLL-public)获取代码、数据和上游说明；
官方数据归档位于 [Figshare](https://doi.org/10.6084/m9.figshare.30426451)。

```text
raw/
├─ xm-full_top5-250515.csv
├─ Binkit-1.0-normal-strip-top_k_code/
├─ few_shot_examples.json
└─ top5_for_llm-idb_path2func_eas.json
```

原始数据只保存一份，各实验通过公共加载器读取，不再复制到实验目录。

## 运行主实验

```powershell
Set-Location experiments/main_agent
uv run python run.py --help
uv run python run.py --row-limit 10
uv run python evaluate.py
```

结果默认写入 `experiments/main_agent/runs/paper_initial/`：

- `trace/`：完整智能体调用轨迹
- `report/`：每个函数对的最终判断
- `evaluation/`：指标、预测表和错误表

## 运行其他实验

优化后智能体：

```powershell
Set-Location experiments/refined_agent
uv run python run.py --row-limit 10
uv run python evaluate.py
```

Co2FuLL v4 基线：

```powershell
Set-Location experiments/co2full_v4_baseline
uv run python run.py --dry-run
uv run python run.py --row-limit 10
uv run python evaluate.py
```

200 样本消融：

```powershell
Set-Location experiments/ablation_200
uv run python build_subset.py
uv run python run_variant.py --variant single_agent
uv run python run_variant.py --variant wo_diffprobe
uv run python run_variant.py --variant wo_noiselens
uv run python summarize.py
```

技能进化：

```powershell
Set-Location experiments/skill_evolution
uv run python run_error_analysis.py --help
uv run python run_package_materializer.py --help
```

## 公共代码边界

以下能力统一维护在 `src/enterprise_agent/benchmarks/co2full/`：

- `paths.py`：项目根目录和数据集默认路径
- `dataset.py`：CSV、函数对和伪代码加载
- `runner.py`：单个函数对执行流程
- `recorder.py`：trace 与 report 落盘
- `batch.py`：批量调度、并发和断点续跑
- `evaluation.py`：预测汇总与指标计算

实验目录只保留该实验独有的参数、提示策略、样本选择和入口，不复制公共实现。

## 测试

```powershell
uv run pytest
uv run ruff check .
```

`runs/`、原始数据和沙箱运行文件均被 Git 忽略；实验代码、说明和配置正常纳入版本管理。
