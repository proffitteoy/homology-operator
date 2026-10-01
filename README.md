# homology-operator

Boundary-native F2 homology operators with joint persistence and geometric outputs.

从有限带基链窗口 `C_{k+1} --D--> C_k --A--> C_{k-1}` 及正坐标权重出发，构造同调投影 `P` 与算子 `L=I+P`。拓扑、代表、距离、支撑与伸长来自同一个投影身份；过滤上的 persistence 由算子族的传输读取。

## 当前状态

2026-10-01 按 [冷启动计划](docs/冷启动.md) 完成项目规则、文档入口和验证工具初始化。当前处于 Phase 0 契约准备阶段，文档描述的算子、solver、filtration 和 fixture corpus 尚未实现；没有已发布版本。

初始化前本地 `HEAD` 与 `origin/main` 均为 `6ddce1b4e4d55c0aaff399c001e684d908026830`。理论来源固定为 [homology-operator-lab 的指定提交](https://github.com/proffitteoy/homology-operator-lab/tree/6143729669902ee875b211b58085e954c76cdf88)，研究代码及其依赖不构成本仓库的运行时依赖。

2026-10-01 规划时另行核实远端 `main` 为 `c0299c3b7750c8a12ced00bf479753236a7dbc85`，已含原始 README、接口和三阶段验证文档；初始化前的本地跟踪引用落后于远端。开发任务由私有 [GitHub Project #3](https://github.com/users/proffitteoy/projects/3) 管理，三阶段与详细路线的对应见 [验证说明](docs/VALIDATION.md)。

## 开始使用

先读 [项目约定](AGENTS.md) 和 [文档索引](docs/README.md)。当前只需 Git 和 PowerShell 7 即可检查仓库文档；没有安装包或算子运行命令。

在仓库根目录运行：

```powershell
pwsh -NoProfile -File ./scripts/check_docs.ps1
git diff --check
```

第一条检查必需文档、UTF-8、冲突标记和本地 Markdown 文件链接，涵盖尚未跟踪的文档；失败时退出码非零。第二条检查已有跟踪文件改动的空白错误。详细范围和数学实现的验收门槛见 [验证说明](docs/VALIDATION.md)。

| 入口 | 当前状态 |
| --- | --- |
| 文档检查 | `scripts/check_docs.ps1`，可运行 |
| 主语言、包管理器和依赖 | 尚未选定；首次 reference 实现时记录，高性能核心按路线图 Phase 4 决定 |
| 启动、构建、数学测试 | 尚无实现与入口 |
| Lint、format、typecheck | 尚未配置 |
| 配置、迁移、种子数据、部署 | 当前没有对应需求或脚本 |
| CI、发布、LICENSE | 尚未配置或选定 |

## 仓库入口

| 路径 | 职责 |
| --- | --- |
| [AGENTS.md](AGENTS.md) | 项目操作规则、数学红线、命令与 skills 使用范围 |
| [HOMOLOGY_OPERATOR_ROADMAP.md](HOMOLOGY_OPERATOR_ROADMAP.md) | Phase 0–7 的开发目标和退出条件 |
| [docs/](docs/README.md) | 架构、接口、结果、solver、验证契约及冷启动入口 |
| [docs/development/](docs/development/) | 通用架构模板、约束、代码组织与审计参考材料 |
| [scripts/check_docs.ps1](scripts/check_docs.ps1) | 文档一致性检查工具 |

`src/`、`tests/`、`benches/` 在架构文档中表示后续组织建议，尚未创建。首个实现按路线图推进：F2 代数与 `ChainWindow` → 合法投影和独立 validator → 同一算子的完整联合读取与小规模 fixture 验证。实现和运行环境建立后同步更新真实命令。

`selected_mass` 表示当前投影选定代表的质量，不能声称是最短代表。可行投影、精确拓扑、全局最优伸长、稳定性和性能分别需要相应证据，见 [solver 契约](docs/SOLVER_CONTRACT.md) 和 [开发路线](HOMOLOGY_OPERATOR_ROADMAP.md)。
