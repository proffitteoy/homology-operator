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

## S5-04 隔离进程采样器

[scripts/benchmark_s5.py](../scripts/benchmark_s5.py)串行执行四个独立进程域：cold/timing、warm/timing、cold/rss、warm/rss。
Cold外层时间覆盖进程启动/导入、整份清单解码、全部预声明重建、标准路径的验证/读取、报告JSON和退出；
每个block的重建次数明确记录，不能把block总成本当一份独立重建的冷启动。
Warm只在已有对象上读取请求；setup保留在worker阶段与外层warm进程总成本，warm batch单独计时。
第一批native workspace准备包含在该批成本，全部重复原值保留；不隐藏重建或转换。

Topology域经合法统一算子/族读取各请求维数完整barcode；GUDHI用同显式复形与固定主参数。
Joint域复用S4完整pipeline，另行完整读取全部请求维数topology的validated构造也明确计费。
它包含solver输出和算子的独立验证、两批几何/复用、tracking、序列化、恢复重验、恢复后几何与全P/L生成元。
互斥outer阶段与各次数nested阶段分开记录，不能双加；外层尚未分配开销显式保留。
GUDHI基线无需额外导入本库或构造链算子，公共manifest验证和实际SimplexTree核查仍计入成本。
Warm GUDHI读取已计算PH对象的各次数区间；两个次入口没有相同stored-object API，warm显式NotApplicable。

RSS是独立同负载worker的OS绝对历史峰值，Windows使用PeakWorkingSetSize；Linux/macOS声明ru_maxrss单位。
采集覆盖结果记录构造和一次JSON分配，最终输出/退出之后没有额外观测。缺值为null，不扣启动基线。
时间域无profiler、tracemalloc或trace；子进程数和native固定单线程，BLAS/OpenMP环境变量均1。
worker墙钟限180秒；RSS预声明2GiB仅作执行后绝对峰值预算评估，不冒充OS硬内存上限。
成功、库内ResourceExhausted/Unavailable/NotApplicable/Mismatch、process_timeout/oom/killed/error和取消分别保留。
SIGKILL不自行推断为OOM；OOM需要MemoryError证据。timeout不作为成功耗时。

固定seed调度且每条样本保存case/fixture hash、block/scope/mode、solver/认证/预算、source/build/environment和所有失败。
标准reference/native只在每个重复同完整输出、solver/认证时生成配对比值；Joint/GUDHI明示额外信息成本。
至少10个独立区组才给10000次固定seed配对log-median bootstrap 95%区间；少样本只列原值/median/IQR。
续跑必须同清单/source/build/environment；旧样本不得重选，原报告hash另存。原子检查点失败保全旧文件和完整临时数据。
`--cancel-file`在worker之间协作停止，活动worker可由Ctrl+C终止，已有完整样本保全。
正式模式拒绝未预提交的清单、改动的helper/source/build/environment或少于10区组。

[首轮smoke原样本](../benchmarks/s5_harness_smoke_v1.json)保留了资源状态JSON mapping序列化失败。
修复只规范化记录；[修正后smoke](../benchmarks/s5_harness_smoke.json)按同输入重新采样，失败仍以真实库状态保留。
五项采样边界回归覆盖真实子进程timeout/kill、记录OOM、缺RSS/输出差异禁比值、warm重复差异、
resource状态在timing/RSS均可序列化和检查点失败保全。这些smoke不是正式性能统计。

```powershell
uv run --locked --no-sync python scripts/benchmark_s5.py --manifest benchmarks/s5_harness_smoke_manifest.json --phase smoke --output .task-artifacts/s5-smoke-recheck.json
```

正式负载、规模网格、重复次数与pilot在S5-05冻结，不能用正式结果选路线。

## S5-05 冻结规模与正式协议

[预声明pilot](../benchmarks/s5_performance_pilot_manifest.json)和[完整pilot原值](../benchmarks/s5_performance_pilot.json)
包含20配置、71个case/route、284个独立进程，全部完成，成功结果无拓扑/同输出差异。
[正式清单](../benchmarks/s5_performance_frozen_manifest.json)沿用全部输入/路线/solver/预算，无性能筛选；
10区组×cold/warm×timing/rss共2840进程。cold每进程5次重建，预声明grid/long/VR/q1024为1次；warm5次。
查询量0/1/8/64/1024、整数/有理/浮点/大整数、ExactOptimal及明确失败配置分组。

规模覆盖10/18列双行网格（H1链37/69、末端β=1）、K4,4/K5,5（β=9/16）、16/32阶段长过滤，
以及10/18顶点显式欧氏VR（H1链20/54）。维数、nnz、消元fill-in、rank/β逐阶段保存在scale_metadata。
这是有限显式稠密边界实现的规模网格，不证明一般中型VR或稀疏复杂度。
R0/reference/全后端和q8的显式native、因子scalar、HC workspace消融均保留；VR真实次入口另列。
没有并行worker性能主张；本轮仅预声明单线程串行采样。

生产Python/Rust源码固定S4 `7fa812d5e76ca80ac16316cb212d133c0639bfd7`，R0固定`54ce78b`；
worker及外层计时函数AST与pilot保持相同，父记录改为每条append-only journal、每10条聚合检查点，
启动/取消/结束也写检查点。续跑同时加载journal中检查点后的完整样本，避免重复或丢失；
六项采样回归包含真实run_plan取消与过时检查点续跑。
正式运行前提交清单和helper，测量时拒绝身份变化；pilot与formal不混入同一统计。

```powershell
uv run --locked --no-sync python scripts/benchmark_s5.py --manifest benchmarks/s5_performance_frozen_manifest.json --phase formal --output .task-artifacts/s5-formal-recheck.json
```

正式结果、配对统计与全部失败在S5-05采样完成后提交，综合审计/隔离复现由S5-06交付。

### S5-05 正式原始证据

被测checkout `f4b0d58148c7b94b83dcb5ae5bfe79857deb2c73`，生产源码仍是冻结S4。
2026-10-03 UTC 13:12:19–14:13:07，2840个独立进程全部正常退出；
记录5360个Computed、240个ResourceExhausted、240个Unavailable和200个NotApplicable，
这些是worker内部重建记录数，不能与进程数混用。reference/拓扑配对差异均0；RSS预算超限0。

[完整原始JSON的gzip](../benchmarks/s5_performance_formal.json.gz)无损保留全部106757401字节、所有重复/失败及原summary；
[原summary与archive hash](../benchmarks/s5_performance_formal_summary.json)便于读取全部284组统计。
解压后SHA256为`f90e00a5f1f29155a6f949c8f2330e5cb48ce82c09fc9c7271f96474fc949f1e`。
原summary属于当时冻结harness；后续review修正的身份门禁和重新汇总另保存，不改写测量来源。

本次结果没有支持统一启用集成后端：grid18的cold集成/reference配对median比为1.329，
95%区间[1.247,1.378]；path32为1.303，[1.241,1.341]。
q1024的cold为1.047，[1.030,1.069]，warm为1.086，[1.055,1.102]，均保留退化。
q8的cold Joint/GUDHI PH额外信息成本比为7.882；两者输出不同，不称PH加速。
完整median、Q1/Q3端点和固定seed的10区组配对bootstrap均保存在原summary，pilot没有参与统计。
正式域只覆盖本工作站、预声明规模和单线程串行执行；综合成本/认证边界与独立复现由S5-06提供。
