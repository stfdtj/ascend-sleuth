# E2E-AUTOCLOSE-001 —— 自动收尾端到端验证（构造）

> 本文件是端到端验证夹具，不是真实事故记录。验证完成后保留在季度目录，供回归复跑。

## 现象

构造样例：训练启动后 `all_to_all_single` 建链超时，`world_size >= 64` 时更易出现。

## 定位

构造样例中，`HCCL_BUFFSIZE` 低于 4194304 时复现；提高后恢复。用于验证 groom 合入后的
自动收尾流程。

## 修复

```bash
export HCCL_BUFFSIZE=4194304
```

重启训练生效。

## 来源

- 构造 trace：`traces/e2e-autoclose-20261110.yaml`
