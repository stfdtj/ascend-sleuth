```python
### scripts/analyzers/ibmc_analyzer/run.py
<<<<<<< SEARCH
def _is_npu_presence_issue(issue: dict) -> bool:
=======
def _valid_empty_npu_table(path: str) -> bool:
    """A complete header with no data rows is the supported zero-card signal."""
    try:
        with open(path, encoding="utf-8-sig") as stream:
            lines = (line.strip() for line in stream if line.strip())
            columns = [col.strip() for col in next(lines, "").split("|")]
            return (columns[:7] == ["Name", "Board", "Power", "WorkMode",
                                    "SingleEcc", "DoubleEcc", "Diversification"]
                    and not any(lines))
    except (OSError, UnicodeError):
        return False


def _is_npu_presence_issue(issue: dict) -> bool:
>>>>>>> REPLACE
```

```python
### scripts/analyzers/ibmc_analyzer/run.py
<<<<<<< SEARCH
        npu_source = _npu_source(machine)
=======
        npu_source = _npu_source(machine)
        invalid_npu = bool(npu_source and not machine.get("npu")
                           and not _valid_empty_npu_table(npu_source))
>>>>>>> REPLACE
```

```python
### scripts/analyzers/ibmc_analyzer/run.py
<<<<<<< SEARCH
            if npu_source is None and _is_npu_presence_issue(issue):
=======
            if ((npu_source is None and _is_npu_presence_issue(issue))
                    or (invalid_npu and "NPU 数量" in str(issue.get("detail", "")))):
>>>>>>> REPLACE
```

```python
### scripts/analyzers/ibmc_analyzer/run.py
<<<<<<< SEARCH
                        "reason": "npu-info-missing",
                        "detail": "未找到 AppDump/CpuMem/npu_info，在位数量未知，不据此判定丢卡",
=======
                        "reason": "npu-info-unreadable" if invalid_npu else "npu-info-missing",
                        "detail": "npu_info 无法确认数量" if invalid_npu else "未找到 npu_info",
>>>>>>> REPLACE
```

```python
### scripts/analyzers/ibmc_analyzer/run.py
<<<<<<< SEARCH
        if npu_source is None:
            missing.append(f"{label}：NPU 在位未知（未找到 npu_info），相关在位判定已从发现里移除")
=======
        if invalid_npu:
            missing.append(f"{label}：NPU 在位未知（npu_info 存在但无法确认数量）")
        elif npu_source is None:
            missing.append(f"{label}：NPU 在位未知（未找到 npu_info），相关在位判定已从发现里移除")
>>>>>>> REPLACE
```
