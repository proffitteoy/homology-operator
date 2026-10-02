# Solver 对照与性能协议

本协议回答同一ProjectionProblem下各solver支持什么、保留什么认证、付出了哪些成本，供#24的一般搜索go/no-go使用。不把单次reference耗时当作性能排名，也不宣称PH加速。

下一轮正式性能协议与工作包见 [S4/S5 项目计划](S4_S5_PROJECT.md)。本文件及冻结记录保留历史口径；后续无 profiler 的重复计时、操作系统峰值 RSS、GUDHI 同输入基线与联合信息成本另行报告。

## S4-01：main reference R0

[测量入口](../scripts/benchmark_reference.py)与[冻结 manifest](../benchmarks/s4_r0_manifest.json)
将实际计算源码固定到已合并 main `54ce78bccdcba619ffa2a4d76aeb450bfd24270e`。
该 main 的 [Reference checks](https://github.com/proffitteoy/homology-operator/actions/runs/36998360788)
已通过；实现分支与测量 harness 的提交/hash另行记录，不用它们替换被测 main。
运行前逐文件比较实际 `src`、fixture、原输入构造器、pyproject 和 lock 与该 Git 提交，
worker 再核对实际导入路径；换行统一为 LF 后保存源码 SHA256。

manifest 保留原23份带来源/hash的窗口、11个既有过滤配置（各用可行 solver），
补充K4的三个认证 solver、T-B1 m=2/3/4紧凑 action、K4的0/1/8/64次查询，
以及浮点不支持、state=0/20中断请求，共46个配置。
每个输入保留完整链、基、权重/算术、shape、nnz、rank与Betti；查询循环、scale、
预算、solver和请求认证写入manifest。Joint-basic查询代表、质量、距离和三种支撑，
过滤另查询追踪；Topology配置为0次几何查询。Joint-certified使用原solver认证，
不额外运行stretch来升级未计算的objective。

冷成本由父进程计时整个全新worker的启动、导入、manifest读取、标准调用链、JSON输出和退出。
流水线的互斥分段为输入转换、solver、dispatch必需验证/其余开销、算子边界验证/其余开销、
拓扑、族输入审计、transport/barcode及composition验证、几何、序列化、恢复/恢复审计和digest。
dispatch与算子总计时只用于相减拆分，不重复加入总成本；快照中的重复验证计入序列化或恢复。
未执行的分段不生成数值，不能解释成合法零。manifest中预声明查询的准备不属于被测流水线，
冷成本仍包含请求文件读取；全部数据共用同一manifest读取路径。

所有计时worker关闭profiler/tracemalloc。RSS另开全新worker执行同一请求，
Windows使用`GetProcessMemoryInfo.PeakWorkingSetSize`，Linux使用`ru_maxrss×1024`，
macOS使用其字节值；无法可靠读取时保存null和原因。
这是含解释器、导入、manifest及RSS读取辅助代码的整个worker绝对峰值，
不是阶段内存差、Python分配峰值或矩阵条目预算。RSSworker的时间不进入计时样本。
两项代表性cProfile诊断另存记录；诊断耗时不作R0计时。

pilot预声明每配置1个独立进程；开发R0为3个进程区组×1次有效重复，固定seed随机化顺序，
另每配置1个RSSworker。这只是后续优化的有限开发基线，不提供尾分位、稳健排名或一般规模结论。
外部timeout、worker异常/退出码保留原始记录；库内Unavailable/ResourceExhausted另保留solver状态、
认证、bounds和未完成标志，不能混入成功负载的summary。
原始样本按同case输入/输出、solver、实际认证、停止状态、算术及预算分组；
跨独立worker核对语义输出hash。输出digest排除run UUID与时间元数据，
真实快照仍完整保留六身份，并按生产入口验证JSON往返。

pilot后、native采样前冻结准入：同输出负载的冷总成本或绝对RSS，
至少一组10个独立进程区组的配对median log ratio经10000次固定seed bootstrap得到的
95%区间完全低于1，才报告改善；全部组公开，median冷成本或RSS退化超过20%时
阻止默认替换，可保留明确限定域的可选后端。数学/认证/失败语义必须全部通过。
此规则不预设收益倍率，不拿正式或holdout数据选路线；S4-09新增规模负载仍需先冻结新manifest。

复跑（仓库根目录；保留已有产物，换新输出路径）：

```powershell
git archive 54ce78bccdcba619ffa2a4d76aeb450bfd24270e --format=zip -o .task-artifacts/r0-main.zip
Expand-Archive -LiteralPath .task-artifacts/r0-main.zip -DestinationPath .task-artifacts/r0-main -Force
uv run --locked python scripts/benchmark_reference.py --source-root .task-artifacts/r0-main --manifest benchmarks/s4_r0_manifest.json --phase pilot --output .task-artifacts/s4-r0/pilot.json
uv run --locked python scripts/benchmark_reference.py --source-root .task-artifacts/r0-main --manifest benchmarks/s4_r0_manifest.json --phase r0 --output .task-artifacts/s4-r0/replay.json
uv run --locked python scripts/benchmark_reference.py --source-root .task-artifacts/r0-main --manifest benchmarks/s4_r0_manifest.json --mode diagnostic --output .task-artifacts/s4-r0/profile.json
```

首次运行前按README执行`uv sync --locked --python 3.10`，并先建立`.task-artifacts`目录。
全新worker使用同一锁定Python，显式导入归档main的源码；不修改主包、依赖或历史Phase 3记录。
用`--create-manifest --source-revision <SHA>`可以生成新manifest，但不是本次冻结证据的复跑入口。

## Phase 3 solver 对照（历史协议）

运行：

```powershell
uv run --locked python scripts/compare_solvers.py --output benchmarks/phase3_reference.json
```

[程序](../scripts/compare_solvers.py)固定原23份带来源的链窗口，以Feasible和ExactOptimal两个请求分别运行；增加K4的CertifiedInterval与0/20状态预算、T-A4宏观割的一般/专用请求，以及T-B1的m=2/3/4结构化请求。来源公式、原始input hash、实际重建输入身份、完整窗口、请求配置、源码commit与LF归一化SHA256清单一起保存。每个相同问题都探测Feasible、Exhaustive、Greedy、Rank2、Structured及尚未实现的GeneralSearch；不支持的组合保留Unavailable记录。

`problem_id`包含完整链/基/权重身份、objective、算术、认证目标、预算、并列、结构、matrix-free与选项，排除backend名称。只有problem_id相同才是同问题；`comparison_group`进一步分开实际认证等级和停止状态。即使请求目标相同，Feasible、ExactOptimal和中断区间也不能混作快慢排名；结构请求不同同样不能直接排名。

每行保存实际projection/handle、六身份、solver报告的objective/bounds/gap/资源、原始证书及独立验证结果。额外`audit_current_objective`只是同一P的限额stretch读取，不能升级solver的原认证或填入它尚未计算的objective。失败、空域、0、缺失和中断分别保留；GeneralSearch尚未实现时明确记录Unavailable。

计时使用perf_counter。构造通过包装现有backend进行测量，但入口仍为生产solve_projection，能力检查、请求配置绑定和独立验证均保留。dispatch总成本包含这些步骤；`dispatch_overhead_including_validation_seconds`不是纯validator成本。程序另外测量一次独立revalidation以及算子构造/审计读取成本，完整成本为这些阶段之和，不隐去重复验证。

构造和独立revalidation分别在tracemalloc启用时计时并记录Python分配峰值；这是带测量开销的时间和Python分配代理，不是原生内存或进程RSS。不可用RSS记录null，没有运行的构造/后验证同样为null，不能当成零耗时。构造预算不覆盖入口校验与独立证书重放；wall/state/matrix-entry语义以solver契约为准。

首次冻结运行使用干净源码提交 `fc9219885b6a3f20d6740368c95ca2f7e63e3ee6`，环境为Windows 10 build 26100 / AMD64 / Python 3.10.11。完整记录见 [phase3_reference.json](../benchmarks/phase3_reference.json)，原始文件SHA256为 `9cce89cc0c14eeda7aff4acf7d7e168c5ecfae6361368941e10586ddab871ffa`；其中的LF源码清单与source_snapshot_id绑定实际运行源码，不以之后的提交或CI替换此身份。

54个请求配置探测6个backend，保存324行：88个Solved、23个FeasibleOnly、6个ResourceExhausted、207个Unavailable。实际认证分为84个ExactOptimal、4个CertifiedInterval、26个Feasible（包括3个中断但保留action的运行）；无action的认证缺失。所有114个保留action经独立后验证，测试还从冻结文件重新构造OperatorResult并核对配置身份和JSON往返。

| 保留观察 | 结果与含义 |
| --- | --- |
| K4 stage 4，同CertifiedInterval请求 | Exhaustive与Rank2都认证9/8；Greedy为区间[1,4/3]。不能按同请求将不同实际认证混作快慢排名 |
| K4 state=20 | 三个优化器均中断，保留Feasible action但尚无完整objective/bounds；审计readout不补成solver认证 |
| T-A4宏观割，一般链窗口 | Exhaustive/Rank2为7/6；Greedy为区间[1,13/8]，保留这项不利质量结果 |
| K4的两个ExactOptimal运行 | 本次完整测量成本约Exhaustive 21.0ms、Rank2 23.4ms；专用构造没有在该单次样本中减少完整成本 |
| T-B1 m=4 | Structured构造约2.3ms，额外独立验证约61.9ms，算子构造及穷举审计约1.67s，完整测量约1.75s；不能只报构造时间 |
| GeneralSearch | 54个请求全部Unavailable，保留未实现事实，不能用已有solver结果填充它 |

这些是单次带tracemalloc测量的有限记录，不提供稳健性能排序。它们说明一般搜索评估必须同时覆盖认证能力、质量与完整成本，而不能仅缩短候选构造；具体go/no-go留给#24。后续性能研究应另定重复次数、预热和隔离环境，不能从本表挑最好一次或混合认证等级作结论。

## 一般搜索准入实验（S3-06）：冻结协议

选择固定PROOF T11的截面参数化作为实验方向：从GreedyCertifiedSolver的P开始，每步只翻转一个边界基系数，遍历所有`rank(D)*beta`邻居并穷举循环Γ，选择严格改善最多的候选；改善并列按packed原坐标列决定，不移动到相等Γ的邻居。候选逐个独立验证。局部固定点没有全局最优证书，仅CycleBounds；通用下界0/1真实等界时才能ExactOptimal。BoundaryFlipExperiment只存在于对照脚本，未注册为公共GeneralSearchSolver。

预先固定输入为原23个来源/hash窗口（保留浮点拒绝）及一个人工A=0、n=5、两个边界、beta=3的窗口，不能运行后挑选有利实例。三种方法为GreedyCertifiedSolver、ExhaustiveExactSolver及该实验；全部请求Feasible、StableBasisOrder、原始算术、一般链窗口，预算分别state=20/2000、wall=10秒、matrix-entry=1000000。每配置单次完整成本测量，沿用上面配置身份、tracemalloc和额外独立重验；不同实际认证仍分组，不作稳健速度排名。

准入条件：实验至少改善一个完整贪心结果，在相同请求/预算下保留可复核bounds，且证明已有公共基线无法满足的支持域或质量需求。若只在现有exact支持域得到同值/局部区间，没有新适用域或可重放的全局证明，则本轮no-go；即使个别构造更快也不能据此接入一般后端。数值MIP/SAT不在本次选择内，未安装或运行，不比较虚构版本/成本。固定上游native/compressed搜索是精确有限枚举；planar_mincut仅适用于已识别对偶结构，其浮点pruning容差不迁移为本库认证。

执行入口：`uv run --locked python scripts/compare_solvers.py --experiment boundary-flips --output benchmarks/phase3_local_search.json`。协议与代码先提交，随后在干净提交运行并保留完整输出；原phase3_reference.json不改写。

正式运行源码为干净提交`e12d2b5f82d0daa4a0e5ac22ce87f4a19038b157`，环境同前；[完整144行记录](../benchmarks/phase3_local_search.json) SHA256=`946ba12bdb2a458e9b5236fa2f52362180c37f156307a9d48862fce297cbea03`。120个保留action全部独立验证并JSON往返；84个ExactOptimal、12个CertifiedInterval和24个仅Feasible，另保留6个浮点Unavailable及18个无action中断。人工beta=3窗口属于明确记录的人工正权，不冒充欧氏来源。

K4原基/重排两例从4/3改善到9/8，但实验仅认证[1,9/8]，Exhaustive在相同2000状态预算认证9/8最优；人工beta=3例没有改善贪心11/7，实验仍只认证[1,11/7]，Exhaustive在2000状态保留相同上界并中断。另独立放宽到默认100000状态作真值核验，Exhaustive以2090状态认证11/7；此核验不混入2000预算的性能记录。

本轮结论为**no-go：不接入公共GeneralSearchSolver**。实验确有两项质量改善，但都在已有exact支持域，不能证明新的支持域或比现有认证更强；beta=3例没有质量收益。完整成本保留原K4约18.9ms及重排20.5ms，穷举分别约22.2ms及18.2ms；认证等级不同且每配置只有一次，不用这些数作速度排名。state=20/2000中断保留seed和已完成改进，已测中途改善保存；不完整neighbor扫描不标局部完成。该证据只拒绝本轮边界翻转原型的公共准入，不否定其他参数化、branch-and-bound、MILP或SAT未来研究；重新准入需要新需求、预先冻结的比较和独立证明。
