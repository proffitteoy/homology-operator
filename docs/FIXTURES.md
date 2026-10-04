# 产品测试输入与来源

测试样本只用于独立正确性与兼容性验证，不进入生产计算路径。
生产输出来自输入窗口与合法 P；oracle 的最短类质量或 PH 结果不能填充产品结果。

## 单尺度与过滤窗口

[reference.json](../tests/fixtures/reference.json) 保存 23 份带基 H0–H3 链窗口，
覆盖空空间、零同调、基置换、重复尺度、人工正权与实际欧氏边长/面积/体积。
[独立标准库 oracle](../tests/oracle/reference.py) 使用整数 XOR、列组合和 Fraction，
不导入生产消元、solver 或算子。窗口以显式 nrows/ncols/rows 保存矩阵，包括 0×n 和 n×0。
带序基使用唯一字符串，精确权保存 numerator/denominator，浮点权保存 JSON 数值。

迁移来源固定为 [homology-operator-lab](https://github.com/proffitteoy/homology-operator-lab/tree/6143729669902ee875b211b58085e954c76cdf88)
的 `6143729669902ee875b211b58085e954c76cdf88`。每份 fixture 的 source 保留路径、
原始源码 hash、迁移步骤、参数及明确的本地补充。

| 来源文件 | 原始字节 SHA256 |
| --- | --- |
| candidates/minimum-stretch/verify.py | f6d2dbeda729b6bba18ea297c1e72c45bdb4412ec80a5e93fb6352d183bf4ab9 |
| candidates/minimum-stretch/highdim/verify_highdim.py | c2b36b673ba9cf82d0c31ac999d0e2a106897ee13d6e5ec01b8fd63d64d39c13 |
| candidates/minimum-stretch/highdim/verify_euclidean_family.py | 79ac315c336d471ddeca8e7b9ce0b0a914ac9e142eaa1b9703e32d9a2ba5c11c |

input_hash 为规范 UTF-8 JSON 的 SHA256，包含 k、A/D、三组有序基、weights、
weight_semantics、unit 和 arithmetic；source、expected、geometry 及 fixture id 单独记录。
编码使用 sort_keys=True、紧凑 separators、ensure_ascii=False、allow_nan=False。
oracle 加载时检查 hash、形状、二元元素、AD=0、正权、基和 Betti。

[solver_reference.json](../tests/fixtures/solver_reference.json) 保存相同输入的精确最优回归与贪心预期，
浮点实例明确不支持精确优化；生产 solver 证书另由独立提升枚举重放。
[单尺度联合测试](../tests/test_joint.py)与[过滤联合测试](../tests/test_family_joint.py)
核对投影、几何、transport composition、rank 与独立 PH。

## 快照兼容样本

[legacy_results.json](../tests/fixtures/legacy_results.json) 保存 7 份旧 schema 快照，
包括未读取/已读取 Matrix、CyclicTrace、EmptyDomain、预算失败、重复尺度和 Partial 族。
来源为本库 `88f69661859fe7475705fb76589cf30674b63746` 的真实序列化入口；
逐源码 hash 和规范 wire hash 保留在数据中。UUID/time 经过合成固定，仅用于兼容性验证。
[旧格式测试](../tests/test_legacy_results.py)检查原版本重发、无重求解恢复、状态和篡改拒绝。
[后端联合测试](../tests/test_backend_integration.py)检查新版紧凑表示与过滤恢复。

## 显式单形与外部 oracle

[simplicial.json](../tests/fixtures/simplicial.json)保存 6 个显式复形，
[oracle_corpus.json](../tests/fixtures/oracle_corpus.json)保存 77 份产品回归输入。
包含单形出生 stage、原尺度、坐标、正权、单位、算术、截断、来源/hash 及完整 corpus hash。
实际链构造和 GUDHI SimplexTree 均从同一单形列表导出；自动补面或修复过滤被拒绝。
GUDHI 显式使用 F2，核对最高请求次数所需 q+1 次单形、重复尺度和常量末端延拓。
一般 AD=0 窗口没有单形适配时明确 NotApplicable，不另造复形。

[输入测试](../tests/test_simplicial_inputs.py)、[GUDHI 测试](../tests/test_gudhi_oracle.py)
和[完整 corpus 回归](../tests/test_oracle_corpus.py)独立核对输入、拓扑、同 P 几何与恢复。
运行命令见 [VALIDATION](VALIDATION.md)。这些有限输入不证明一般规模效率或应用收益。
