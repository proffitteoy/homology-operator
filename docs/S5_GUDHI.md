# S5：显式同输入 GUDHI 验收

## S5-01 输入冻结与双构造器

[issue #70](https://github.com/proffitteoy/homology-operator/issues/70) 的输入适配器位于
[tests/oracle/simplicial.py](../tests/oracle/simplicial.py)，不进入运行时包。
reference 的运行时依赖仍为空；GUDHI 仅在测试 oracle 和后续测量对照路径使用。
S5-01 只验收输入；下方 S5-02 提供 PH oracle。三方联合验收及性能由后续工作包交付。

[冻结 corpus](../tests/fixtures/s5_simplicial.json) 有六个明确构造的复形：空复形、孤点、
重复 scale 的环/填充、H2 球面/三维填充、受控 H3/四维填充、截断环存活。
来源是明确记录的人工单形出生列表，未迁移研究仓库数据。
每份 manifest 包含源 payload/hash、总 input hash、canonical 单形、整数 birth stage、
原 scale、顶点坐标、坐标顺序、正权/单位/算术、请求次数、截断维数/阈值和常量末端延拓。
corpus hash 覆盖完整 manifest；几何权与 topology 输入的身份分别保留。

整数 stage 是两端实际使用的 filtration，原 scale 保留在 manifest 中。
同 scale 不同 stage 不合并；同 stage 瞬时配对的 PH 规范化属于 S5-02。
stage 限于能被 double 精确表示的整数范围，顶点标识限于非负 int32。
支持 H0–Hq 的次数前缀，q≤3；输入最大维数为 q 或 q+1。
只提供 q 维单形时，q+1 维死亡不会被自动补出，末端存活仅指该截断的常量延拓。

校验先拒绝缺面、非单调面出生、非 canonical 单形、重复顶点/单形、非法尺度/权重、
hash 篡改和未声明的截断。不把零长度或零体积改成 epsilon。
ExactInteger、ExactRational 与 FloatingPoint 权重明确区分；重复坐标本身不修改权重。
一般 AD=0 链窗口如果没有显式单纯复形适配，`applicability()` 返回 NotApplicable，
不会生成另一份点云来代替原输入。

两个构造器各从同一 manifest 构造实际输入：链侧保留带序基、A/D 的显式形状与 F2 面边界；
GUDHI 侧插入明确单形，禁止调用 filtration repair。
审计从实际链基/矩阵列和 SimplexTree `get_filtration`/`get_boundaries` 回读，
核对所有 stage 的活动坐标、权重、算术、每个单形的首次出生、面边界与维数计数。
两端导出均须等于声明输入。GUDHI 插入导致的补面和 filtration 降低会被检出。
[双边完整导出](../benchmarks/s5_input_audit.json) 保存实际内容、构造 hash、环境及 corpus hash。

## 安装与复跑

oracle 依赖组锁定 GUDHI 3.11.0、NumPy 2.2.6，具体平台 wheel URL/hash 见
[uv.lock](../uv.lock)。它们不是生产依赖。Python 3.10/3.12，Windows x64 或 Linux x64：

```powershell
uv sync --locked --group oracle --python 3.12
$env:HOMOLOGY_GUDHI_REQUIRED = '1'
uv run --locked --group oracle python -m unittest discover -s tests -p 'test_s5*.py' -v
uv run --locked --group oracle python scripts/check_s5_inputs.py --output .task-artifacts/s5-input-recheck.json
```

输出路径必须不存在，防止覆盖冻结证据。导出不包含 PH 结果。
缺 GUDHI 时普通 reference suite 会明确跳过双构造器测试；设置上述环境变量则直接失败。
[S5 oracle CI](../.github/workflows/s5-oracle.yml) 在 Windows/Python 3.12 和
Linux/Python 3.10、3.12 安装锁定组并强制执行真实 GUDHI 测试。
CI 配置、本地通过和准确 PR head 的远端结果分别报告，不借用 S4 CI 认证新内容。

## S5-02 F2 PH 与区间规范化

[tests/oracle/gudhi_oracle.py](../tests/oracle/gudhi_oracle.py) 主入口直接使用同一显式 SimplexTree，
再次核对真实输入后显式调用 `persistence(homology_coeff_field=2, min_persistence=0, persistence_dim_max=True)`。
拒绝安装版本偏离3.11.0；[冻结结果](../benchmarks/s5_oracle_audit.json)记录实际wheel中的编译模块hash，
wheel来源/下载hash由uv.lock绑定，无本地GUDHI编译。

规范化只使用整数stage，丢弃同stage对角配对，保留跨stage但同原scale的条、None末端和multiplicity。
由条多重集计数Betti和所有i≤j区间rank，与实际算子/族逐项读取值对拍。
最高维度选项不补缺失的q+1单形：H2球面仅有三角面时存活，有共同四面体时才死亡。
不比较算法pairing、基或代表；几何、Γ和证书没有GUDHI真值。

次基线执行真实 `SimplexTree.collapse_edges(nb_iterations=1)` → `expansion(q+1)`，
以及 `gudhi.sklearn.rips_persistence.RipsPersistence(...).fit_transform([matrix])`。
只接受顶点stage0且与图的q+1维flag展开完全相同的输入；延迟填充或缺失高维单形返回NotApplicable。
RipsPersistence使用stage编码的完整edge dissimilarity矩阵、threshold=末stage、显式F2、num_collapses=0和n_jobs=1。
这里不把stage矩阵声称为欧氏度量；collapse改变链表示，只比较flag拓扑，不声明原链几何保持。
主基线的输入/参数与这些次入口分别记录。

`oracle-secondary` 组额外锁定scikit-learn1.7.2、SciPy1.15.3、joblib1.5.2和threadpoolctl3.6.0；
缺依赖时RipsPersistence显式Unavailable。主PH不需要这些可选包。完整实际入口复跑：

```powershell
uv sync --locked --group oracle --group oracle-secondary --python 3.12
uv run --locked --group oracle --group oracle-secondary python scripts/check_s5_oracle.py --require-secondary --output .task-artifacts/s5-oracle-recheck.json
```

本地12项S5测试通过；六个主实例的Betti/barcode/全区间rank与reference族一致，
实际flag次入口也一致。有限对拍不作为一般性证明、三方完整语义或性能验收。

## S5-03 三方有限 correctness corpus

[冻结77份manifest](../tests/fixtures/s5_correctness.json)含13份结构/权重变体和seed=20261003的64份随机闭合2复形，
随机顶点数3–5、四个stage、正单位权。结构实例包括断连/两个H1类、一个死亡一个末存活、同stage单形、
重复scale、坐标反序、整数/有理/浮点重权和真实二维坐标欧氏边长，以及原H0–H3实例。
来源/生成参数、每份input hash与corpus hash冻结，原六份输入没有改写。

[三方脚本](../scripts/check_s5_correctness.py)逐份审计实际输入、所有请求次数的Betti/barcode/全区间rank，
并检查transport composition。n≤10的窗口另外用原独立oracle枚举全部ambient链和循环验证四个投影条件。
Native↔reference复用S4已验收的完整联合pipeline：全部坐标生成元P/L（包括非循环）、几何批/复用、tracking、
合法性、objective/bounds/认证状态、序列化、恢复重验和恢复后几何。结构exact权输入另覆盖Exhaustive与Greedy；
四种限定solver、非法AD、零投影、身份混用和证书/快照篡改继续由整仓既有独立回归验收。
人工一般AD=0旧fixture保留原代数oracle与来源，GUDHI=NotApplicable，不替换输入。

[完整结果](../benchmarks/s5_correctness_audit.json)保留77份结果、双方hash/状态/六身份/后备/成本、源码逐文件hash和实际native二进制身份。
生产Python/Rust源码必须逐文件等于S4冻结7fa812d；harness的checkout提交和helper内容hash另列。
缺native显式记录Unavailable；`--require-native`禁止将仅两方通过当三方通过。
差异保存原manifest、双方结果、快照与类别，并在保持闭包的最大单形删除操作下缩减。
最小性声明仅为该删除域的不可再缩减，绝不声称全局最小；没有真实差异时不伪造反例。

```powershell
uv sync --locked --group oracle --group oracle-secondary --python 3.12
# 按INTERFACE安装匹配解释器的冻结S4 release native wheel，随后保留安装：
$env:HOMOLOGY_NATIVE_REQUIRED = '1'
$env:HOMOLOGY_GUDHI_REQUIRED = '1'
uv run --locked --no-sync python scripts/check_s5_correctness.py --require-native --output .task-artifacts/s5-correctness-recheck.json
uv run --locked --no-sync python -m unittest discover -s tests -v
```

Native CI安装oracle组，强制同时运行真实native与GUDHI；reference仍可独立安装。
本轮有限corpus通过不推出一般证明、规模稳定性或性能结论。
