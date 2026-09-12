# Co2FuLL Dataset

本仓库不重复分发 Co2FuLL/BinKit 原始数据。请通过官方来源获取：

- 代码与数据说明：<https://github.com/GentleCP/Co2FuLL-public>
- 官方数据归档：<https://doi.org/10.6084/m9.figshare.30426451>

按照上游项目说明下载所需文件，然后将未经修改的数据放在 `raw/` 下。
项目默认需要：

```text
raw/
├─ xm-full_top5-250515.csv
├─ Binkit-1.0-normal-strip-top_k_code/
├─ few_shot_examples.json
└─ top5_for_llm-idb_path2func_eas.json
```

`raw/` 被 Git 忽略，实验代码统一通过 `enterprise_agent.benchmarks.co2full.paths` 获取这里的路径。

上游代码仓库采用 Apache-2.0 许可证，Figshare 数据集采用 CC BY 4.0。
使用或重新分发下载内容时，请遵守上游许可证和引用要求。
