# S4 高性能阶段验收报告

本轮冻结性能门槛通过：1880个独立进程、成功联合输出一致，完整路线10个配置/指标组获得收益。
96阶段增长过滤完整时间median从57.42秒降至5.50秒，RSS从256.14MiB降至41.35MiB。
4组超过20%时间退化门槛，阻止全局默认替换，保留reference与显式可选后端。
本次生产源码未改动；新增内容为验收harness、测试、冻结数据和阶段说明。

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

## 采样中断审计

原冻结harness在第4个计时区组写检查点时遇到Windows `OSError errno22`，
已落盘297个独立进程（3个完整区组和第4组15个进程）的JSON完整且hash可读，
保存为 `benchmarks/s4_acceptance_interrupted.json`，不覆盖。
修复仅涉及父进程原子写、续跑和相应CLI选项；独立worker的测量流水线、恢复器和
外层冷计时函数AST、helpers、生产源码、manifest/阈值/预算、环境及release二进制
逐一核对相同。新报告记录两次harness提交、旧原始数据hash及保留样本数；
仅补跑未落盘的case/route/block/mode，不重选路线或计入缺失观察。
新增测试证明替换失败时旧检查点和完整临时数据均可保全。
RSS在流水线及结果记录构造后读取OS历史峰值；外层报告JSON输出和退出含在cold时间，
RSS采集点之后的报告输出/退出没有另外观测RSS。

## 正式采样结果

共1880个独立进程区组；每条路线/配置各10次计时及10次独立RSS。进程状态：`{'completed': 1880}`。
全部统计组见[188行汇总CSV](../benchmarks/s4_acceptance_summary.csv)；[原始报告](../benchmarks/s4_acceptance_formal.json)保留每个重复的状态、认证、质量、身份、输出hash、阶段成本、wire大小、配置/预算、后备及失败。未完成请求不进入成功成本比。
下表为完整integrated路线对R0。时间单位秒/整个进程区组；RSS单位MiB/独立进程绝对峰值。比值小于1有利；区间为冻结的配对bootstrap 95%区间；没有成功同输出配对时填NA。

