# 实验代码与冻结成果

本目录保存已提交的原始样本、失败记录、清单、统计表和验证日志。
研究成果总览见[研究索引](../docs/research/README.md)，归档原型见 [research](../research/README.md)。
正式数据保留在现有路径，以便历史报告、Git 提交和测量源码继续对应。

## 完整清单与校验

[registry.json](registry.json) 为每份原始产物登记实验、用途、大小、SHA256 和换行政策，
并把实验关联到实际脚本和报告。它涵盖本目录的 JSON/CSV/log/gzip、五份测试输入及四份上传原件。
文本用 LF 规范化 hash；上传原件和 gzip 使用原始字节 hash，S5 gzip 另核对解压后的大小与 hash。
数据自己的来源、源码、环境、认证及输入身份仍以原记录为准，清单不重新赋予测量身份。

在仓库根目录运行（Python 3.10+，仅标准库）：

```powershell
python scripts/reproduce_research.py
```

检查只读；缺失、篡改、重复登记或未登记的数据使命令失败。Reference CI 执行同一检查。
SHA256 一致说明证据没有改变，不单独证明数学结论或重新测量性能。

## 复现已有成果

```powershell
uv sync --locked --python 3.12
uv run --locked --no-sync python scripts/reproduce_research.py --reproduce all --output-dir .task-artifacts/research-reproduced
```

该命令运行归档的 5,689 例独立端点原型，比较完整 JSON；随后从已有 S5 原值重建统计及分段 CSV，
比较冻结的表格 SHA256。也可使用 `--reproduce probe` 或 `--reproduce s5-report`。
输出目录必须尚不存在，且不能位于源码、文档或冻结证据目录内。
命令不追加性能样本、不改变原始结果；失败时保留新输出供排查。

S5 重建要求安装当前 reference 包并保留完整 Git 历史：使用 `git clone`，浅克隆需先
`git fetch --unshallow`。无需安装 native/GUDHI，因为重建读取已有原值。
CSV 字节对拍采用报告原有口径；跨平台数值末位差异的处理见 [S5 报告](../docs/S5_REPORT.md)。
重建通过不会把历史测量重标为当前 main 的新测量。

## 代码、输入、结果与报告

| 实验 | 保留入口 | 成果与范围 |
| --- | --- | --- |
| Phase 1/2 | [独立 oracle](../tests/oracle/reference.py)、[fixtures](../tests/fixtures/reference.json)、[联合过滤测试](../tests/test_family_joint.py) | 23 窗口、11 过滤族/变体；[来源](../docs/FIXTURES.md)及历史报告 |
| Phase 3 solver / no-go | [compare_solvers.py](../scripts/compare_solvers.py)、[solver fixture](../tests/fixtures/solver_reference.json) | `phase3_*.json`；[对照协议](../docs/BENCHMARKS.md)和 [Phase 3](../docs/PHASE3_REPORT.md) |
| S4 R0 | [benchmark_reference.py](../scripts/benchmark_reference.py) | `s4_r0_*` 的完整成本、独立 RSS、profiling；[协议](../docs/BENCHMARKS.md) |
| S4 native / packed | [benchmark_native.py](../scripts/benchmark_native.py) | `s4_native_*`、`s4_packed_*`；限定范围及复用消融，不能代替正式全后端验收 |
| S4 compact / geometry | [benchmark_compact.py](../scripts/benchmark_compact.py)、[benchmark_geometry.py](../scripts/benchmark_geometry.py) | `s4_compact_*`、`s4_geometry_*`；同 P、几何批查询与 workspace 消融 |
| S4 solver | [benchmark_native.py](../scripts/benchmark_native.py) | `s4_solver_pilot.json` 与验证日志；四种限定优化 solver 的有限成本 |
| S4 filtration | [benchmark_filtration.py](../scripts/benchmark_filtration.py) | `s4_filtration_*`；[相邻 transport 与历史基](../docs/S4_FILTRATION.md) |
| S4 integration | [集成测试](../tests/test_integration.py)、[旧快照](../tests/fixtures/legacy_results.json) | `s4_integration_verification.log`；安装、后备、取消与恢复，不是新性能数据 |
| S4 正式验收 | [benchmark_acceptance.py](../scripts/benchmark_acceptance.py) | `s4_acceptance_*`；[27 配置、1,880 进程](../docs/S4_REPORT.md)，保留中断、pilot 和退化 |
| S5 输入 / oracle / correctness | [check_s5_inputs.py](../scripts/check_s5_inputs.py)、[check_s5_oracle.py](../scripts/check_s5_oracle.py)、[check_s5_correctness.py](../scripts/check_s5_correctness.py) | 输入导出、F2 拓扑及 77 份三方正确性记录；[契约](../docs/S5_GUDHI.md) |
| S5 smoke / pilot / 正式采样 | [benchmark_s5.py](../scripts/benchmark_s5.py)、[prepare_s5_performance.py](../scripts/prepare_s5_performance.py) | `s5_harness_*`、`s5_performance_*`；smoke/pilot 不混入正式统计 |
| S5 统计重建 | [report_s5.py](../scripts/report_s5.py) | `s5_statistics.csv`、`s5_phases.csv`、`s5_report_audit.json`；[2,840 进程报告](../docs/S5_REPORT.md) |
| 独立端点原型 | [quiver_barcode_probe.py](../research/s4-s5/quiver_barcode_probe.py) | 5,689 有限例、零端点差异；不验证生产几何/序列化或一般性能 |

## 新实验与维护

安装/native/GUDHI 命令见[开发验证](../docs/VALIDATION.md)；各测量脚本的选项与用途见
[脚本索引](../scripts/README.md)。普通复跑结果放在忽略的 `.task-artifacts/`，正式交付再登记入清单。
不要通过更新 SHA256 来掩盖原证据变动；修正统计、补测和新环境分别新增产物并记录原因。

重采 S4/S5 必须遵守原 manifest 对源码、二进制、环境和协议的冻结要求，或声明新的完整协议。
当前脚本不能冒用旧测量身份。Cold、warm、绝对 RSS、solver 认证和输出集合分别比较。
失败、资源耗尽、Unavailable、NotApplicable 及合法零值保留各自含义；GUDHI 只提供拓扑对照。
