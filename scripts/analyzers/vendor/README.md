# vendor（上游原文）

`scripts/analyzers/vendor/` 保留 6 个可调用分析器的实现和 vLLM 调优资料。环境快照比对只保留 `compare_dumps.py`。上游版本固定为 `6519f6f`。 [保留范围](../NOTICE.md) · [来源清单](../PROVENANCE.yaml)

阅读上游 `SKILL.md` / `README.md` 时注意：其中「自动安装依赖」「现场采集」「绑核执行」等步骤在本仓**不会自动执行**。诊断中的调用路径、开关和失败退化以 [../README.md](../README.md) 与 `skills/diagnose/references/analyzer-dispatch.md` 为准；上游文档只作算法与输入格式参考。