| 配置 | 重建次数 | 实际状态/认证 | R0时间 | integrated时间 | 时间比[95%CI] | R0 RSS | integrated RSS | RSS比[95%CI] |
| --- | --- | --- | ---: | ---: | --- | ---: | ---: | --- |
| k4/q0 | 5 | FeasibleOnly/Feasible | 0.159 | 0.180 | 1.153 [1.105,1.243] | 25.865 | 26.680 | 1.030 [1.028,1.036] |
| k4/q1 | 5 | FeasibleOnly/Feasible | 0.159 | 0.187 | 1.172 [1.124,1.246] | 25.895 | 26.742 | 1.032 [1.031,1.038] |
| k4/q8 | 5 | FeasibleOnly/Feasible | 0.184 | 0.214 | 1.157 [1.126,1.180] | 26.070 | 26.869 | 1.031 [1.025,1.034] |
| k4/q64 | 5 | FeasibleOnly/Feasible | 0.367 | 0.382 | 1.058 [1.002,1.087] | 26.531 | 27.324 | 1.030 [1.028,1.033] |
| k4/q1024 | 5 | FeasibleOnly/Feasible | 3.550 | 3.375 | 0.948 [0.930,0.962] 准入 | 32.725 | 33.553 | 1.029 [1.016,1.032] |
| geometry/rational | 5 | FeasibleOnly/Feasible | 0.371 | 0.394 | 1.047 [1.035,1.086] | 26.561 | 27.373 | 1.029 [1.023,1.035] |
| geometry/bigint | 5 | FeasibleOnly/Feasible | 0.371 | 0.384 | 1.033 [1.010,1.084] | 26.625 | 27.303 | 1.029 [1.022,1.033] |
| geometry/euclidean_float | 5 | FeasibleOnly/Feasible | 0.310 | 0.348 | 1.105 [1.054,1.258] | 26.115 | 26.881 | 1.029 [1.027,1.032] |
| dimension/h0_interval_stage_1 | 5 | FeasibleOnly/Feasible | 0.165 | 0.174 | 1.080 [1.034,1.110] | 25.893 | 26.477 | 1.023 [1.019,1.026] |
| dimension/h2_euclidean_one_hole | 5 | FeasibleOnly/Feasible | 0.205 | 0.239 | 1.162 [1.067,1.183] | 26.230 | 26.955 | 1.029 [1.025,1.034] |
| dimension/h3_euclidean_one_hole | 5 | FeasibleOnly/Feasible | 0.235 | 0.284 | 1.222 [1.156,1.264] | 26.373 | 27.264 | 1.034 [1.032,1.037] |
| wide/n65/beta2/q8 | 1 | FeasibleOnly/Feasible | 0.848 | 1.656 | 1.951 [1.899,1.997] | 25.871 | 26.473 | 1.022 [1.015,1.027] |
| wide/n65/beta2/q64 | 1 | FeasibleOnly/Feasible | 1.335 | 1.848 | 1.398 [1.342,1.434] | 26.732 | 27.240 | 1.019 [1.015,1.023] |
| wide/n65/beta64/q8 | 1 | FeasibleOnly/Feasible | 0.549 | 0.355 | 0.651 [0.626,0.672] 准入 | 25.836 | 26.576 | 1.029 [1.025,1.033] |
| wide/n65/beta64/q64 | 1 | FeasibleOnly/Feasible | 1.017 | 0.544 | 0.537 [0.528,0.558] 准入 | 26.707 | 27.201 | 1.017 [1.012,1.022] |
| wide/n129/beta2/q64 | 1 | FeasibleOnly/Feasible | 6.356 | 10.739 | 1.686 [1.672,1.703] | 28.482 | 29.420 | 1.034 [1.029,1.038] |
| family/constant/s48 | 1 | FeasibleOnly/Feasible | 15.831 | 3.811 | 0.239 [0.237,0.245] 准入 | 88.910 | 35.490 | 0.399 [0.396,0.402] 准入 |
| family/growing/s48 | 1 | FeasibleOnly/Feasible | 14.983 | 3.076 | 0.206 [0.204,0.212] 准入 | 90.271 | 36.436 | 0.403 [0.400,0.404] 准入 |
| family/growing/s96 | 1 | FeasibleOnly/Feasible | 57.422 | 5.496 | 0.095 [0.094,0.096] 准入 | 256.141 | 41.350 | 0.161 [0.161,0.162] 准入 |
| certified/k4_exact | 5 | Solved/ExactOptimal | 0.236 | 0.246 | 1.040 [0.999,1.088] | 26.262 | 26.857 | 1.024 [1.020,1.026] |
| certified/k4_greedy | 5 | Solved/CertifiedInterval | 0.234 | 0.241 | 1.081 [1.015,1.121] | 26.158 | 26.850 | 1.026 [1.024,1.030] |
| certified/cut_rank2 | 5 | Solved/ExactOptimal | 0.344 | 0.345 | 0.976 [0.961,0.988] 准入 | 26.254 | 26.885 | 1.023 [1.021,1.028] |
| certified/cyclic_m4 | 5 | Solved/ExactOptimal | 0.542 | 0.558 | 1.033 [1.018,1.051] | 26.150 | 27.809 | 1.064 [1.060,1.066] |
| certified/k4_bigint | 5 | Solved/CertifiedInterval | 0.228 | 0.247 | 1.084 [1.042,1.128] | 26.225 | 26.824 | 1.021 [1.020,1.026] |
| certified/k4_interrupted | 5 | ResourceExhausted/Feasible | NA | NA | NA | NA | NA | NA |
| certified/floating_unavailable | 5 | Unavailable/None | NA | NA | NA | NA | NA | NA |
| failure/feasible_entries0 | 5 | ResourceExhausted/None | NA | NA | NA | NA | NA | NA |

完整路线有10个配置/指标组通过冻结收益门槛；4组超过20%退化门槛；成功组输出不一致数为0。有目标组收益才能通过本轮性能条件；退化阻止全局默认替换，保留独立reference和显式可选后端。

### 全部退化与失败

