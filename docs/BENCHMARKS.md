# Solver 对照与性能协议

本页保存已执行的 Phase 3 solver 对照、S4-01 R0、S4-02 原型、S4-03 packed 复用及 S4-04 紧凑 action 协议与冻结结果。Phase 3 的同问题/认证/预算对照用于 #24 一般搜索 go/no-go；后续实验按各节声明的完整成本口径解释。不把单次 reference 耗时当作性能排名，也不宣称 PH 加速。

正式全后端/GUDHI 验收见 [S4/S5 项目计划](S4_S5_PROJECT.md)，当前实现状态见 [文档索引](README.md)。本页及冻结数据保留各次实验的源码、输入、输出、测量范围与不利结果；S4-01 已有独立计时/RSS 基线，但原型/人工代数收益不替代 S4-09/S5 的冻结负载与正式统计。

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

### 首次冻结结果

实际被测源码为上述main，harness为干净提交`81056a652814c27f86f7501104bc1ba9aac8c3e2`；
Windows 10 build 26100 / AMD64 / Python 3.10.11 / 单线程。
[main与实现验证日志](../benchmarks/s4_r0_validation.json)保留main的129项数学测试、
两示例、Ruff/format、构建、隔离wheel导入和19份/90链接文档检查；
实现分支131项回归及其示例、静态、打包和22份/112链接检查另列，不混作main证据。
main的准确SHA/远端CI任务结果也在记录中，当前实现PR的CI须另查。

[pilot](../benchmarks/s4_r0_pilot.json)有46条计时及46条RSS；
[R0原始样本](../benchmarks/s4_r0_samples.json)有138条计时和46条RSS；
[独立profiling](../benchmarks/s4_r0_profile.json)保存K4 exact窗口和完整K4过滤的函数累计成本摘要。
全部worker执行成功，无外部timeout、异常或退出失败；46份RSS均有操作系统读数。
每配置的语义输出hash在计时/RSSworker间稳定。
三类库内失败配置仍保留Unavailable或ResourceExhausted和实际认证状态，
不进入成功负载的summary；“worker完成”不等于solver完成或返回最优解。
profiling的累计时间包含嵌套调用，不能相加或混入无profiler计时。

| 固定请求 | 冷进程median | 流水线median | 独立worker绝对峰值RSS |
| --- | --- | --- | --- |
| K4 stage 4，ExhaustiveExact / ExactOptimal，8次查询 | 138.85 ms | 16.62 ms | 21,725,184 B |
| K4完整过滤，Feasible，8次查询 | 434.63 ms | 299.93 ms | 24,637,440 B |
| T-B1 m=4，Structured / ExactOptimal，8次查询 | 195.97 ms | 72.06 ms | 21,766,144 B |

各行仅3个开发进程样本，RSS每配置1次；不作solver间排名或收益认证。
K4过滤的序列化/恢复分段median分别约126.07/113.22 ms，solver约6.08 ms；
m=4结构化构造约1.03 ms，dispatch与算子验证分别约16.84/17.26 ms，
序列化/恢复又分别约17.04/17.70 ms。
这些结果指向完整路径的实际瓶颈，不能只报构造时间。
各分段median不保证相加等于总成本median；原始单次分段严格互斥且和等于流水线总成本。
冷进程还包含导入与退出，未测Rust、GUDHI、一般规模效率或正式S5置信区间。

### 原始CRLF身份与Git LF文件校验

初次Windows采集时，Python默认文本写出把换行转换为CRLF。
原先此表误将这些原始字节SHA256标为UTF-8/LF；随后`.gitattributes`使Git文件为LF，
但不会改写已采集报告的身份。修正保留五份冻结JSON和三个报告的`manifest_sha256`原值：
它们绑定原始CRLF manifest `5b7461fa…`，不是Git LF manifest `0008d7ba…`。
不得将该历史字段直接与LF checkout的`read_bytes()`摘要比较，或无说明重写为新身份。

