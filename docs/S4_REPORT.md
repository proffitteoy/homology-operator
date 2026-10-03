# S4-09 冻结验收协议

本轮只验收 S4；S5/GUDHI、稳定性、应用和发行没有在本轮验收。
数学实现固定为 candidate `7fa812d5e76ca80ac16316cb212d133c0639bfd7`，
R0 固定为 `54ce78bccdcba619ffa2a4d76aeb450bfd24270e`。
独立 Python reference 保留，所有优化路线都显式选择。

pilot 清单 `s4_acceptance_manifest.json` 预声明 27 个配置、94 个 case/route 配对。
正式清单保留全部配置、路线、预算及查询；pilot 只检查执行、同输出和成本。
K4 查询量 0/1/8/64/1024、整数/有理/大整数/真实欧氏浮点、H0/H2/H3、
65/129 维与低/高 Betti、48/96 阶段过滤、四种限定 solver、
预算中断、浮点优化 Unavailable 和显式 entries0 失败全部保留。

正式计时与 RSS 各 10 个 fresh-process 区组，串行执行，固定 seed 6909 随机顺序。
普通配置每进程重建完整流水线 5 次；65/129 维显式输入和48/96阶段过滤预声明1次。
cold 时间单位是**整个进程区组**：包括启动、导入、完整 manifest 解码、所有重建、
输出 JSON 和退出；不是单次重建的独立冷启动。
RSS 使用另外一批同重复次数的 fresh process，在 Windows 读取 PeakWorkingSetSize。
RSS 缺失、失败和超时不能用零替代。每 worker 预算180秒。

区组内不复用已求解算子：每次重新转换输入、求解并独立验证，构造算子并重验，
读取拓扑、barcode与请求端点的transport证书、两批几何、tracking、共同查询历史，
序列化、恢复重验、恢复后重读几何，并流式核对所有链生成元的P/L。
第一批 workspace 准备和第二批复用均计入成本。没有物化紧凑 P 供 hash 使用。
完整来源和六身份保留在真实快照内；输出语义 hash 排除具体表示和随机 run 身份，
包含状态、objective/bounds/gap/认证、拓扑、全部请求几何/tracking/barcode、
transport证书和全部生成元P/L。不同表示仍保留各自身份，不能混用。

相同成功状态、认证、完整逻辑输出才做配对时间/RSS比较。
合法但ResourceExhausted的中间投影不算完成；Unavailable不算零结果或加速。
至少10个成功配对区组，配对median log ratio的10000次固定seed percentile
bootstrap 95%区间完全低于1，才认定该预声明组有收益。
任意组的配对median时间或RSS比大于1.20，阻止全局默认替换；全部组公开。
该规则继承S4-01准入，在本轮正式数据之前冻结。

消融路线：r0（旧源码/旧族/schema1）、reference（当前reference/相邻族/schema2）、
integrated（native限定solver或Factorized feasible与workspace）、
native_explicit、factorized_scalar、factorized_batch（临时workspace）、
hc_workspace和legacy_family（仅family.py为R0；schema1快照由当前恢复API读取）。
CyclicAction没有native几何支持，在integrated中预声明标记scalar读取；
不把这种后备记为native几何。

正式原始数据不会覆盖pilot或S4-01/04/05/06/07数据。
采样时冻结源码、helper/harness提交与LF hash、native源码和release二进制hash、
manifest LF hash、完整环境/命令、状态/质量、分段/完整成本与绝对RSS。
正式数据不用于挑选新的路线、删配置或修改门槛。

## Pilot 审计与冻结

pilot v1：188个独立进程，全部正常完成；成功配置完整语义hash一致。
Rank2的必需solver_options在pilot v1清单生成时漏传，导致三个路线一致Unavailable；
保留v1原始数据，按原fixture补齐dual图/terminals并针对该配置追加6个独立进程的pilot，
均Solved/ExactOptimal且完整输出一致。没有根据性能结果删负载或改变门槛。
冻结正式清单为 `benchmarks/s4_acceptance_frozen_manifest.json`，
其中保存两个pilot的LF hash。正式样本在冻结提交后产生。
