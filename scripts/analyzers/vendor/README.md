# vendor（上游原文）

`scripts/analyzers/vendor/` 保留 8 个上游 skill 的内容。上游版本固定为 `6519f6f`。来源、许可与改动见 [../NOTICE.md](../NOTICE.md) 与 [../PROVENANCE.yaml](../PROVENANCE.yaml)。

阅读上游 `SKILL.md` / `README.md` 时注意：其中「自动安装依赖」「现场采集」「绑核执行」等步骤在本仓**不会自动执行**。诊断中的调用路径、开关和失败退化以 [../README.md](../README.md) 与 `skills/diagnose/references/analyzer-dispatch.md` 为准；上游文档只作算法与输入格式参考。