[可机读校验表](../benchmarks/s4_r0_checksums.json)显式区分`original_crlf_sha256`与`git_lf_sha256`。
LF摘要已逐文件核对Git blob；从LF字节仅将换行换回CRLF，便能重建原始采集字节身份。
采样内容、时间、输出hash、harness/source身份及旧manifest绑定均未重写。
未来`write_json`在Git处理前就显式写UTF-8/LF，原始文件摘要与LF checkout摘要相同。
新报告同时记录输入文件的原始`manifest_sha256`和换行归一化的`manifest_sha256_lf`，
即使读取历史CRLF输入也能核对Git LF身份；三个历史报告继续使用上述伴随校验表。
回归同时核对写出字节、五份历史CRLF/LF映射和三个旧manifest绑定；运行
`uv run --locked python -m unittest discover -s tests -p test_comparison.py -v`。
首次采集的131测试记录仍是历史证据，修正后新增两项校验使当前测试总数为133。

| 冻结文件 | Git UTF-8/LF文件SHA256 | 原始UTF-8/CRLF采集SHA256 |
| --- | --- | --- |
| s4_r0_manifest.json | 0008d7bae2f0f9f8f12667196c9b4013fd9ebaf299615e0e6f3f3e4fa2fe0496 | 5b7461fa18eab56e9c5457f8395755b6c82f77587738ef199d5965a561d53e31 |
| s4_r0_pilot.json | af95942149efd2034617ce34079675245460013040ccc9fcdcdbadf1f479019d | 6fc7698cc1e4c7c12370a5a8eb18d79475edde3f85ac6b67043887602765ba42 |
| s4_r0_samples.json | b66646ca59bc69d70b1a0fa568d001fff5012cb8561ec0addecf515e0246d5a4 | 614e6ec1edec3342fbb84785b7fb78f3fc8c96fd88b0ae2fca5aca3fa31c7a99 |
| s4_r0_validation.json | a8dbed283c30be34661197e7fa48fab38378afbd22c11d94105432d4ac6eda57 | 0e888c6d0da7f27537564c8516bfdb70001bf33e9b6bcf73fc0ac84cd1d1a66b |
| s4_r0_profile.json | 71dd0fb35160ef741c6fdadf9cc336956eaab86f8fb1559a3f37811ca4420172 | 1111f609bafae07ecf20b4928c649902e0c64ed763ebc97328a9ab85c2d7ec02 |

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

## S4-02：可选纵向原型的最小完整成本协议

在干净源码提交上运行 `uv run --locked --no-sync python scripts/benchmark_native.py --revision <准确HEAD> --output benchmarks/s4_native_prototype.json`。脚本拒绝源码与提交不同，保存Rust/Python/平台、源码LF hash、release扩展及wheel hash。预先固定K4 stage 4、ExactRational、StableBasisOrder、Feasible、原默认资源预算，查询量0/8/64，每配置5个独立冷worker，seed=62打乱顺序；30行原始采样全部保留。

两条路径构造完全相同P/G/U，比较同一Betti、核基、所有坐标生成元action、代表/质量/距离/支撑及恢复结果的语义hash。每个worker包含导入、链输入、solve与独立验证、算子验证、拓扑/查询准备、几何、快照/序列化、恢复验证、语义hash；外部process时间另含启动和收尾。转换、Rust计算、绑定/回传、decode以及Python几何后备是父阶段内的诊断，不能与父阶段重复相加。独立projection validator和恢复验证没有省略。

这是一个真实窗口的原型计时实验，不是R0全配置替代、统计准入或S4/S5性能验收；本项不测RSS，也不推断大尺寸或其他solver的收益。原型的单字宽、显式Matrix导出、Python验证与几何成本均公开；不利结果如实保存。后续任意尺寸prepared代数、factorized action、native几何和平台集成仍需独立工作包。

