# Homology Operator：验证说明

## 固定理论与研究仓库验证记录

理论来源为 `proffitteoy/homology-operator-lab @ 6143729669902ee875b211b58085e954c76cdf88`。远端 [原始验证契约](https://github.com/proffitteoy/homology-operator/blob/c0299c3b7750c8a12ced00bf479753236a7dbc85/docs/VALIDATION.md) 记录：其父提交 `cc6f9b637552d3eda4b948121b932576ae5eeec9` 的 `run_tests.py` 通过 32 组检查（16 exact、16 auxiliary），后续提交仅修正 README 清单 hash。这里保留该来源记录，本轮未复跑研究检查；exact 组内仍需按具体报告区分符号、区间及附带数值检查，不能作为本仓库测试通过声明。

## 当前可执行验证

S4-06 增加6项几何 workspace 回归：显式/Factorized/HC 在 0/1/63/64/65/127/128/129 维上的原坐标输出；u64 最大值、单次求和溢出与超大整数/任意正有理权；binary64 fsum、subnormal 与浮点溢出；0/1/8/64/1024 两次批查询和真实缓冲扩容复用；非循环/非法坐标/索引拒绝；projection/weight/basis/run 混用、查询 JSON 往返和 NotComputed/Computed 快照历史。既有23个冻结窗口的几何对拍继续经过新入口，独立原坐标质量与共享质量恒等式同时核对。缺少扩展显式返回 Unavailable，native CI 强制这些测试实际运行；有限性能采样另见 [BENCHMARKS](BENCHMARKS.md)，不替代 S4/S5 准入。

S4-04 新增8项验收（其中2项完全不依赖Rust）：23窗口的Factorized/HC全链/循环/非循环、几何与规范核；11过滤族的全部区间transport/rank/barcode与恢复；完整增广逆与至多3×3穷举、小链窗口；0/1/63/64/65/127/128/129边界；阻断dense P/展开G/U路径；未知版本/非法因子/零投影/身份篡改及资源失败。独立D像分解复用核验所有循环残差，不信任native分解。恢复无扩展可运行；native CI仍强制运行全部native测试。原129项数学与历史数据保持，本项不是S4阶段性能准入。


