# Phase 3 solver 对照协议

本协议回答同一ProjectionProblem下各solver支持什么、保留什么认证、付出了哪些成本，供#24的一般搜索go/no-go使用。不把单次reference耗时当作性能排名，也不宣称PH加速。

运行：

```powershell
uv run --locked python scripts/compare_solvers.py --output benchmarks/phase3_reference.json
```

[程序](../scripts/compare_solvers.py)固定原23份带来源的链窗口，以Feasible和ExactOptimal两个请求分别运行；增加K4的CertifiedInterval与0/20状态预算、T-A4宏观割的一般/专用请求，以及T-B1的m=2/3/4结构化请求。来源公式、原始input hash、实际重建输入身份、完整窗口、请求配置、源码commit与LF归一化SHA256清单一起保存。每个相同问题都探测Feasible、Exhaustive、Greedy、Rank2、Structured及尚未实现的GeneralSearch；不支持的组合保留Unavailable记录。

`problem_id`包含完整链/基/权重身份、objective、算术、认证目标、预算、并列、结构、matrix-free与选项，排除backend名称。只有problem_id相同才是同问题；`comparison_group`进一步分开实际认证等级和停止状态。即使请求目标相同，Feasible、ExactOptimal和中断区间也不能混作快慢排名；结构请求不同同样不能直接排名。

每行保存实际projection/handle、六身份、solver报告的objective/bounds/gap/资源、原始证书及独立验证结果。额外`audit_current_objective`只是同一P的限额stretch读取，不能升级solver的原认证或填入它尚未计算的objective。失败、空域、0、缺失和中断分别保留；GeneralSearch尚未实现时明确记录Unavailable。

计时使用perf_counter。构造通过包装现有backend进行测量，但入口仍为生产solve_projection，能力检查、请求配置绑定和独立验证均保留。dispatch总成本包含这些步骤；`dispatch_overhead_including_validation_seconds`不是纯validator成本。程序另外测量一次独立revalidation以及算子构造/审计读取成本，完整成本为这些阶段之和，不隐去重复验证。

构造和独立revalidation分别在tracemalloc启用时计时并记录Python分配峰值；这是带测量开销的时间和Python分配代理，不是原生内存或进程RSS。不可用RSS记录null，没有运行的构造/后验证同样为null，不能当成零耗时。构造预算不覆盖入口校验与独立证书重放；wall/state/matrix-entry语义以solver契约为准。

首次冻结运行在提交程序及测试后执行；结果和环境随后记录在本页。每种组合只运行一次，后续性能研究应另定重复次数、预热和隔离环境，不能从本表挑最好一次或混合认证等级作结论。
