# S5 显式复形与 GUDHI：有限成本审计

本报告交付S5-05/06（#74/#75），并入同一个[PR #92](https://github.com/proffitteoy/homology-operator/pull/92)。
冻结corpus的三方检查通过；正式测量保留了明显退化。集成后端68个可比统计组没有一个95%配对区间完全低于1，
本轮不支持统一启用集成后端。GUDHI只对照拓扑，Joint比值表示额外信息成本，不是PH加速。
按用户本轮要求，S5-06直接审计已有原值并构建报告，没有追加隔离采样或重复corpus验证；
下面明确区分已执行证据与提供的复现命令。

## 输入、数学范围与规模

[输入/oracle契约](S5_GUDHI.md)与[正式manifest](../benchmarks/s5_performance_frozen_manifest.json)固定20配置、71个case/route。
同一显式单形列表、带序基、q+1截断与stage过滤构造链窗口和SimplexTree；GUDHI固定F2、
min_persistence=0、persistence_dim_max=True。对角条丢弃，跨stage同scale条、末存活与重数保留。
Topology由同P的OperatorFamily及transport/rank读取，GUDHI不填充主结果。

| 预声明族 | 实际规模 | 已测边界 |
| --- | --- | --- |
| 小β双行网格 | 10/18列，20/36顶点，H1链37/69，3stage，末β1=1 | 显式稠密边界，未填最后一面 |
| 高β图 | K4,4/K5,5，H1链16/25，β1=9/16，2stage | 没有补成clique复形 |
| 长过滤 | path16/32，16/32stage，重复原尺度 | 单线程有限族，未测试无限过滤 |
| 欧氏VR | circle10/18顶点，H1链20/54，3stage | 只测试显式q+1截断，不代表一般中型点云规模 |
| 查询/算术/认证 | q=0/1/8/64/1024，整数/有理/浮点/2^130整数，Exhaustive认证 | selected_mass仍是当前P代表质量，非真实最短类质量 |

每个case的scale_metadata保存各次数/stage的维数、A/D nnz、rank/β与RREF nnz。
RREF nnz是当前消元结果的观测，不能当作一般最坏fill-in复杂度。
一般AD=0窗口没有单形适配器，GUDHI明确NotApplicable，不替换输入。
浮点几何没有精确最优认证；预声明Exact请求明确Unavailable。

## 源码、环境与正确性证据

- 生产Python/Rust逐文件固定S4 `7fa812d5e76ca80ac16316cb212d133c0639bfd7`；R0为`54ce78bccdcba619ffa2a4d76aeb450bfd24270e`。
- pilot协议`d16eb3d`，284独立进程；正式helper/清单提交`f4b0d58148c7b94b83dcb5ae5bfe79857deb2c73`，pilot没有参加正式统计。
- CPython3.12.13、Windows11 build26100、Intel64 Family6 Model170 Stepping4、22逻辑CPU；worker/native单线程，BLAS/OpenMP环境均1。
- native release：Rust1.98.1、PyO3 0.29.3、maturin1.15.0；GUDHI3.11.0/NumPy2.2.6为锁定PyPI wheel，次入口另锁sklearn/SciPy依赖。
- [原77份correctness](../benchmarks/s5_correctness_audit.json)覆盖13结构/权重变体与seed20261003的64随机复形，77 Passed/Compared。
- #90修复实现`aea7940`的8项回归通过；[新77份审计](../benchmarks/s5_correctness_review_audit.json)仍77 Passed/Compared，独立保存原证据。
- #91修复`265c623`的9项采样回归通过，包含真实Greedy/NativeFeasible认证差异；#92同步后10项采样回归通过（1.708秒）。

上述correctness检查完整action P/L（含非循环）、四投影条件/同调保持、同P几何/transport composition、
认证、查询历史与恢复；GUDHI仅核对barcode/Betti/区间rank，不给几何代表或Γ真值。
实际solver/config/认证/停止状态在review后的配对门禁中核对；Native前缀与已验收Feasible表示差异规范化，
其余配置/证据保留。原raw用修正门禁重新汇总后原summary不变，不能称为执行过新worker。