源码 `d6d6966fc4615078f7ac29798c568d4f0ccd5f38` 的 [30行冷worker采样](../benchmarks/s4_native_prototype.json)（LF SHA256 `bb417695081833ab2faabb7915605ef9fbeeda3a9b511a52eed54ca396714339`）保存3个查询量的相同语义hash。Windows x64/MSVC、Python3.10.11，release/safe Rust/单线程。worker中位数（含导入及完整恢复）：reference/native，q0为29.961/31.780ms，q8为32.899/31.915ms，q64为46.123/53.486ms；native/reference比值为1.061、0.970、1.160。外部进程中位数另为127.251/131.411、129.892/123.994、142.099/150.934ms。有限5次采样没有稳定完整成本收益，q64反而退化，不能据q8约3%的差异宣称性能改善。native的显式decode、QueryResult冻结/参数记录、Python循环检查和几何后备仍有成本，应由后续工作包分别处理。

[实际完整回归日志](../benchmarks/s4_native_verification.log) 记录140项全部通过（历史129项数学+4项测量+7项原型），另本地Ruff、Rust fmt/Clippy、两示例、文档、reference构建及隔离无扩展安装通过；这些不代替远端CI。采样与历史R0数据不覆盖，结果中的fixture/source/output/扩展二进制hash可逐项核验。

## S4-03：packed 分解复用完整成本消融

运行 `uv run --locked --no-sync python scripts/benchmark_native.py --prepared --revision <准确HEAD> --output benchmarks/s4_packed_ablation.json`。预先固定人工F2矩阵24×65/129、每行4个不同非零位（seed=6300+width）、8/64个相同生成规则RHS，3次独立冷worker，每个配置比较reference、native每次重新分解、native一次prepared，共36条，顺序seed=63。两条native路线是同一个内核的复用消融，非新增后端。

完整成本包含导入、Matrix/RHS准备、rank/核/像/solve/membership/action的转换/原生计算/decode，以及序列化恢复/hash；外部process时间单独记录。reference实际统计RREF调用，native统计实际handle构造，counter开销计入成本。prepared只分解一次，另两条为3+2q次；记录原矩阵、RREF和消元峰值非零位数及持有word量，fill-in不等同RSS。匹配完整原坐标输出hash，保存源码与release二进制hash，不将人工有限矩阵代数消融当作算子端到端或S4准入收益；本项不重新采集或覆盖R0/S4-02历史数据。

干净源码 `b75240e04e5d7b7b3e62bd7fa02adaac13ef02d6` 的 [36行完整采样](../benchmarks/s4_packed_ablation.json)（LF SHA256 `297f85dbfad1f540d5474f8d6c2a6c3a5711e41a7f0ca6fd026f9333a1a5d15d`）保存四个配置的同输出hash。Windows/MSVC、Python3.10.11、release/safe Rust/单线程；worker中位数含导入/输入/RHS/转换/输出恢复。列顺序为reference / native反复分解 / native一次prepared：

| 人工矩阵 / RHS数 | 完整worker中位数 ms | 实际分解数（反复 / prepared） |
| --- | --- | --- |
| 24×65 / 8 | 33.201 / 26.446 / 25.661 | 19 / 1 |
| 24×65 / 64 | 106.377 / 55.442 / 36.751 | 131 / 1 |
| 24×129 / 8 | 47.258 / 42.653 / 41.207 | 19 / 1 |
| 24×129 / 64 | 138.423 / 84.897 / 63.593 | 131 / 1 |

24×65的96个输入非零位在消元中峰值188、RREF170，持有120个u64；24×129的96个位峰值/RREF124，持有168个u64。它们只统计Rust系数/RREF/行变换payload，排除allocator、pivots、Python、RHS与结果分配，不能冒充峰值RSS。有限人工代数实验显示复用收益，不能推广为真实算子收益；S4-02真实窗口的退化记录继续保留。

[144项完整回归日志](../benchmarks/s4_packed_verification.log) 保存本地数学/测量/native全通过证据；release构建、Clippy/fmt、Ruff、文档另实际通过。远端native与reference CI按PR准确head核验。

## S4-04：同 P 的显式、因子与 HC 时间/RSS协议