完整路线超过20%的配对median退化组：dimension/h3_euclidean_one_hole timing=1.222; wide/n65/beta2/q8 timing=1.951; wide/n65/beta2/q64 timing=1.398; wide/n129/beta2/q64 timing=1.686。其余消融路线的全部退化旗标也在CSV中公开。

| 非成功配置/路线 | 状态/认证 | 进程数 | 计时区组median/s | RSS median/MiB |
| --- | --- | ---: | ---: | ---: |
| wide/n65/beta64/q8 / native_explicit | {('Unavailable', None): 10} | 10 | 0.133 | 25.865 |
| certified/k4_interrupted / r0 | {('ResourceExhausted', 'Feasible'): 10} | 10 | 0.189 | 26.119 |
| certified/k4_interrupted / reference | {('ResourceExhausted', 'Feasible'): 10} | 10 | 0.200 | 26.396 |
| certified/k4_interrupted / integrated | {('ResourceExhausted', 'Feasible'): 10} | 10 | 0.202 | 26.617 |
| certified/floating_unavailable / r0 | {('Unavailable', None): 10} | 10 | 0.133 | 25.764 |
| certified/floating_unavailable / reference | {('Unavailable', None): 10} | 10 | 0.137 | 25.939 |
| certified/floating_unavailable / integrated | {('Unavailable', None): 10} | 10 | 0.140 | 25.883 |
| failure/feasible_entries0 / r0 | {('ResourceExhausted', None): 10} | 10 | 0.126 | 25.840 |
| failure/feasible_entries0 / reference | {('ResourceExhausted', None): 10} | 10 | 0.128 | 25.895 |
| failure/feasible_entries0 / integrated | {('ResourceExhausted', None): 10} | 10 | 0.129 | 26.109 |
预算中断的合法中间投影仍保留Feasible等级和实际objective状态，不能算ExactOptimal；entries0没有action；浮点认证不可用，真实浮点几何仍另有成功配置。native_explicit的65维拒绝是预声明支持域边界。

### 消融与阶段成本

下表公开预声明消融配置的所有路线；仍以相同P/完整输出/认证核对。绝对成本差用于观察贡献，不从本轮数据挑默认表示。每次snapshot/restore仍执行真实API。legacy_family保留旧family.py和schema1的创建/序列化，解码恢复使用当前API；因此它与全R0恢复成本有区别。

