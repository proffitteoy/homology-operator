# Phase 1 reference fixture corpus

[reference.json](../tests/fixtures/reference.json) 保存 23 个有限带基链窗口；[独立 oracle](../tests/oracle/reference.py) 仅使用标准库、整数 XOR、列组合穷举及 `Fraction`，不导入生产 `Matrix`、消元、solver 或算子。当前空间最多 9 维，因此最多枚举 512 条链。这些小实例用于正确性核验，不是性能或一般效率证据。

## 固定来源与迁移范围

来源仓库为 `proffitteoy/homology-operator-lab`，固定提交为 `6143729669902ee875b211b58085e954c76cdf88`。下列 SHA256 对 GitHub contents API 返回的原始文件字节计算，保留源码原始换行；没有执行会覆盖研究结果的脚本，也没有引入研究依赖。

| 源文件 | 原始字节 SHA256 | 迁移内容 |
| --- | --- | --- |
| [verify.py](https://github.com/proffitteoy/homology-operator-lab/blob/6143729669902ee875b211b58085e954c76cdf88/candidates/minimum-stretch/verify.py) | `f6d2dbeda729b6bba18ea297c1e72c45bdb4412ec80a5e93fb6352d183bf4ab9` | `filtration_example` 的 K4 六边图、继承人工权重及 8 个切片；`k4_example` 的有限实例最优值记录 |
| [verify_highdim.py](https://github.com/proffitteoy/homology-operator-lab/blob/6143729669902ee875b211b58085e954c76cdf88/candidates/minimum-stretch/highdim/verify_highdim.py) | `c2b36b673ba9cf82d0c31ac999d0e2a106897ee13d6e5ec01b8fd63d64d39c13` | `edge_cases` 的 ordinary H0 区间与 top sphere 构造原则；明确标注的本地退化和升维补充 |
| [verify_euclidean_family.py](https://github.com/proffitteoy/homology-operator-lab/blob/6143729669902ee875b211b58085e954c76cdf88/candidates/minimum-stretch/highdim/verify_euclidean_family.py) | `79ac315c336d471ddeca8e7b9ce0b0a914ac9e142eaa1b9703e32d9a2ba5c11c` | `geometry(k,4k)` 的 central/lower 子复形、真实欧氏面积/三维体积与原坐标导出的实际边长 |

每个 fixture 的 `source` 保存仓库、提交、路径、上述文件 hash、迁移步骤及参数；本地扩展明确使用 `local_extension=true` 或在迁移文字中说明。本地补充不被描述为研究库已有的序列化 fixture。研究源码中的通过记录也不构成本仓库测试通过记录。

欧氏 H2/H3 的迁移步骤如下，完整坐标另存于每个 fixture 的 `geometry`：

1. 取源 `geometry(k,m)`，`k=2` 或 `3`，`m=4k`，`h=2m/(m²-k)`。保留原点、`k` 个标准基向量及末坐标为 `±h` 的两点，仍使用源顶点编号。
2. 保留 `central=(0,...,k+1)`、`lower=(0,...,k,k+2)` 的全部 `k` 维边界面及其 `(k-1)` 维面，遗漏源 `upper` 及其专属面。以字典序建立所有带序基。
3. `A` 和 `D` 逐单形面取 F2 边界。三个切片依次填入零个、仅 central、central 与 lower 两个 `(k+1)` 单形。
4. 每个当前基面沿用源坐标对应的 `sqrt(det Gram)/k!` 欧氏度量；本次生成通过独立 Leibniz 行列式及整数平方根重新核对有理值。H2 有 7 个三角面，H3 有 9 个四面体面；这是源子复形，完整研究实例的 10/13 个当前坐标没有被冒称为已迁移。

H3 是嵌入 R4 的四面体的实际三维体积；单位是 `model_length^3`，没有臆造为现实测量的立方米。人工 top sphere 的权重是 `(i+1)/2`，独立标为 `abstract_positive_cost`。边长实例只取源 `geometry(2,8)` 的顶点 `[0,1,3]`，重标为 `[0,1,2]`；长度是 `1`、`8/31`、`sqrt(1025)/31`，以 binary64 存储并标为 `FloatingPoint`。它的 F2 拓扑精确，几何 objective 只有浮点数值语义。

## 覆盖与预期

| Fixture | 覆盖 |
| --- | --- |
| `h0_interval_stage_0/1`、`h0_interval_duplicate_scale` | ordinary H0，两个分支合并为一个，重复尺度，末端常值延拓 |
| `h1_k4_stage_0` 至 `7` | 人工正权，单洞、多洞、非平凡且末端线性相关的边界，循环非空的零同调；源 8 切片 Betti 为 `[0,1,2,3,2,1,0,0]` |
| `h1_k4_stage_4_permuted` | 明示 previous/current 基置换，连同边界矩阵与权重一并置换 |
| `h2_euclidean_two_holes/one_hole/filled` | 实际面积、两洞/单洞/零同调，Betti `[2,1,0]` |
| `h3_euclidean_two_holes/one_hole/filled` | 实际三维体积、两洞/单洞/零同调，Betti `[2,1,0]` |
| `h2_abstract_top_sphere`、`h3_abstract_top_sphere` | 人工有理权与无上边界的 top sphere，Betti 1 |
| `h1_euclidean_length_triangle` | 实际边长、浮点算术，Betti 1 |
| `empty_h1`、`acyclic_injection_h1` | 空链窗口、当前空间非空而循环空间为零；与 filled 的循环非空 Betti 0 区分 |

`expected` 保存独立穷举得到的 Betti、循环/边界/商类数量、oracle 的最短类质量，以及一个本地列组合补空间构造的已知可行投影和其 objective。已知可行投影仅为 `Feasible`，不冻结生产 solver 的代表选择。`h1_k4_stage_4` 另存源有限实例的已知最优值 `9/8` 及来源；这不将 Phase 1 的可行 solver 提升为 `ExactOptimal`，生产构造也不能消费 oracle 类表。

`filtration_slice` 只保存 Phase 2 准备材料，不实现传输或 persistence。K4 源 stage barcode 为 `[[1,4],[2,5],[3,6]]`，截断在 stage 5 且末端常值时为 `[[1,4],[2,5],[3,null]]`。重复尺度保留阶段顺序；这些区间使用阶段编号、左闭右开，`null` 表示所声明常值延拓下存活。死亡和非零合并事实可由 stage 4/5 新边界解释；本轮不声称完成 `OperatorFamily`、rank invariant 或独立 PH 对拍。

## 存储与独立核验

矩阵始终包含 `nrows`、`ncols`、`rows`，包括 `0×n` 和 `n×0`。基是非空唯一字符串标识的有序数组。精确权为 `{numerator, denominator}`，浮点权为 JSON 数值；语义、单位和算术策略是单独字段。

`input_hash` 为 SHA256，内容仅包括 `k`、`A`、`D`、三组有序基、`weights`、`weight_semantics`、`unit`、`arithmetic`。编码为 UTF-8 的 `json.dumps(..., sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)`。Fixture id、source、expected 和 geometry 不在此输入 hash 中；source 的 hash 单独绑定原始来源文件。生产身份模型可再包含 provenance，但不能用 source hash 代替链输入 hash。

Oracle 的 `load_fixtures()` 核对输入 hash、矩阵形状与二元元素、`AD=0`、基长度/唯一性、正权和 Betti。`verify_projection(fixture, projection_columns)` 接受长度 `n` 的 packed 整数列，逐条检查全部链上的幂等性与循环像、全部边界上的湮灭，以及所有循环的 `z+Pz∈im(D)`。`objective` 对非零循环独立穷举，空定义域返回约定值 0。类最短质量只供测试 oracle 使用，不能填入生产 `selected_mass`。

安装及统一测试入口见 [根 README](../README.md) 和 [验证说明](VALIDATION.md)。单独检查 corpus 可在已激活的项目 Python 环境中运行：

```powershell
python -c "import sys; sys.path.insert(0, 'tests/oracle'); from reference import load_fixtures, columns, verify_projection; fixtures=load_fixtures(); assert all(verify_projection(f, columns(f['expected']['known_feasible_projection'])) for f in fixtures); print(len(fixtures))"
```

此命令不联网、不写研究数据，也不调用生产实现。完整 Phase 1 的生产查询对拍由相应数学测试承担。Fixtures 不证明一般规模效率、无限族稳定性、过滤传输正确性或全局最优性。
