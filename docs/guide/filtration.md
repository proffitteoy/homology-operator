# 有限过滤与类追踪

[English](../en/guide/filtration.md)

## 阶段与包含

给 `OperatorFamily` 提供同次数的窗口、对应算子和有序 scales。
三个次数的基标识确定坐标包含，检查链映射和权重政策。
默认 Inherited 要求原坐标权重继承；Variable 显式允许变权，语义与单位仍需相容。
重复尺度保留阶段顺序；末端按 Constant 延拓。

## Barcode 与传输

主来源为 `T_ij=P_j J_ij|ker(L_i)`，不使用外部 PH 结果补齐主输出。
`barcode()` 只读取相邻 transport；`transport_rank(i,j)` 返回一个区间的 rank。
`barcode_basis()` 显式生成死亡回改后的历史区间基；`rank_table()` 显式读取二次大小的完整表。
区间左闭右开，保留重数，death_stage=None 表示声明末端延拓下存活。
同尺度跨阶段区间保留，失败 rank 不变为空 barcode。

## 几何追踪与恢复

track_class、track_mass 和支撑追踪接受源循环，从目标的同一投影读取。
死亡类给出合法零代表、零质量和空支撑。失败阶段仍为缺失，不补成零维阶段。
cache_limit 限制各 LRU 缓存条目，不是字节/RSS 上限。
默认族快照采用 schema 2；schema 1 可读并原版本重发，或显式请求旧格式。
恢复重验投影、族身份、已存传输与查询，不重新求解。

完整签名与返回值见[API](../INTERFACE.md#过滤与传输)，相邻读取与历史基不变量见
[数学与架构](../ARCHITECTURE.md)。
