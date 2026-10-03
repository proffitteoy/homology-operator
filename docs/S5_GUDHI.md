# S5：显式同输入 GUDHI 验收

## S5-01 输入冻结与双构造器

[issue #70](https://github.com/proffitteoy/homology-operator/issues/70) 的输入适配器位于
[tests/oracle/simplicial.py](../tests/oracle/simplicial.py)，不进入运行时包。
reference 的运行时依赖仍为空；GUDHI 仅在测试 oracle 和后续测量对照路径使用。
此工作包没有实现 PH oracle、三方联合验收或性能结论，它们由后续 S5 issue 交付。

[冻结 corpus](../tests/fixtures/s5_simplicial.json) 有六个明确构造的复形：空复形、孤点、
重复 scale 的环/填充、H2 球面/三维填充、受控 H3/四维填充、截断环存活。
来源是明确记录的人工单形出生列表，未迁移研究仓库数据。
每份 manifest 包含源 payload/hash、总 input hash、canonical 单形、整数 birth stage、
原 scale、顶点坐标、坐标顺序、正权/单位/算术、请求次数、截断维数/阈值和常量末端延拓。
corpus hash 覆盖完整 manifest；几何权与 topology 输入的身份分别保留。

整数 stage 是两端实际使用的 filtration，原 scale 保留在 manifest 中。
同 scale 不同 stage 不合并；同 stage 瞬时配对的 PH 规范化属于 S5-02。
stage 限于能被 double 精确表示的整数范围，顶点标识限于非负 int32。
支持 H0–Hq 的次数前缀，q≤3；输入最大维数为 q 或 q+1。
只提供 q 维单形时，q+1 维死亡不会被自动补出，末端存活仅指该截断的常量延拓。

校验先拒绝缺面、非单调面出生、非 canonical 单形、重复顶点/单形、非法尺度/权重、
hash 篡改和未声明的截断。不把零长度或零体积改成 epsilon。
ExactInteger、ExactRational 与 FloatingPoint 权重明确区分；重复坐标本身不修改权重。
一般 AD=0 链窗口如果没有显式单纯复形适配，`applicability()` 返回 NotApplicable，
不会生成另一份点云来代替原输入。

两个构造器各从同一 manifest 构造实际输入：链侧保留带序基、A/D 的显式形状与 F2 面边界；
GUDHI 侧插入明确单形，禁止调用 filtration repair。
审计从实际链基/矩阵列和 SimplexTree `get_filtration`/`get_boundaries` 回读，
核对所有 stage 的活动坐标、权重、算术、每个单形的首次出生、面边界与维数计数。
两端导出均须等于声明输入。GUDHI 插入导致的补面和 filtration 降低会被检出。
[双边完整导出](../benchmarks/s5_input_audit.json) 保存实际内容、构造 hash、环境及 corpus hash。

## 安装与复跑

oracle 依赖组锁定 GUDHI 3.11.0、NumPy 2.2.6，具体平台 wheel URL/hash 见
[uv.lock](../uv.lock)。它们不是生产依赖。Python 3.10/3.12，Windows x64 或 Linux x64：

```powershell
uv sync --locked --group oracle --python 3.12
$env:HOMOLOGY_GUDHI_REQUIRED = '1'
uv run --locked --group oracle python -m unittest discover -s tests -p 'test_s5*.py' -v
uv run --locked --group oracle python scripts/check_s5_inputs.py --output .task-artifacts/s5-input-recheck.json
```

输出路径必须不存在，防止覆盖冻结证据。导出不包含 PH 结果。
缺 GUDHI 时普通 reference suite 会明确跳过双构造器测试；设置上述环境变量则直接失败。
[S5 oracle CI](../.github/workflows/s5-oracle.yml) 在 Windows/Python 3.12 和
Linux/Python 3.10、3.12 安装锁定组并强制执行真实 GUDHI 测试。
CI 配置、本地通过和准确 PR head 的远端结果分别报告，不借用 S4 CI 认证新内容。