| 配置/路线 | 时间median/s | 对R0时间比[95%CI] | RSS/MiB | 对R0 RSS比[95%CI] | wire median/bytes |
| --- | ---: | --- | ---: | --- | ---: |
| k4/q0 / r0 | 0.159 | 1.000 [1.000,1.000] | 25.865 | 1.000 [1.000,1.000] | 6663.000 |
| k4/q0 / reference | 0.169 | 1.054 [1.022,1.160] | 26.088 | 1.008 [1.003,1.012] | 6663.000 |
| k4/q0 / integrated | 0.180 | 1.153 [1.105,1.243] | 26.680 | 1.030 [1.028,1.036] | 7086.000 |
| k4/q0 / native_explicit | 0.171 | 1.057 [1.016,1.155] | 26.455 | 1.025 [1.016,1.028] | 6906.000 |
| k4/q64 / r0 | 0.367 | 1.000 [1.000,1.000] | 26.531 | 1.000 [1.000,1.000] | 16193.000 |
| k4/q64 / reference | 0.377 | 1.033 [0.999,1.051] | 26.826 | 1.011 [1.008,1.014] | 16193.000 |
| k4/q64 / integrated | 0.382 | 1.058 [1.002,1.087] | 27.324 | 1.030 [1.028,1.033] | 16616.000 |
| k4/q64 / native_explicit | 0.369 | 1.006 [0.969,1.059] | 27.199 | 1.026 [1.023,1.028] | 16436.000 |
| k4/q64 / factorized_scalar | 0.497 | 1.369 [1.311,1.398] | 27.160 | 1.024 [1.023,1.025] | 16616.000 |
| k4/q64 / factorized_batch | 0.379 | 1.040 [1.018,1.050] | 27.273 | 1.028 [1.025,1.031] | 16616.000 |
| k4/q1024 / r0 | 3.550 | 1.000 [1.000,1.000] | 32.725 | 1.000 [1.000,1.000] | 151321.000 |
| k4/q1024 / reference | 3.486 | 0.984 [0.969,1.005] | 32.840 | 1.001 [0.993,1.012] | 151321.000 |
| k4/q1024 / integrated | 3.375 | 0.948 [0.930,0.962] 准入 | 33.553 | 1.029 [1.016,1.032] | 151744.000 |
| k4/q1024 / native_explicit | 3.330 | 0.949 [0.926,0.963] 准入 | 33.791 | 1.034 [1.025,1.040] | 151565.000 |
| wide/n65/beta2/q64 / r0 | 1.335 | 1.000 [1.000,1.000] | 26.732 | 1.000 [1.000,1.000] | 63091.000 |
| wide/n65/beta2/q64 / reference | 1.442 | 1.085 [1.062,1.122] | 26.859 | 1.005 [1.003,1.009] | 63091.000 |
| wide/n65/beta2/q64 / integrated | 1.848 | 1.398 [1.342,1.434] | 27.240 | 1.019 [1.015,1.023] | 71709.000 |
| wide/n65/beta2/q64 / hc_workspace | 0.629 | 0.478 [0.472,0.486] 准入 | 27.082 | 1.013 [1.010,1.016] | 55450.000 |
| wide/n65/beta2/q64 / factorized_scalar | 2.610 | 1.965 [1.921,2.012] | 27.078 | 1.013 [1.010,1.017] | 71709.000 |
| wide/n65/beta2/q64 / factorized_batch | 1.835 | 1.378 [1.350,1.416] | 27.170 | 1.018 [1.014,1.019] | 71709.000 |
| wide/n65/beta64/q8 / r0 | 0.549 | 1.000 [1.000,1.000] | 25.836 | 1.000 [1.000,1.000] | 32177.000 |
| wide/n65/beta64/q8 / reference | 0.626 | 1.138 [1.094,1.157] | 26.137 | 1.012 [1.008,1.015] | 32177.000 |
| wide/n65/beta64/q8 / integrated | 0.355 | 0.651 [0.626,0.672] 准入 | 26.576 | 1.029 [1.025,1.033] | 24372.000 |
| wide/n65/beta64/q8 / native_explicit | NA | NA | NA | NA | NA |
| wide/n65/beta64/q64 / r0 | 1.017 | 1.000 [1.000,1.000] | 26.707 | 1.000 [1.000,1.000] | 66728.000 |
| wide/n65/beta64/q64 / reference | 1.097 | 1.094 [1.065,1.127] | 26.941 | 1.008 [1.004,1.011] | 66728.000 |
| wide/n65/beta64/q64 / integrated | 0.544 | 0.537 [0.528,0.558] 准入 | 27.201 | 1.017 [1.012,1.022] | 58923.000 |
| wide/n65/beta64/q64 / hc_workspace | 1.578 | 1.559 [1.539,1.584] | 27.453 | 1.029 [1.025,1.030] | 75334.000 |
| family/constant/s48 / r0 | 15.831 | 1.000 [1.000,1.000] | 88.910 | 1.000 [1.000,1.000] | 5622812.000 |
| family/constant/s48 / reference | 3.114 | 0.195 [0.191,0.198] 准入 | 34.932 | 0.393 [0.390,0.396] 准入 | 664789.000 |
| family/constant/s48 / integrated | 3.811 | 0.239 [0.237,0.245] 准入 | 35.490 | 0.399 [0.396,0.402] 准入 | 684189.000 |
| family/constant/s48 / legacy_family | 15.375 | 0.964 [0.955,0.971] 准入 | 89.689 | 1.009 [1.001,1.020] | 5622812.000 |
| family/growing/s48 / r0 | 14.983 | 1.000 [1.000,1.000] | 90.271 | 1.000 [1.000,1.000] | 5574543.500 |
| family/growing/s48 / reference | 2.804 | 0.187 [0.186,0.190] 准入 | 35.799 | 0.396 [0.394,0.397] 准入 | 661095.000 |
| family/growing/s48 / integrated | 3.076 | 0.206 [0.204,0.212] 准入 | 36.436 | 0.403 [0.400,0.404] 准入 | 675873.000 |
| family/growing/s48 / legacy_family | 14.446 | 0.962 [0.957,0.968] 准入 | 90.141 | 0.995 [0.990,1.004] | 5574543.000 |
| family/growing/s96 / r0 | 57.422 | 1.000 [1.000,1.000] | 256.141 | 1.000 [1.000,1.000] | 21234424.000 |
| family/growing/s96 / reference | 4.793 | 0.083 [0.083,0.084] 准入 | 40.586 | 0.158 [0.158,0.161] 准入 | 964380.500 |
| family/growing/s96 / integrated | 5.496 | 0.095 [0.094,0.096] 准入 | 41.350 | 0.161 [0.161,0.162] 准入 | 993942.500 |
| family/growing/s96 / legacy_family | 55.107 | 0.958 [0.950,0.962] 准入 | 252.588 | 0.986 [0.985,0.986] 准入 | 21234425.000 |
完整流水线阶段耗时保存在原始报告，每个重建的相邻perf_counter边界互不重叠。内层阶段与外层cold区组不能相加；第一批包括workspace准备，第二批记录复用，恢复后另外重验/重读。流式P/L审计不物化完整紧凑矩阵，其成本也计入流水线。