## 原始样本、失败与统计口径

2026-10-03 UTC13:12:19–14:13:07：10独立区组×cold/warm×timing/rss，共2840进程。
cold每进程5次完整重建，预声明grid/long/VR/q1024为1次；warm每进程5批已有对象读取。
调度固定seed7405，所有路线/失败保留，无性能筛选、无并行worker实验。

| 层级 | 实际结果 |
| --- | --- |
| 进程 | 2840 completed；2560成功性能样本，280按协议未完成/N/A样本 |
| worker内部重建记录 | 5360 Computed，240 ResourceExhausted，240 Unavailable，200 NotApplicable |
| 失败含义 | entries0预算耗尽；浮点Exact请求不支持；一般链GUDHI及VR次入口warm无同对象API |
| 进程timeout/OOM/killed/error | 正式测量均0；既有真实/故障注入回归另覆盖，不声称本轮实际OOM |
| 语义差异/绝对RSS | 同输出/拓扑配对差异0；成功RSS缺失0，2GiB事后预算超限0 |

[完整原值gzip](../benchmarks/s5_performance_formal.json.gz)解压为106757401字节。
完整原JSON SHA256：`f90e00a5f1f29155a6f949c8f2330e5cb48ce82c09fc9c7271f96474fc949f1e`。
gzip SHA256：`e0bc636f595657927889cc1399c667a07b9b07342030175a110a9bef2224cdf0`。
[原summary](../benchmarks/s5_performance_formal_summary.json)及[review后审计/hash](../benchmarks/s5_report_audit.json)
共同绑定manifest、历史helper、生产源码、实际二进制、依赖与环境；UTF-8源码hash统一LF。

[全部284组统计CSV](../benchmarks/s5_statistics.csv)给出median、Q1/Q3（IQR端点）、单位、重复次数、
全部失败计数及配对比值。至少10成功配对区组才报告固定seed的10000次log-median bootstrap 95%区间；
不报告尾分位。Mismatch无耗时也否决比值；timeout/耗尽/N/A不作为成功耗时。
Cold数值是整个新进程重建区组总成本，warm数值是该进程已有对象批次的median；两者不互当单次独立试验。

## 全部配置对照

以下均为候选/基线的配对median比值[95%区间]。reference栏只比较同输出/实际solver/认证，
GUDHI栏的Topology行为同拓扑成本比，Joint-basic行为额外信息成本比；Certified无GUDHI认证配对。
N/A覆盖缺路线、未完成或无可比结果，含义见manifest与原状态，不等同零。

