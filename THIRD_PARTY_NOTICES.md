# 来源与第三方依赖

本项目采用 [MIT License](LICENSE)。下列来源与依赖的原有许可和来源记录分别保留。

## 理论与研究材料

理论定义来自 [homology-operator-lab 的固定提交](https://github.com/proffitteoy/homology-operator-lab/tree/6143729669902ee875b211b58085e954c76cdf88)。
迁移测试窗口的源码路径、原始 hash 与本地补充见 [Fixture 来源](docs/FIXTURES.md)。
研究源码与验证成绩不构成本包的运行时依赖或当前验收成绩。

[S4/S5 研究归档](docs/research/s4-s5/)保存上传原件、原型脚本与原始结果；
文件名、原始字节及历史阶段编号保留。来源与 hash 见 [工作包记录](docs/S4_S5_PROJECT.md)。
这些材料用于研究追溯，不进入本包的生产计算路径。

## 分别安装的依赖

| 范围 | 依赖及用途 |
| --- | --- |
| Python reference 运行时 | Python 标准库 |
| 可选 Rust 扩展 | PyO3；由 Cargo.lock 锁定，maturin 负责 wheel 构建 |
| 开发 | hatchling 构建 reference 包，Ruff 检查 Python 源码，uv 管理锁定环境 |
| 可选外部 oracle | GUDHI、NumPy 及 secondary oracle 依赖；仅用于测试/测量对照 |
| 文档 | Sphinx、MyST、Furo、sphinx-copybutton；与库运行时独立 |

上述项目分别按其自身许可证分发；依赖版本以 pyproject、Cargo.lock、uv.lock 和
[文档依赖](docs/requirements.txt)为准。本页说明来源与用途，不改变各依赖的许可证。
GUDHI 只对照同输入的 F2 拓扑，不决定本包的投影、类代表、几何或主 barcode。