### 冻结身份与环境

实际环境：`Windows-11-10.0.26100-SP0`，`3.12.13 (main, Apr  7 2026, 20:53:22) [MSC v.1944 64 bit (AMD64)]`，processor=`Intel64 Family 6 Model 170 Stepping 4, GenuineIntel`。当前结论只对应此Windows环境和有限负载；远端Linux/WindowsCI验证正确性/安装，不能充作异平台性能数据。
原harness为 `e2882369d10ca2e8ad72b186cb8abe530b85247f`，父进程续跑harness为 `9f3537f21a17800377d711ca8717439bcc48f6d5`；297个已保存样本复用，缺失观察不进入统计。当前main或报告提交没有被回写为测量源码。
源码/fixture/native文件LF hash、两个harness、release wheel/extension字节hash、manifest/pilot/原始报告/CSV的LF hash统一保存在[校验账本](../benchmarks/s4_acceptance_checksums.json)。

| 工件 | LF SHA256 |
| --- | --- |
| s4_acceptance_manifest.json | `8fb3194b7b5c7a49e1abde9427a5d6aa199ed307093238e0f90fd55f10819b44` |
| s4_acceptance_frozen_manifest.json | `0fd552569f3658ef9471a22d9653ea3c1d9d19b148a92276450d15de2ba5a043` |
| s4_acceptance_pilot_v1.json | `255bb67849c08fa42080b40dd4695f2cf8c02059b9e8eaae7f3e8b3923bea777` |
| s4_acceptance_pilot_rank2.json | `f8fb221fd6a7d8cb3ebda7f3c736f6ba6d4829ff48c341b940f3c46bd9be3a1b` |
| s4_acceptance_interrupted.json | `d0dcb0ceb3f698053e5111bc5056b0ff26f676f1be1c23bbe5c1cd0876498ebc` |
| s4_acceptance_formal.json | `ce5eff361f1b16d93f5468244245e15c0ff23fdd1f69aa806560e9cabc82bedb` |
| s4_acceptance_summary.csv | `e8d837384924ff19e7d6264ee47007210344c343d972a5d93b4bf58379bd0df2` |

## 认证质量与实际支持域

一般规模线为Feasible/NotComputed objective；不将合法投影解释为最优投影。
认证线的实际精确质量如下，R0/reference/integrated状态、认证与数值均一致。

| 配置 | objective | bounds | absolute gap |
| --- | --- | --- | --- |
| k4_exact | 9/8，精确 | [9/8,9/8] | 0 |
| k4_greedy | 4/3，精确 | [1,4/3] | 1/3 |
| cut_rank2 | 7/6，精确 | [7/6,7/6] | 0 |
| cyclic_m4 | 4，精确 | [4,4] | 0 |
| k4_bigint | 精确超大整数比，原始报告保留全部分子/分母 | [1,objective] | objective-1 |
| k4_interrupted | ResourceExhausted，无value | 未得bounds | 未得gap |
| floating_unavailable | NotComputed，无value | 未计算 | 未计算 |