| 冻结配置 | cold时间/reference | warm时间/reference | cold RSS/reference | cold/GUDHI |
| --- | --- | --- | --- | --- |
| small_beta/grid_10x2/Topology | 1.275 [1.165, 1.420] | 1.028 [0.893, 1.329] | 1.019 [1.016, 1.023] | 1.907 [1.856, 2.202] |
| small_beta/grid_18x2/Topology | 1.329 [1.247, 1.378] | 0.921 [0.807, 1.145] | 1.009 [1.004, 1.012] | 5.694 [5.308, 6.070] |
| high_beta/K4_4/Topology | 1.092 [1.003, 1.160] | 0.948 [0.896, 1.046] | 1.015 [1.010, 1.021] | 1.341 [1.107, 1.408] |
| high_beta/K5_5/Topology | 1.072 [0.992, 1.134] | 0.933 [0.672, 1.099] | 1.014 [1.012, 1.022] | 1.628 [1.573, 1.677] |
| long_filtration/path_16/Topology | 1.204 [1.099, 1.220] | 1.035 [0.893, 1.117] | 1.021 [1.016, 1.025] | 1.239 [1.096, 1.344] |
| long_filtration/path_32/Topology | 1.303 [1.241, 1.341] | 1.006 [0.834, 1.043] | 1.022 [1.019, 1.031] | 4.499 [4.257, 4.743] |
| vr/circle_10/Topology | 1.001 [0.967, 1.166] | 1.023 [0.992, 1.072] | 1.013 [1.007, 1.022] | 1.038 [0.971, 1.157] |
| vr/circle_18/Topology | 1.149 [1.111, 1.205] | 1.096 [0.977, 1.219] | 1.017 [1.006, 1.022] | 2.693 [2.365, 2.906] |
| query/q0 | 1.040 [0.915, 1.144] | 1.065 [0.914, 1.142] | 1.012 [1.011, 1.015] | 1.050 [0.937, 1.102] |
| query/q1 | 1.111 [1.021, 1.128] | 1.162 [1.103, 1.266] | 1.016 [1.011, 1.020] | 4.934 [4.619, 5.176] |
| query/q8 | 1.073 [0.993, 1.094] | 1.120 [1.073, 1.163] | 1.017 [1.012, 1.023] | 7.882 [6.918, 8.506] |
| query/q64 | 1.042 [1.018, 1.083] | 1.070 [1.055, 1.117] | 1.016 [1.014, 1.020] | 19.921 [19.014, 20.695] |
| query/q1024 | 1.047 [1.030, 1.069] | 1.086 [1.055, 1.102] | 1.013 [1.009, 1.015] | 47.837 [47.081, 49.282] |
| weight/ExactRational | 1.067 [0.991, 1.118] | 1.044 [0.950, 1.113] | 1.018 [1.013, 1.023] | 8.148 [7.534, 8.381] |
| weight/FloatingPoint | 1.126 [1.085, 1.158] | 1.078 [1.022, 1.174] | 1.014 [1.011, 1.018] | 7.933 [7.586, 8.318] |
| weight/bigint | 1.051 [1.017, 1.116] | 1.078 [1.030, 1.197] | 1.013 [1.012, 1.022] | 7.448 [7.143, 7.597] |
| certificate/exhaustive | 1.012 [0.992, 1.115] | 1.050 [1.030, 1.115] | 1.015 [1.010, 1.017] | N/A |
| failure/float_exact_unavailable | N/A | N/A | N/A | N/A |
| failure/entries0 | N/A | N/A | N/A | N/A |
| general_chain/gudhi_na | N/A | N/A | N/A | N/A |

集成cold的绝对median成本/reference median退化超过20%的配置为grid10（1.260）、grid18（1.351）、path32（1.268）。
上表的配对median log ratio与两组绝对median的比值是不同统计量，不能混写；例如path16配对比为1.204，
但绝对median比未超过1.2。68个集成组中51个区间下界大于1，17个其余组没有区间完全低于1。
q8的显式native、Factorized scalar、HC workspace各4个统计组也没有区间完全低于1；原值全部保留。
R0只作为声明的历史实现消融；其全部36组见CSV，不用它替代当前reference主基线。

## 完整成本、分段与联合信息增量

[完整分段CSV](../benchmarks/s5_phases.csv)区分process、互斥outer与nested/Hk；nested已包含在outer Joint阶段，不能再次加总。
以q8集成cold（每进程5次重建）为例，区组median1.650秒，outer Joint约1.432秒，
额外validated topology构造0.053秒，topology读取0.00294秒；初始化0.0199秒，未分配外层成本0.1545秒。
H1 nested的快照/必需验证约0.2065秒、恢复重验0.2321秒、tracking0.0989秒，均已计入Joint。
各阶段分别取median，阶段median之和不要求等于总成本median。

Joint-basic还读取当前P代表、selected_mass、类距离/三种支撑、tracking、两批几何、完整快照和恢复后P/L/几何；
Topology仅读统一算子/族的完整拓扑。下表按同ring输入比较不同信息请求成本；
warm增量是相对q0的描述性median差，输出不同，不是同功能加速或应用价值证据。