运行 `uv run --locked --no-sync python scripts/benchmark_compact.py --revision <准确HEAD> --output benchmarks/s4_compact_action.json`。冻结后运行原K4 stage4（β/n=2/6）、H0 interval stage0（2/2），另两个人工坐标边界窗n=65、β=2/64；人工输入标明来源，不冒充迁移研究。三路线explicit reference / NativeFactorizedSolver Factorized / HC全部为Feasible、同权重、稳定并列、objective未计算及原默认资源上限。Factorized成功states与reference相同，HC额外2n个构造checkpoint，预算单位差异显式记录，完整认证等级不降低。

每配置3个冷timing worker，顺序seed64，共36条时间；之后每配置独立一个RSS worker，共12条，只报告真实绝对PeakWorkingSetSize/ru_maxrss与不可用原因，不与timing互相污染。成本包含输入、求解/独立验证、算子验证、拓扑、8个几何联合查询、快照序列化、恢复重验及流式完整生成元hash，外部process时间另报。绑定、Python后备与验证没有省略；validator分段诊断是父阶段子项，不能重复相加。四个输入的全部P/L生成元、核基、Betti、几何与恢复hash须跨三表示一致，projection身份按版本内容保持不同。

保存源码/输入/二进制hash、β/n、实际状态/认证/预算、序列化字节与factor条目，保留全部不利结果。HC在β接近n时H/C输出可大于dense P，Factorized包含A/D和逆非零行，消元有平方行变换workspace；这些成本与完整进程RSS一并报告。有限3次时间与1次RSS不足以推断S4准入或稳健速度排名，不据此自动选择默认表示，不改写R0或S4-02/03原始证据。

实际采样源码为干净提交 `c8a2f5bdf5bfa2ab387ac271b56e330205d45cfc`，
Windows x64 / CPython 3.10.11，release wheel与扩展hash保存在
[48条原始记录](../benchmarks/s4_compact_action.json)；该JSON的LF SHA256为
`75b566273ff1980162c51d93803b80f3c757ef1a3cb538ba904d18190153c69f`。
36个冷timing与12个独立RSS worker全部成功，四组完整语义hash跨三表示一致。
以下三元组依次为explicit / Factorized / HC；worker包含imports到恢复与生成元hash，
外部process另含进程启动/退出。每个RSS值仅为一个独立进程的绝对峰值。

| 输入 | 完整worker中位数 ms | 外部process中位数 ms | 绝对RSS MiB | action逻辑条目 |
| --- | --- | --- | --- | --- |
| K4 stage4，β/n=2/6 | 49.573 / 51.867 / 50.791 | 199.308 / 200.826 / 200.202 | 19.625 / 19.785 / 19.645 | 36 / 48 / 24 |
| H0 interval stage0，β/n=2/2 | 43.119 / 45.611 / 45.284 | 179.877 / 180.179 / 186.699 | 19.488 / 19.652 / 19.777 | 4 / 0 / 8 |
| 人工n65、β2 | 1043.010 / 1856.347 / 403.276 | 1187.412 / 2017.651 / 545.801 | 20.844 / 20.965 / 20.504 | 4225 / 8190 / 260 |
| 人工n65、β64 | 575.648 / 259.490 / 1484.519 | 715.676 / 406.335 / 1633.926 | 20.387 / 20.504 / 21.145 | 4225 / 130 / 8320 |

真实小窗口未见可靠收益；人工小β时HC较快而Factorized退化，人工高β时结果相反，
所有退化保留。Factorized在边界秩高时非零U行和D仍可大于dense P，HC在β接近n时H/C同样如此。
两种紧凑表示解决P/G/U/L的显式展开与身份/恢复语义，不保证任意输入都更省空间或更快。
这是共享开发主机上的有限样本，未控制主机其他负载，也未采尾分位或置信区间；
本聊天的性能worker串行，计时与RSS分开。该结果不用于默认路线选择或S4退出收益认定。

