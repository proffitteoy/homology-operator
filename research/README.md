# 归档研究代码与原件

[s4-s5/](s4-s5/) 保存上传的计划、摘要、独立端点算法原型和原始结果。
这些文件从文档树迁到这里，文件名、原始字节、SHA256 和历史 S3/S4 编号保持不变。
来源与五份原件 hash 记录见[工作包来源](../docs/S4_S5_PROJECT.md)；上传 zip 的三项解包内容
与归档文件一致，zip 原件保留在原用户工作区，不重复提交二进制副本。

实际库代码位于 [src/homology_operator](../src/homology_operator/) 和 [native/src](../native/src/)；
独立测试 oracle 位于 [tests/oracle](../tests/oracle/)；维护中的测量与审计入口位于 [scripts](../scripts/README.md)。
归档原型不导入上述生产模块，也不参与生产计算路径。

## 可复现原型

[quiver_barcode_probe.py](s4-s5/quiver_barcode_probe.py) 用 packed 列向量表示有限 F2 持久模，
将相邻映射的端点读取与全区间 rank oracle 对拍：689 个两阶段小映射穷举和 5,000 个随机例，
固定 seed=20261002。原[结果](s4-s5/quiver_barcode_probe_result.json)记录全部 5,689 例、corpus hash 和脚本 hash。

在仓库根目录运行：

```powershell
python scripts/reproduce_research.py --reproduce probe --output-dir .task-artifacts/probe-reproduced
```

这是标准库独立有限检查；不产生历史区间基，不验证几何追踪、solver、native、GUDHI 或序列化，
也不测性能。生产的相邻 transport/历史基与同 P 几何验证仍见 [S4-07](../docs/S4_FILTRATION.md)
和 [tests/test_family.py](../tests/test_family.py)。
原型保留上传字节，统一复现入口为它指定新输出，随后核对完整结果，避免覆盖原证据。

## 成果与未解决问题

数学契约、有限验证、正式性能和未解决问题分别列在[研究成果索引](../docs/research/README.md)。
所有原始数据、fixtures 和原件由 [registry.json](../benchmarks/registry.json) 登记，
[校验与统计重建](../benchmarks/README.md)提供统一入口。
理论研究仓库固定于 [6143729](https://github.com/proffitteoy/homology-operator-lab/tree/6143729669902ee875b211b58085e954c76cdf88)，
其研究依赖和验证成绩不当成本库已有实现或本轮验证。
