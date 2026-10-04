# 研究检查与测量入口

所有命令在仓库根目录运行。安装见[验证说明](../docs/VALIDATION.md)，
原始成果及逐文件清单见 [benchmarks](../benchmarks/README.md)。
脚本保留现有路径和参数，方便重放历史 Git 提交及继续维护测试。

## 审计与重建

| 脚本 | 用途 | 依赖与输出 |
| --- | --- | --- |
| [reproduce_research.py](reproduce_research.py) | 完整原件/数据 hash 与覆盖检查；`--reproduce` 运行 probe / s5-report / all | 校验/probe 仅标准库；S5 另需安装 reference、完整 Git 历史；只写新的 `--output-dir` |
| [report_s5.py](report_s5.py) | 从冻结原值重建统计/分段 CSV，审计原源码和环境身份 | 标准库、reference、完整 Git 历史；要求新的 `--output-dir`，无需 GUDHI/native |
| [check_s5_inputs.py](check_s5_inputs.py) | 两构造器的实际单形/链边界与 manifest 导出对拍 | `oracle` 组；`--output` 保存输入审计 |
| [check_s5_oracle.py](check_s5_oracle.py) | 显式 F2、stage barcode/Betti/rank 与实际次入口 | `oracle`，次入口需 `oracle-secondary`；`--output` 保存 oracle 审计 |
| [check_s5_correctness.py](check_s5_correctness.py) | reference/native/GUDHI、同 P 几何/认证/快照与反例保存 | native 和 `oracle` 组；`--output` 保存本次结果，失败证据按脚本参数保存 |
| [check_docs.ps1](check_docs.ps1) | UTF-8、本地文档文件链接与必需入口 | PowerShell 7；只读检查根目录、docs、research、benchmarks 与 scripts 的 Markdown |

```powershell
python scripts/reproduce_research.py
uv run --locked --no-sync python scripts/reproduce_research.py --reproduce all --output-dir .task-artifacts/research-reproduced
```

## 测量与协议

| 脚本 | 测量范围 | 对应实验 |
| --- | --- | --- |
| [compare_solvers.py](compare_solvers.py) | 小窗口 solver / 局部搜索、独立验证及完整成本 | Phase 3；[协议](../docs/BENCHMARKS.md) |
| [benchmark_reference.py](benchmark_reference.py) | R0 串行隔离计时/独立 RSS/profiling | S4-01；固定 R0，包含窗口、过滤与故障请求 |
| [benchmark_native.py](benchmark_native.py) | 可行 prototype、packed 与限定 solver 差分/有限成本 | S4-02/03/05；支持域和认证分开记录 |
| [benchmark_compact.py](benchmark_compact.py) | 同 P 的显式/Factorized/HC、独立 RSS | S4-04 |
| [benchmark_geometry.py](benchmark_geometry.py) | 标量/批量/workspace、准备与完整成本、显式后备 | S4-06 |
| [benchmark_filtration.py](benchmark_filtration.py) | legacy、相邻 barcode、全 rank 消融 | S4-07；[输出及证明](../docs/S4_FILTRATION.md) |
| [benchmark_acceptance.py](benchmark_acceptance.py) | 冻结配置、独立进程区组、计时/RSS、同输出门禁 | S4-09；[正式报告](../docs/S4_REPORT.md) |
| [prepare_s5_performance.py](prepare_s5_performance.py) | 预声明负载、输入、预算与 pilot 后冻结 | S5-05；不按速度选择正式配置 |
| [benchmark_s5.py](benchmark_s5.py) | cold/warm、独立绝对 RSS、失败保全和认证配对 | S5-04/05；[正式报告](../docs/S5_REPORT.md) |

参数以实际 `python scripts/<name>.py --help` 和各报告的已执行命令为准。
GUDHI 与次入口依赖只在测试/测量中安装，不进入生产结果路径。
这些脚本执行新测量时要求自己的源码/环境冻结；重放旧数据使用 `report_s5.py`。
新输出放入 `.task-artifacts/`；正式交付时以新文件名登记进 [registry.json](../benchmarks/registry.json)，
保留失败、不利数据、认证与来源，不覆盖已经冻结的成果。
