# 自动收尾端到端验证用例

本 PR 只用于验证 dsh-sleuth-autoclose 插件对 GitHub PR 合入的自动检测：

1. 台账登记一条 `platform=github`、`repo=stfdtj/ascend-sleuth` 的记录；
2. 插件按 1 分钟间隔执行 `groom_sweep`（`--fetch`），`pr_status` 通过 GitHub 平台适配器查询本 PR 状态；
3. 合入后状态由 `open` 变为 `merged`，面板「自动收尾」页出现该草稿并完成收尾。

验证完成后本条记录与后续清理动作一并由主检出的收尾流程处理，本文件无技术内容。
