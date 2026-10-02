# Phase 2 有限过滤联合验收（2026-10-02）

Phase 1 已通过 PR #30–#41 合入 main `2a8c0f07b70d48e47c32c335fc3642319302a312`，该提交的 Python 3.10/3.12 CI 与 57 项本地测试通过。Phase 2 基于此提交实现；后续 PR 按 issue 审核，合并后才进入 Phase 3。

## 实现与边界

`OperatorFamily` 消费有限非空阶段序列、合法 ChainWindow 和已验证单尺度 P，验证三个次数的坐标包含与两侧链映射。权重选择 Inherited 或显式 Variable，单位/语义一致。重复尺度保留 OrderedStages，末端 Constant 延拓。失败阶段保留完整记录并使族为 Partial。

主路径由 `P_j J_ij|ker(L_i)` 给 kernel 坐标矩阵与目标原链作用，复核恒等、composition、目标核和同调保持；barcode 仅从 transport rank 差分恢复。半开阶段区间保存重数，None 末端表示常量延拓下存活，重复尺度的零尺度长度明确标注。未存储的阶段内部瞬时事件不属于输入可恢复的信息。

几何追踪使用同一 P 族，死亡为合法零链/零质量/空支撑。終点质量界只使用目标当前 stretch 和源选定质量；变权因子显式为 max(w_j/w_i)，不乘中间 stretch。有理/整数核验精确；浮点只报告数值观察，溢出为 Unavailable/NumericalFailure。stretch 受单尺度 ResourceLimits 限制。

`OperatorFamilyResult` 保留完整阶段及传输身份、认证/失败、rank/barcode/tracking 和来源。读取时复核内容身份并重算派生结果，拒绝篡改、混用及 bool 冒充整数 rank。`to_family` 从记录的 P 恢复作用，不重新运行 solver。

## 实际验证

本地 Windows、CPython 3.10.11、uv 0.11.5、Ruff 0.11.13、PowerShell 7.6.5，运行时仅标准库。79 项 unittest 通过：Phase 1 的 57 项及族输入 4、transport 3、barcode 3、tracking 3、序列化 4、独立族联合验收 5。

- 四个多阶段 H0–H3 过滤、五个单阶段边界、K4 存活前缀和基重排变体，共 11 个族/变体，覆盖全部 23 份冻结 fixture。
- 独立全局边界列约化恢复 barcode，循环像商空间枚举核对所有区间 rank；均不导入生产源码。区间表重建 rank 与原传输一致。
- 全源循环核对直达/多步传输、同一目标 P 的类/质量/支撑、共享/总支撑和终点界。单尺度数学验收仍完整运行。
- 相同 Betti 不同映射导致不同 rank/barcode；不同合法 P 保持拓扑而改变几何与族身份；失败与合法空结果保持区分。
- AST 检查生产不导入 tests/oracle、独立 PH reduction、Ripser 或 GUDHI。

实际通过入口：

```powershell
uv run --locked python -m unittest discover -s tests -v
uv run --locked python examples/single_scale.py
uv run --locked python examples/filtration.py
uv run --locked ruff check .
uv run --locked ruff format --check .
uv build --no-build-isolation
pwsh -NoProfile -File ./scripts/check_docs.ps1
git diff --check
```

另在隔离 venv 重装 wheel，以 `python -I` 构造 H0 合并族，核对 barcode、传输/几何和完整 JSON round-trip。[过滤示例](../examples/filtration.py) 输出 family_result 和带目标身份的 endpoint_mass_control；末端 Constant 的 H0 区间为 [0,1) 与 [0,∞)，后两阶段尺度重复为 1，合并后两坐标类相同且 selected_mass=10。

## 源码与 fixture 身份

源码文件 UTF-8/LF 规范化 SHA256 及 sorted/compact path:hash 映射的聚合 hash 在下表固定。报告内容不进入源码 hash，fixture 文件不修改。

| 生产文件 | SHA256 |
| --- | --- |
| `src/homology_operator/__init__.py` | `5ab49ce80cebb843985510c3c89cb072d71867b2e37541e42300a1158e2c8d2b` |
| `src/homology_operator/algebra.py` | `0a85de257bd25c6595d6bcfd1b08729713213c2dd187bf1181790d5285e604b5` |
| `src/homology_operator/chain.py` | `2b38886cf4df56504bd28ee383b7e61c29965a375298fff67b7a46e7a67c3517` |
| `src/homology_operator/family.py` | `b7344801b54fc810528a7b7a1e2e455a621587de0890b280177b94715a86c554` |
| `src/homology_operator/operator.py` | `ed035183561e9546f3712a057c39c6ce8a36b487ffee739edef8506c9dba9a4d` |
| `src/homology_operator/result.py` | `575d1b2b81e99e0421604b5c1f1d20951969a816ce757bb5914643236277fc01` |
| `src/homology_operator/solver.py` | `73de16dff7c8248774cc54ef1ba7d5c4b0f97d1a66c72bbd2460cc347d7a1d0d` |
| `src/homology_operator/validation.py` | `9c91a941a98a51ced479a3ff6d8b53fd3695320ea03e25d68ee5fe7a130f8791` |

聚合 SHA256：`bfdda2f060c646565b6a91cbe63b7d0b1f0bd0e2c86def8f87b382b31e22e1a8`。23 份 fixture 的 LF 文件 SHA256 为 `593fb2784a2b5ea25bc62d7ee3c0180fa3185fefc6b42cf87a7203f7b111d7e2`；理论固定于 [指定研究提交](https://github.com/proffitteoy/homology-operator-lab/tree/6143729669902ee875b211b58085e954c76cdf88)。迁移来源见 [FIXTURES](FIXTURES.md)。

## 剩余限制

仅支持有限单参数、带基坐标包含 reference。无一般链映射、matrix-free、高性能、全局最小伸长、最优 solver、采样稳定性或发行保证。全区间 rank 及快照读取需要稠密计算，当前无族级抢占预算；单尺度 stretch 仍指数枚举，预算在步骤间检查。远端 CI 按每张 PR 的实际 head 核对，本地通过不代替 CI；这批 Phase 2 PR 待用户合并。
