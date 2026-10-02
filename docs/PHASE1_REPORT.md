# Phase 1 单尺度 reference 联合验收（2026-10-02）

验收候选包含 PR #32–#40 的审查修复、联合测试、公共导出与记录边界；具体 PR/提交见 [Phase 1 汇总 issue](https://github.com/proffitteoy/homology-operator/issues/1)。源码内容身份如下，不依赖报告自身提交 hash；所有文件先按 UTF-8 解码并规范换行为 LF，再计算 SHA256。

| 生产文件 | SHA256 |
| --- | --- |
| `src/homology_operator/__init__.py` | `b29fc1dadbdd320d17a13713d44f017557739e8bb89846458c56d063e2288d7b` |
| `src/homology_operator/algebra.py` | `0a85de257bd25c6595d6bcfd1b08729713213c2dd187bf1181790d5285e604b5` |
| `src/homology_operator/chain.py` | `2b38886cf4df56504bd28ee383b7e61c29965a375298fff67b7a46e7a67c3517` |
| `src/homology_operator/operator.py` | `ed035183561e9546f3712a057c39c6ce8a36b487ffee739edef8506c9dba9a4d` |
| `src/homology_operator/result.py` | `575d1b2b81e99e0421604b5c1f1d20951969a816ce757bb5914643236277fc01` |
| `src/homology_operator/solver.py` | `73de16dff7c8248774cc54ef1ba7d5c4b0f97d1a66c72bbd2460cc347d7a1d0d` |
| `src/homology_operator/validation.py` | `9c91a941a98a51ced479a3ff6d8b53fd3695320ea03e25d68ee5fe7a130f8791` |

将上表的 `path:hash` 映射编码为 sorted/compact JSON 后，其 SHA256 为 `e54fe2f9f26b99b30e81826d05fdaff92e48ff51ce58697a30407fc82f9deb5e`。23 份 [fixture corpus](../tests/fixtures/reference.json) 的 LF 规范化文件 SHA256 为 `593fb2784a2b5ea25bc62d7ee3c0180fa3185fefc6b42cf87a7203f7b111d7e2`；各链输入和研究原文件的独立 hash 见 [迁移说明](FIXTURES.md)。

## 实际环境与命令

本地 Windows，CPython 3.10.11、uv 0.11.5、Ruff 0.11.13、PowerShell 7.6.5；运行时仅标准库。依赖由 `uv.lock` 锁定。以下命令在仓库根运行并通过：

```powershell
uv sync --locked --python 3.10
uv run --locked python -m unittest discover -s tests -v
uv run --locked python examples/single_scale.py
uv run --locked ruff check .
uv run --locked ruff format --check .
uv build --no-build-isolation
pwsh -NoProfile -File ./scripts/check_docs.ps1
git diff --check
```

另外在隔离 venv 中重新安装构建出的 wheel，使用 `python -I` 成功构造一维无边界算子并验证 `betti=1`、`stretch=1`。源码示例 [single_scale.py](../examples/single_scale.py) 实际运行，记录源码提交、六身份、原基/权重、solver、资源预算和独立证书；手工 H0 输入的 Betti 为 1，选定质量为 10、同类距离为 0、当前 stretch 为 10，solver 认证仍为 Feasible。

## 数学与状态证据

57 项 unittest 通过：包入口 2、F2 代数 6、ChainWindow 8、结果 14、solver 4、validator 5、operator 5、几何 4、stretch 5、联合验收 4。

- 所有至多 3×3 的 F2 矩阵核/像/rank/可解性与广义逆用独立向量穷举核验。
- 所有 `m,n,p≤2` 的合法链窗口与全部候选 P，以独立全向量检查对拍 validator 五项代数条件，包含非零同调上的非法零投影。
- 23 个固定来源窗口覆盖 H0–H3、单/多洞、非平凡边界、空链、空循环域、循环非空零同调、人工权、实际长度/面积/体积和基重排。
- [联合测试](../tests/test_joint.py) 不借用生产消元建立 oracle：全链对拍 action、循环与边界；通过列组合商类验证 Betti、核到商的双射及循环同调保持；独立坐标核对所有循环对的距离与共享/总支撑、质量恒等式及商类三角不等式。
- 当前 stretch 与独立非零循环枚举相符。有理/整数结果精确；浮点只作数值核对，无未经认证的全局上界。
- 查询及嵌套 objective 六身份、原基/权重、来源和预算 round-trip 保留；普通保留键字典与 Fraction 无歧义；无投影失败记录保留真实部分身份，不生成伪算子；非法 Ready、混用结果、伪最优证书、非循环类查询、0/缺失/空域/资源中断均有回归。
- 真实最短类质量只在测试 oracle 内计算。已证明存在 selected_mass 大于该类最短质量的小实例，生产可选最短查询仍为 Unavailable/NotComputed。

## 验收边界与合并门槛

本地通过不替代远端 CI；CI 在每张 PR 的确切 head 上分别运行 Python 3.10/3.12，结果以 GitHub checks 为准。每个 issue 有独立增量 PR，全部 Phase 1 PR 按用户授权合并进入 main 后，才推进 Phase 2。

只达到有限单尺度 correctness reference：没有 OperatorFamily、transport/rank/barcode 主结果、一般最小伸长 solver、高性能或稳定性结论。Fixture 的过滤切片和预期区间是 Phase 2 输入准备。资源时间在稠密步骤间检查，不保证单步抢占或进程 RSS；stretch 按循环维数指数枚举。开发快照未发布，许可证仍待选定。
