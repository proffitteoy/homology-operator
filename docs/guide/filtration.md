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

## 稳定特征引用与单形来源

`features()` 复用完整历史区间基，提供绑定族身份、次数、端点、重复项和生成元历史的引用；
`resolve_feature(reference, stage)` 返回目标阶段的原链代表、核坐标、原链基和六身份。
非活跃阶段返回 `NoClass`；跨过滤、跨运行或被替换的引用被拒绝。
可选 `simplex_source` 保留逐单形全序并重建每阶段 A/D；`feature_pairing(reference)`
以完整历史基和传输认证出生、死亡单形，没有来源时明确 `Unavailable`。
新查询与来源使用 schema 3，旧 schema 1/2 保持可读；带来源或引用时禁止降级丢失信息。
输入格式、两种阶段编号、证明和资源边界见[英文说明](../en/guide/filtration.md#feature-references-and-simplex-sources)。
