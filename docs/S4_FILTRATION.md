# S4-07：相邻 transport 与过滤快照

实现对应 [#67](https://github.com/proffitteoy/homology-operator/issues/67)。主结果来自当前族的
T_ij=P_j J_ij|ker(L_i)，无独立 PH 旁路。上传的[端点脚本](research/s4-s5/quiver_barcode_probe.py)
及[5689例记录](research/s4-s5/quiver_barcode_probe_result.json)保持原字节和历史限制。

## 实现与成本

内部共享末阶段的标签空间与阶段活动索引，比较边界对应列/新增行验证链映射，按索引嵌入
投影，不物化 inclusion。公共 inclusion(i,j,degree) 仍按请求返回完整矩阵。每个不同投影的
核基和 packed 列消元分解保存一次，multi-RHS 复用该分解。工作区用标准库 Python 任意精度
整数，无新依赖；支持现有显式矩阵和 CyclicAction 的 apply/kernel_basis 协议。
#64 因子化 action、#66 native 几何及 #68 完整绑定仍需各自实现和联合验收。

barcode() 只读取相邻核坐标映射，不请求完整 chain action、历史基或全部区间 rank。
transport(i,j) 按需返回原有完整 value；transport_rank(i,j) 仅读坐标映射的秩；
rank_table() 显式输出 s(s+1)/2 条 rank，按真实二次输出成本计费。action/transport/rank
三种缓存分别为 LRU，cache_limit=64 限制每种条目，0禁用；不是字节或 RSS 硬限制。
核分解随不同投影保留，tracking 是显式查询历史。恢复快照先保留全部已存查询以无损重发，
下次缓存写入按上限淘汰；已返回 QueryResult 不变。族的工作区不修改已有算子。

任意循环 tracking 直接计算 P_j J_ij P_i x，在循环上等于 P_j J_ij x；质量/支撑从同一
已投影链读取，不再次投影。缺失端点仍缺失；合法端点可越过失败中间阶段直达，完整
composition 证书仍要求中间阶段可用。死亡类为合法零链、零质量和空支撑。

## 完整 birth 前缀证明

记 V_i=ker(L_i)，f_i=T(i,i+1)。投影同调保持、目标投影消去边界及链映射相容给出
T(b,i+1)=f_i T(b,i)，独立于任何 PH reduction。

活动向量按 birth 非降序排列，保持两个不变量：活动向量是 V_i 的基；对于每个
0≤b≤i，birth≤b 的活动向量张成 im T(b,i)。

初始所有单位向量出生于0，构成 V_0 的基，且 T(0,0)=I。假设在 i 成立。按旧到新 birth
作用 f_i 并保留独立像。每个被丢弃的像已由当前前缀内更早保留的像张成，故对任何 birth
前缀，筛选后的张成空间恰为原前缀的像，即 f_i(im T(b,i))=im T(b,i+1)。零像同样属于
已有张成空间，零维不例外。保留像独立且张成 im f_i。按目标坐标顺序补独立单位向量，
标为 i+1 出生，得到 V_(i+1) 的基；它们不进入 b≤i 的前缀。b=i+1 的完整前缀张成目标空间，
与 T(i+1,i+1)=I 一致。归纳完成。

因此 j 阶段 birth≤b 的存活数等于 r(b,j)=rank T(b,j)，恰在 b 出生的存活数为
r(b,j)-r(b-1,j)，负索引 rank 约定为0。从 d−1 到 d 死亡的这种向量数恰为

```text
r(b,d-1) - r(b-1,d-1) - r(b,d) + r(b-1,d).
```

这正是保留在 tests/oracle/reference.py 的原全区间 rank 公式。末阶段存活向量在 Constant
延拓下给出 death=None。证明适用任意有限 F2 映射序列，与维数和重复 scale 无关；scale
只标注，stage 顺序保持。有限测试验证实现，不代替归纳证明。

## 历史区间基

仅丢弃依赖像不能直接给出正确历史基。例如两向量的像相同，死亡生成元应为其源向量之和。

barcode_basis() 单独保存每个活动向量从 birth 到当前阶段的坐标历史。当 birth=b 的向量
在 j 的像依赖时，消元给出其在更早保留像中的系数。保留向量 birth≤b，历史覆盖全部
b≤s<j。对这些 s，将待死亡历史加上同一线性组合。更早历史传输相容，故修正历史仍相容，
在 j 的像严格为0。其它历史不变；每个受影响旧阶段只是把一个基向量加上其它基向量，
为可逆初等变换，故过去阶段的基仍满秩、传输等式仍成立。出生向量的单阶段历史及存活
向量的像延长保持不变量。归纳后每条历史在活跃阶段组成基、逐级传输一致、有限死亡归零，
构成所报告端点的区间分解。

vectors 保存 stage、核坐标、当前 P 的原链代表及阶段六身份。这可有二次输出量，普通
barcode 不生成历史。它们不声明最短质量，也不限制任意循环组合 tracking。
44个冻结过滤/solver配置、混合显式与 CyclicAction 族及5689个原 corpus 模块分别检查
原链追踪和历史基相容性。

## 快照兼容

默认 family schema_version=2：windows 保存末阶段 A/D、三个全局基，各阶段活动索引、
原权重和输入元数据；stage_results 用 input_ref 消除重复输入。读取重建限制矩阵，重验
输入/投影/证书/族身份，重算已存 transport/rank、barcode、tracking、已请求历史基。
仅不可变边界及基被 intern；权重、投影选择和 solver run 不合并。bool、越界/重复活动
索引、错误引用、混用身份和输出篡改拒绝。schema 1 可读并原版本重发；
to_result(schema_version=1) 显式输出旧格式，不含新历史基。单尺度 schema 不变。
schema 2 需升级读取客户端。

## 复跑

在仓库根目录运行：

```powershell
uv run --locked python -m unittest discover -s tests -v
uv run --locked ruff check .
uv run --locked ruff format --check .
pwsh -NoProfile -File ./scripts/check_docs.ps1
git diff --check
uv run --locked python scripts/benchmark_filtration.py --output benchmarks/s4_filtration_ablation.json
```

测量要求计算源码/worker 已提交，逐文件核对 HEAD/LF hash。baseline 为
d9bdf3bfe7a3fb365929d99d90cb85ca7c367f23 的 family.py，其余源码相同。两个本地合成过滤
为常量阶段、递增坐标与边界消去，含64/192阶段及重复 scale。legacy、adjacent、完整 rank
按固定打乱顺序在独立冷进程串行执行，每格3次。保存源码/fixture/语义输出 hash、全部样本、
互斥计时段、绝对峰值 RSS、认证/预算。两版快照大小/含验证导出时间另列，在查询计时/RSS
采样之后。完整 rank 输出更多，不是普通 barcode 的同输出速度比。有限合成实验不构成
GUDHI、全 native、应用或发行验收。

## 本地冻结结果（2026-10-02）

[全部36个原始样本](../benchmarks/s4_filtration_ablation.json) 绑定计算源码
e0e31835e61b590f2e1467ed34e09f470884d12f，Windows x64 / CPython 3.10.11；每格3次。
同一fixture/阶段数的公共barcode与几何输出hash全部一致。以下为192阶段冷worker总耗时
中位数（包含导入、输入、solver/验证、族验证、读取及几何），RSS为采样时的绝对进程峰值。

| 过滤 | 路线 | worker秒 | 峰值MiB | 保留chain action数 |
| --- | --- | --- | --- | --- |
| 常量 | legacy | 38.8516 | 139.64 | 18528 |
| 常量 | adjacent | 0.1123 | 19.71 | 0 |
| 常量 | 完整rank表 | 4.4234 | 22.51 | 0 |
| 递增/消去 | legacy | 35.1155 | 140.89 | 18528 |
| 递增/消去 | adjacent | 0.1152 | 20.17 | 0 |
| 递增/消去 | 完整rank表 | 4.3312 | 23.79 | 0 |

64阶段快照的schema 2字节数比schema 1小约15.4%（常量）/11.7%（递增），投影与证书
仍逐阶段保存；这是输入存储压缩，不声称全记录共用投影。快照导出/恢复成本另存原样本，
不混入上述读取时间/RSS，也不把schema的不同输出字节数当成相同输出速度比较。

旧版 d9bdf3b 实际生成的schema 1快照经新reader恢复、原版本重发，JSON逐字一致。
另用隔离副本将 #64 的已提交源码
3a6c6fa13d86102954227a34ace103ec8e3fc8f7 与本版family.py组合，23个冻结窗口的
Matrix/CompactAction.HC混合族通过transport证书、barcode、历史基、循环tracking与
schema 2往返。此smoke不覆盖native因子构造或尚未交付的#66，也不代表依赖PR已合并。

本地从同一源码构建Rust 1.98.1 / PyO3 0.29.3 / maturin 1.15.0 release wheel，
设置HOMOLOGY_NATIVE_REQUIRED=1、使用uv --no-sync后[148项完整回归](../benchmarks/s4_filtration_verification.log)
全部通过，无跳过。Ruff、文档/链接、示例、构建、隔离wheel导入另实际通过。远端CI及
最终main验收按实际PR/head记录，不以本地日志代替。