[152项完整数学回归与独立wheel恢复日志](../benchmarks/s4_compact_verification.log)
记录同一源码的实际验证：包含23个窗口、完整非循环生成元、至多3×3全增广逆、
多字边界、零投影/因子/版本/身份篡改、no-dense guard和11个族的全区间transport/barcode。
额外独立安装reference wheel，在没有native扩展时恢复Factorized/HC并实跑2项纯Python边界测试。
两示例、Ruff、Rustfmt/Clippy、release与reference打包、文档检查另通过；远端CI按PR准确head核验。

## 一般搜索准入实验（S3-06）：冻结协议

选择固定PROOF T11的截面参数化作为实验方向：从GreedyCertifiedSolver的P开始，每步只翻转一个边界基系数，遍历所有`rank(D)*beta`邻居并穷举循环Γ，选择严格改善最多的候选；改善并列按packed原坐标列决定，不移动到相等Γ的邻居。候选逐个独立验证。局部固定点没有全局最优证书，仅CycleBounds；通用下界0/1真实等界时才能ExactOptimal。BoundaryFlipExperiment只存在于对照脚本，未注册为公共GeneralSearchSolver。

预先固定输入为原23个来源/hash窗口（保留浮点拒绝）及一个人工A=0、n=5、两个边界、beta=3的窗口，不能运行后挑选有利实例。三种方法为GreedyCertifiedSolver、ExhaustiveExactSolver及该实验；全部请求Feasible、StableBasisOrder、原始算术、一般链窗口，预算分别state=20/2000、wall=10秒、matrix-entry=1000000。每配置单次完整成本测量，沿用上面配置身份、tracemalloc和额外独立重验；不同实际认证仍分组，不作稳健速度排名。

准入条件：实验至少改善一个完整贪心结果，在相同请求/预算下保留可复核bounds，且证明已有公共基线无法满足的支持域或质量需求。若只在现有exact支持域得到同值/局部区间，没有新适用域或可重放的全局证明，则本轮no-go；即使个别构造更快也不能据此接入一般后端。数值MIP/SAT不在本次选择内，未安装或运行，不比较虚构版本/成本。固定上游native/compressed搜索是精确有限枚举；planar_mincut仅适用于已识别对偶结构，其浮点pruning容差不迁移为本库认证。

执行入口：`uv run --locked python scripts/compare_solvers.py --experiment boundary-flips --output benchmarks/phase3_local_search.json`。协议与代码先提交，随后在干净提交运行并保留完整输出；原phase3_reference.json不改写。

正式运行源码为干净提交`e12d2b5f82d0daa4a0e5ac22ce87f4a19038b157`，环境同前；[完整144行记录](../benchmarks/phase3_local_search.json) SHA256=`946ba12bdb2a458e9b5236fa2f52362180c37f156307a9d48862fce297cbea03`。120个保留action全部独立验证并JSON往返；84个ExactOptimal、12个CertifiedInterval和24个仅Feasible，另保留6个浮点Unavailable及18个无action中断。人工beta=3窗口属于明确记录的人工正权，不冒充欧氏来源。

K4原基/重排两例从4/3改善到9/8，但实验仅认证[1,9/8]，Exhaustive在相同2000状态预算认证9/8最优；人工beta=3例没有改善贪心11/7，实验仍只认证[1,11/7]，Exhaustive在2000状态保留相同上界并中断。另独立放宽到默认100000状态作真值核验，Exhaustive以2090状态认证11/7；此核验不混入2000预算的性能记录。

本轮结论为**no-go：不接入公共GeneralSearchSolver**。实验确有两项质量改善，但都在已有exact支持域，不能证明新的支持域或比现有认证更强；beta=3例没有质量收益。完整成本保留原K4约18.9ms及重排20.5ms，穷举分别约22.2ms及18.2ms；认证等级不同且每配置只有一次，不用这些数作速度排名。state=20/2000中断保留seed和已完成改进，已测中途改善保存；不完整neighbor扫描不标局部完成。该证据只拒绝本轮边界翻转原型的公共准入，不否定其他参数化、branch-and-bound、MILP或SAT未来研究；重新准入需要新需求、预先冻结的比较和独立证明。