Rank2的2.4%配对时间收益达到本冻结门槛，但绝对median约0.345秒且没有RSS改善，
两组绝对时间median分别为R0约0.344秒、integrated约0.345秒，保留这一略高结果；
配对median比不是两组median的商。本轮通过的过滤目标不依赖Rank2的小幅配对收益。
不推论所有认证solver提速。Structured的CyclicAction仍采用scalar几何。
一般规模的收益集中于大查询量、65维高Betti及共享过滤；
65/129维低Betti的Factorized路线较慢，HC/Factorized消融及wire大小完整公开。
本轮规模上界是129维单窗口、96阶段人工过滤；不推论更大/稠密/真实应用规模。

## S4 工作包来源与整合

| 工作包/整合 | 原PR head | 合并提交 |
| --- | --- | --- |
| [PR #77](https://github.com/proffitteoy/homology-operator/pull/77) | `ad38f0f2bfbd7a145fab577e6c35a339d3dfbb8a` | `846132d5eafb14dc9f83bd8f6bcb367a80cc48d9` |
| [PR #78](https://github.com/proffitteoy/homology-operator/pull/78) | `97a37376aa4a5cbc6e225e1077d8d859aa8949c8` | `9f933432a6be933c96698d707bd3da3efa404644` |
| [PR #79](https://github.com/proffitteoy/homology-operator/pull/79) | `88f69661859fe7475705fb76589cf30674b63746` | `d9bdf3bfe7a3fb365929d99d90cb85ca7c367f23` |
| [PR #80](https://github.com/proffitteoy/homology-operator/pull/80) | `6c40b93221ff4d9b90f89d069a2be6009100791b` | `520ecc95478d0b8123dfa17d5a11198eb7a5f734` |
| [PR #81](https://github.com/proffitteoy/homology-operator/pull/81) | `02e56a7c6adec256eda9b633a8198dc4dace8b7f` | `0b21461c0c5d03a0e211b4397c6bfd3055000e7b` |
| [PR #82](https://github.com/proffitteoy/homology-operator/pull/82) | `1e38dacfc9032b9328aa723fd35a0263ff8b932b` | `f0c15265b000941d1caa20030593eb84f3be969a` |
| [PR #83](https://github.com/proffitteoy/homology-operator/pull/83) | `4aacc008b6c44dfecc292a92361c7327952d2ff4` | `10e643f8efbdeec71b5c47a70f3b85ad2f19429c` |
| [PR #84](https://github.com/proffitteoy/homology-operator/pull/84) | `86a651c2ac8fec8e7b06ae958b60fb477d3b2c0a` | `63138fcb8da53d66fdc815ebb8af816392728ab6` |
| [PR #85](https://github.com/proffitteoy/homology-operator/pull/85) | `3bc4d5007502473ee3c6b8068bf7b6b839f51084` | `e920de0a2a9ac92e4f4c46bfe28e39a8212f5769` |
| [PR #86](https://github.com/proffitteoy/homology-operator/pull/86) | `a704f2760baf3fc3d365446df93a6e552066a3ad` | `7fa812d5e76ca80ac16316cb212d133c0639bfd7` |

PR #81最初合入S4开发分支，正式main整合由PR #85完成；不能将原分支成绩当作当时main成绩。
各历史性能源码、fixture、证据与不利结果继续保存在BENCHMARKS及原始工件，
本轮没有回写旧结果。S4-01–08的生产能力统一在本轮candidate `7fa812d`进行测量。
## 合并与 CI 证据

S4-01–08均已合并，GitHub #61–68均closed；S4-09 #69和S4 Epic #59仍等待本次最终交付。
前置 S4-08 [PR #86](https://github.com/proffitteoy/homology-operator/pull/86)
head `a704f2760baf3fc3d365446df93a6e552066a3ad` 已于2026-10-03T09:07:37Z合并，
main为 `7fa812d5e76ca80ac16316cb212d133c0639bfd7`。
该精确 main 的 [Reference checks](https://github.com/proffitteoy/homology-operator/actions/runs/37111993987)
与 [Native prototype checks](https://github.com/proffitteoy/homology-operator/actions/runs/37111993984)
均success；Native包括Windows/Python3.10与Linux/Python3.12。
这只证明被测生产源码的前置CI，不自动证明本次新增harness/报告最终head的CI或S4-09已合并。
本次最终PR与main的精确SHA/CI需在真正完成后追加，不能用关闭issue代替。

## 安装与复跑

原协议冻结提交：`e288236`；原子检查点/续跑harness：`9f3537f21a17800377d711ca8717439bcc48f6d5`。
后者的生产Python/Rust源码与被测candidate
`7fa812d5e76ca80ac16316cb212d133c0639bfd7`完全一致；正式原始报告绑定完整SHA及逐文件hash。
fixture/query/预算/重复次数固定在[正式清单](../benchmarks/s4_acceptance_frozen_manifest.json)。
不重新生成或改写清单，不用当前main冒充测量源码；后续报告文档提交不代表重新测量。

Windows PowerShell，Python3.12、uv0.11.5、Rust1.98.1、maturin1.15.0：

```powershell
git checkout 9f3537f21a17800377d711ca8717439bcc48f6d5
uv sync --locked --python 3.12
New-Item -ItemType Directory .task-artifacts/s4-09-r0 -ErrorAction Stop
git archive 54ce78bccdcba619ffa2a4d76aeb450bfd24270e --format=zip -o .task-artifacts/s4-09-r0/source.zip
Expand-Archive -LiteralPath .task-artifacts/s4-09-r0/source.zip -DestinationPath .task-artifacts/s4-09-r0/source
$env:RUSTUP_TOOLCHAIN = '1.98.1'
$taskPython = (Resolve-Path .venv/Scripts/python.exe).Path
uv tool run --from maturin==1.15.0 maturin build --manifest-path native/Cargo.toml --release --locked --interpreter $taskPython --out .task-artifacts/s4-09-native-wheels
$taskWheel = Get-ChildItem .task-artifacts/s4-09-native-wheels/*.whl
uv pip install --python $taskPython $taskWheel.FullName
uv run --locked --no-sync python scripts/benchmark_acceptance.py --manifest benchmarks/s4_acceptance_frozen_manifest.json --baseline-root .task-artifacts/s4-09-r0/source --phase formal --output .task-artifacts/s4-09-reproduction.json
```

输出路径必须不存在；正式采样禁止筛case，脚本拒绝覆写manifest/旧报告、源码hash不符、
未提交harness和缺native。复跑前退出本地构建/测试/其他性能任务。
worker固定180秒超时，时间和RSS串行且独立；完整区组包括所有预声明重建。
脚本使用标准库；uv.lock只提供既有开发工具。Windows RSS为进程真实绝对峰值，
不以tracemalloc或增量差代替。其他平台的后备方法会明确记录，不能直接混合成Windows结论。

S5冻结的是以上精确生产源码、harness、manifest、solver/认证/预算、release构建参数
及本轮原始数据hash。S5同单纯复形manifest、GUDHI、三方对拍与正式成本报告仍单独实施。
预声明人工代数窗口没有单纯复形适配时，S5应报告NotApplicable，不能换输入做比值。

## 本地验证（正式采样之后）

- 强制native完整193项，125.177秒，零跳过；[原始日志](../benchmarks/s4_acceptance_verification.log)。
- reference-only隔离wheel：20项中14项通过、6项native测试按预期跳过；明确确认扩展Unavailable。
- reference/native双wheel隔离安装：同20项全部通过、零跳过；确认扩展Available。
- Ruff check/format、Rust1.98.1 fmt/Clippy通过；精确比值溢出边界Rust单测1项通过。
- source/wheel打包、两个公开示例、文档链接与Git空白检查通过。

没有改动生产Python/Rust源码；数学实现hash仍与7fa812d一致。
最终验收PR与合并后的main CI准确身份记录在S4 Epic #59与任务#69，
本页保留发布时的源码、测量和本地验证证据，不用未来main或异平台CI回写性能数据。