| q | cold重建次数 | reference cold区组秒 | integrated cold区组秒 | reference warm批秒 | integrated warm批秒 | warm增量秒/reference q0 |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | 5 | 0.209767 | 0.221961 | 0.000280 | 0.000298 | 0.000000 |
| 1 | 5 | 0.974437 | 1.079303 | 0.005940 | 0.006940 | 0.005659 |
| 8 | 5 | 1.569891 | 1.650385 | 0.040267 | 0.045169 | 0.039987 |
| 64 | 5 | 4.057948 | 4.277852 | 0.328982 | 0.351803 | 0.328701 |
| 1024 | 1 | 9.469616 | 9.932407 | 5.170436 | 5.592529 | 5.170156 |

q1024的cold为1次重建，其余query配置为5次，不能从cold区组原值直接推导单位查询斜率。
认证线单列Joint-certified/Exhaustive：完成才认证ExactOptimal；Feasible的objective未计算不能升级。
浮点Exact的Unavailable和预算耗尽保持独立状态。精确有理/大整数后备记录保留，不把F2精确性等同浮点objective精确。
RSS来自另一个同请求进程的Windows PeakWorkingSetSize绝对历史峰值（字节），包含解释器/导入/报告分配，
不扣启动基线；2GiB是事后观测预算，非OS硬限制。计时无profiler/tracemalloc，最终输出/退出后不另测RSS。

## 复现入口与本次执行边界

[report_s5.py](../scripts/report_s5.py)用标准库与本包重建统计/分段表，并核对原manifest、Git历史helper、
生产源码hash、环境、完整调度、每个fixture/repeat/output身份。无需GUDHI/native运行时，因为读取已有raw。
本次已从完整raw构建表格，审计记录含执行helper与发布格式化版本hash及AST一致性；
没有追加新的隔离corpus或性能样本。由用户取消的重复执行不伪记为S5-06通过的新测量。

在完整Git checkout（含测量历史提交）中运行：

```powershell
# 可在新的reference环境执行；已有native环境使用后面的--no-sync保留安装。
uv sync --locked --python 3.12
uv run --locked --no-sync python scripts/report_s5.py --output-dir .task-artifacts/s5-report-rebuilt
uv run --locked --no-sync python -c "import hashlib,json,pathlib; p=pathlib.Path; expected=json.loads(p('benchmarks/s5_report_audit.json').read_text('utf-8'))['table_sha256']; actual={n:hashlib.sha256((p('.task-artifacts/s5-report-rebuilt')/n).read_bytes()).hexdigest() for n in expected}; assert actual==expected; print('All frozen report tables match')"
pwsh -NoProfile -File scripts/check_docs.ps1
git diff --check
```

输出目录必须是新目录，原证据不会覆盖。同一记录/解释器统计重建要求CSV字节一致；不同平台libm若有末位差异，
只可单列数值重建（相对1e-12、绝对1e-15），不能替代上述hash对拍。这是数值口径，未定义新的计时重复验收。
原正式采样要求f4b0d58的helper/已提交清单/生产源码/构建/环境完全匹配；
review后当前harness拒绝冒用旧freeze，若要实际重采，应checkout原测量提交并提供原二进制/依赖环境，
或先声明新的完整pilot/环境/协议，保留本次所有原值，不能把新数据绑定旧hash。
真实native安装与三方命令见[API](INTERFACE.md#可选-rust-扩展)和[S5说明](S5_GUDHI.md#s5-03-三方有限-correctness-corpus)。

## 合并状态与退出条件

S5-01/02/03已合入main `6b193b1`；PR #91（head265c623）实际合入S5-03原分支，main尚未包含S5-04。
PR #92转向main，携带S5-04实现与S5-05/06交付；最终合并和精确main CI仍以GitHub实时状态为据。
本报告的有限正确性/性能及本地回归不是全部PR合并/main CI的替代证据；S5 Epic尚不据此宣布退出。
新的journal尾行截断review按用户本轮指示暂未处理；本次正式执行完整结束，没有续跑/截断样本，
这一恢复边界不改写已有正式结果，未来续跑仍需修复或确认原journal完整。
许可证/发行、其他机器/规模的采样稳定性、真实最短类质量与应用收益都没有由本实验获得验收。
