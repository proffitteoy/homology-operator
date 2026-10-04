# 二元同调算子：定义、构造与性质

[English](en/MATHEMATICS.md) · [算例与 Python 用法](guide/single-scale.md) · [solver 契约](SOLVER_CONTRACT.md)

`homology-operator` 实现一种从边界数据直接构造的二元同调算子。
数学对象是原链空间上的线性算子 $`L=I+P`$：它的核实现同调空间，
配套投影 $`P`$ 为每个同调类选定一个线性一致的循环代表。
正坐标权重把同一个作用转化为代表质量、类距离、共享支撑与最坏伸长；
多个尺度的核之间通过投影传输实现完整的持久同调模。

本页给出定义与证明，以及这些数学对象在当前产品中的对应关系。
定义适用于任意固定次数的有限带基二元链窗口。
理论来源为 [固定研究提交中的 D1、T1–T4 与 E4](https://github.com/proffitteoy/homology-operator-lab/blob/6143729669902ee875b211b58085e954c76cdf88/docs/proof/PROOF.md)。
这里保留产品所需的完整论证与算例，不要求安装研究仓库。

## 1. 输入与数学对象

设

```math
C_{k+1}=\mathbf F_2^p\xrightarrow{D}
C=C_k=\mathbf F_2^n\xrightarrow{A}\mathbf F_2^m=C_{k-1},
\qquad AD=0.
```

矩阵采用列向量约定，$`A`$ 为 $`m\times n`$，$`D`$ 为 $`n\times p`$。
所有链运算均在 $`\mathbf F_2`$ 上，因此加法也是 XOR，减法与加法相同。
三个链空间具有固定带序基；中间空间的坐标具有严格正权 $`w_i>0`$。

记循环空间、边界空间与同调商为

```math
Z=\ker A,\qquad B=\mathrm{im}\,D\subseteq Z,\qquad
H=Z/B,\qquad q:Z\to H.
```

第 $`k`$ 次 Betti 数为

```math
\beta=\dim H=n-\mathrm{rank}\,A-\mathrm{rank}\,D.
```

链的加权质量是

```math
m_w(x)=\sum_{i:x_i=1}w_i.
```

它在非零链上严格为正，并满足 $`m_w(x+y)\le m_w(x)+m_w(y)`$。
单位权表示活跃坐标的数量；实际边长、面积、体积或代价须由输入声明。
在更高次数中，$`k`$ 只改变链与权重的解释，不改变以下代数构造。

## 2. 同调投影与同调算子的定义

**定义。** 合法同调投影是一个线性映射 $`P:C\to C`$，满足

```math
P^2=P,\qquad AP=0,\qquad PD=0,\qquad
z+Pz\in B\quad\text{对所有 }z\in Z.
```

对应的**二元同调算子**定义为

```math
\boxed{L=I+P.}
```

这些条件各有具体含义：幂等性使一次选择即稳定；$`AP=0`$ 使输出为循环；
$`PD=0`$ 杀掉边界；最后一项保证循环更新只加边界，保持原同调类。
最后一项不可省略：当 $`H\ne0`$ 时，零投影满足前三项却丢掉所有非零类。

在代码中，`HomologyOperator.P` 与 `.L` 分别对应上述映射。
`project(x)` 读取 $`Px`$，`apply_operator(x)` 读取 $`Lx`$。
对循环 $`z`$，一次更新

```math
z+Lz=Pz
```

给出同调相同的选定代表。原始作用定义在全部链上；只有循环才具有这里的同调类语义。

### 2.1 从边界矩阵构造

选取代数广义逆

```math
G:\mathbf F_2^m\to C,\quad AGA=A,\qquad
U:C\to\mathbf F_2^p,\quad DUD=D.
```

它们总是存在：在矩阵的像上选择线性原像，再延拓到整个目标空间即可。
这里使用有限域消元。令

```math
R=I+GA,\qquad Q=I+DU,\qquad
\boxed{P=QR=(I+DU)(I+GA)},\qquad L=I+P.
```

构造的三个步骤是：$`R`$ 将任意链回缩到 $`Z`$；$`Q`$ 从循环中删掉边界方向；
$`P`$ 在原坐标中给出一个固定的类代表。构造器需要的是 $`A,D,w`$，
同调商 $`H`$ 和商映射 $`q`$ 用于分析这一构造，无须调用者预先提供同调基。

**构造合法性证明。** 广义逆关系给出

```math
AR=0,\quad R^2=R,\quad R|_Z=I_Z,\qquad
Q^2=Q,\quad QD=0,\quad AQ=A.
```

因为 $`QRx`$ 是循环，$`RQR=QR`$，于是 $`P^2=QRQR=Q^2R=P`$。
又 $`RD=D`$，故 $`PD=QD=0`$，且 $`AP=AQR=AR=0`$。
对循环 $`z`$，$`Pz=Qz=z+DUz`$，所以 $`z+Pz=DUz\in B`$。
四项条件全部成立。

## 3. 核实现同调：完整证明

**核定理。** 每个合法投影及对应算子满足

```math
L^2=L,\qquad \ker L=\mathrm{im}\,P\subseteq Z,\qquad
q|_{\ker L}:\ker L\xrightarrow{\cong}H.
```

因此

```math
\dim\ker L=\beta,\qquad
Pz=0\iff z\in B\quad(z\in Z),\qquad
Pz=Py\iff z+y\in B\quad(z,y\in Z).
```

**证明。** 特征二与 $`P^2=P`$ 给出 $`L^2=I+P=L`$。
若 $`x=Py`$，则 $`Lx=Py+P^2y=0`$；若 $`Lx=0`$，则 $`x=Px`$。
故 $`\ker L=\mathrm{im}\,P`$，且由 $`AP=0`$，核包含于 $`Z`$。

对每个类 $`h=qz`$，定义 $`s(h)=Pz`$。若 $`qz=qy`$，则 $`z+y\in B`$，
由 $`PD=0`$ 得 $`Pz=Py`$，所以 $`s`$ 良定义且线性。
同调保持给出 $`qs(h)=qPz=qz=h`$，即 $`qs=I_H`$。
在核中 $`x=Px=s(qx)`$，所以 $`s`$ 正是限制商映射的逆。
每个类在核中都有且仅有一个向量，得到所述同构及等价判据。

这里的核是一组实际循环代表，而非仅一个维数。
它有 $`2^\beta`$ 个向量；这个基数与 Betti 数 $`\beta`$ 的含义不同。

### 3.1 谱与信息来源

幂等性给出原链空间的直和分解

```math
C=\mathrm{im}\,P\oplus\ker P.
```

$`L`$ 在第一项上为零，在第二项上为恒等，因而

```math
\chi_L(\lambda)=\lambda^\beta(\lambda+1)^{n-\beta}.
```

所以该算子的特征值只有 $`0,1`$。几何信息来自原坐标中的带权作用和选定代表，
读者应据此解释质量与距离。实内积的 Hodge 正定性不能直接移到 $`\mathbf F_2`$：
一条边的边界 $`d=(1,1)^\mathsf T`$ 满足 $`d^\mathsf T d=0`$，却没有非零一维同调。
本定义通过上述四项条件建立核与同调的对应。

## 4. 线性代表选择与最小伸长

投影的选择决定如何同时实现所有类。由核定理，它在循环上的作用必为

```math
P|_Z=sq,\qquad s:H\to Z,\quad qs=I_H.
```

$`s`$ 称为商映射的**线性截面**。它要求 $`s(h+g)=s(h)+s(g)`$，
因此类代表的选择相互约束。两个基类各自选最短代表，未必能使它们的和也短。

### 4.1 固定回缩下的全部投影

固定上述 $`R`$。给定任意截面 $`s`$，映射 $`T(z)=z+sqz`$ 是 $`Z\to B`$ 的回缩。
选 $`D`$ 在 $`B`$ 上的线性右逆，把 $`T`$ 提升为 $`U_Z`$，再延拓到 $`C`$。
则 $`DU|_Z=T`$、$`DUD=D`$，并有 $`QR=sqR`$。
所以广义逆构造在循环上覆盖**所有**线性截面；在全链空间上覆盖与固定 $`R`$ 相容的延拓。

记 $`r=\dim B`$，选一个截面 $`s_0`$。其他截面恰为

```math
s=s_0+t,\quad t\in\mathrm{Hom}_{\mathbf F_2}(H,B),\qquad
\Omega_R=\{(s_0+t)qR:t\in\mathrm{Hom}(H,B)\}.
```

这是维数 $`r\beta`$ 的仿射空间，恰有 $`2^{r\beta}`$ 个投影。
同一固定回缩下的 $`P,Q\in\Omega_R`$ 还满足

```math
PQ=P,\qquad QP=Q,\qquad(P+Q)^2=0.
```

例如 $`PQ=sqR\,s' qR=sqR`$，因为 $`R|_Z=I`$ 且 $`qs'=I`$。
这些关系描述算子选择的空间；它们不表示两个投影的代表、支撑或质量相同。

### 4.2 循环上的最坏质量扩张

定义

```math
\Gamma_w(P)=\max_{0\ne z\in Z}\frac{m_w(Pz)}{m_w(z)},\qquad
\Gamma_*=\min_{P\ \mathrm{legal}}\Gamma_w(P).
```

有限二元空间保证最优值存在。固定 $`R`$ 已覆盖全部循环截面，
所以该最优循环目标与回缩 $`G`$ 的选择无关；非循环作用和并列选择仍可依赖 $`R`$。
最小伸长算子是 $`L_*=I+P_*`$，其中 $`P_*`$ 达到上述最小值。

为了分析目标，定义真正最短类质量

```math
\mu_w(h)=\min\{m_w(z):z\in Z,\ qz=h\}.
```

**截面等价定理。** 若 $`\beta>0`$，则

```math
\boxed{\Gamma_w(P)=\max_{0\ne h\in H}\frac{m_w(sh)}{\mu_w(h)}}.
```

**证明。** 同一类中的所有循环有相同输出 $`sh`$，所以该类内最大的质量比由最短输入取得。
零类的输出为零。逐类取最大值即可。这也解释为何目标约束全部类的线性组合。

$`\mu_w`$ 是这里的数学分析量，当前 `minimum_class_mass()` 返回 `Unavailable`。
求解与 `stretch()` 可以直接枚举循环比值，不依赖该查询。
若 $`Z=0`$，$`\Gamma`$ 的约定值为零，产品报告 `EmptyDomain`；
若 $`Z\ne0`$ 但 $`H=0`$，循环投影为零，$`\Gamma=0`$ 是 `Computed` 的合法零。

### 4.3 通用界与计算代价

当 $`\beta>0`$ 时，

```math
1\le\Gamma_*\le\beta.
```

下界来自 $`sh`$ 本身是 $`h`$ 的一个代表。
上界可由贪心截面构造：依次选质量最小、且类不在已选类张成中的循环 $`z_i`$。
质量序列非降。对类 $`h=\sum_i a_i qz_i`$，设最大活跃下标为 $`j`$。
$`h`$ 的最短代表也是第 $`j`$ 步的候选，故

```math
m_w(z_i)\le m_w(z_j)\le\mu_w(h)\quad(i\le j),\qquad
m_w(sh)\le\sum_{a_i=1}m_w(z_i)\le\beta\mu_w(h).
```

这证明界，未给一般输入的多项式时间优化算法。
完整循环评估有 $`2^{\dim Z}-1`$ 个非零输入；固定回缩的完整截面搜索有 $`2^{r\beta}`$ 个候选。
reference 的精确穷举、贪心、秩二与结构族 solver 各有实际支持域和预算，见 [solver 契约](SOLVER_CONTRACT.md)。
默认 `FeasibleSolver` 构造合法算子；只有独立最优证书支持时才报告 `ExactOptimal`。

## 5. 同一作用给出的几何

对循环 $`z,y`$ 定义

```math
\ell_P([z])=m_w(Pz),\qquad d_{P,w}([z],[y])=m_w(P(z+y)).
```

这些量只依赖类，不依赖该类作为查询输入时的代表。
$`d_{P,w}`$ 是 $`H`$ 上的真度量：对称性来自二元加法，三角不等式来自线性性和质量三角不等式，
正权与核定理给出 $`d_{P,w}=0`$ 当且仅当两个类相同。在 $`Z`$ 上，它是同调等价关系对应的伪度量。

令 $`x=Pz`$、$`y'=Py`$，则共享支撑质量满足

```math
m_w(\mathrm{supp}\,x\cap\mathrm{supp}\,y')
=\frac{m_w(x)+m_w(y')-m_w(x+y')}2.
```

证明只需逐坐标计数：共有坐标在前两项各计一次，在 XOR 中抵消。
这里除以二是对质量进行的有理或实数运算。
共有部分解释组合代表的质量下降，输出支撑的并则表示这些代表共同占用的原坐标。

| 读取 | 数学意义 | 产品入口 |
| --- | --- | --- |
| 核与维数 | 每个类唯一的选定代表、Betti 数 | `kernel_basis`, `betti` |
| 选定质量 | 当前线性规则实现这个类的代价 | `selected_mass` |
| 类距离 | 差类的选定实现代价 | `class_distance` |
| 支撑与交/并 | 当前代表使用、共享、合并的原坐标 | `support`, `shared_support`, `union_support` |
| 最坏伸长 | 当前投影对所有循环的最大质量比 | `stretch` |

几何随截面、链基与权重变化。长度权得到长度，面积权得到所选链的面积；
链面积并不自动是包围区域的面积或空腔体积。
拓扑相同的输入可以产生不同几何输出，下一节给出可直接核算的实例。

## 6. 六边复形：完整算例

取四顶点完全图，只填充面 $`012`$。按边序 $`(01,02,03,12,13,23)`$ 赋权 $`(2,4,2,3,4,2)`$。
输入为

```math
A=\begin{pmatrix}
1&1&1&0&0&0\\1&0&0&1&1&0\\0&1&0&1&0&1\\0&0&1&0&1&1
\end{pmatrix},\qquad
D=\begin{pmatrix}1\\1\\0\\1\\0\\0\end{pmatrix}.
```

$`\dim Z=3`$，$`B=\langle b\rangle`$，$`b=01+02+12`$，故 $`\beta=2`$。
以 $`a=[013]`$、$`c=[023]`$ 为类基，每个类有两个代表。
四个截面给出如下全部可能输出，其中 $`X_0=01+03+13`$、$`Y_0=02+03+23`$：

| $`s(a)`$ | $`s(c)`$ | $`m(s(a)),m(s(c)),m(s(a+c))`$ | $`\Gamma`$ |
| --- | --- | --- | --- |
| $`X_0`$ | $`Y_0`$ | $`(8,8,12)`$ | $`4/3`$ |
| $`X_0`$ | $`Y_0+b`$ | $`(8,9,9)`$ | $`9/8`$ |
| $`X_0+b`$ | $`Y_0`$ | $`(13,8,9)`$ | $`13/8`$ |
| $`X_0+b`$ | $`Y_0+b`$ | $`(13,9,12)`$ | $`13/8`$ |

类的真正最短质量为 $`(8,8,9)`$。最小总质量基选两个质量八的代表，
但其组合质量十二。最小伸长截面选择第二行，让一个基输出多付一单位，
把组合质量从十二降到九；最坏比值由 $`4/3`$ 降为 $`9/8`$。
四行穷尽全部截面，因此最优性是精确结论。

当前默认并列规则下，`ExhaustiveExactSolver` 在这个窗口返回

```math
P_*=\begin{pmatrix}
0&0&0&0&1&1\\0&0&0&0&0&0\\0&0&0&0&1&1\\ 0&0&0&0&0&1\\0&0&0&0&1&0\\0&0&0&0&0&1
\end{pmatrix},\qquad L_*=I+P_*.
```

其核为 $`\{0,X,Y,X+Y\}`$，$`X=X_0`$、$`Y=Y_0+b=01+03+12+23`$。
同一个算子给出 Betti 数二、代表质量 $`(8,9,9)`$、两类距离九、共享支撑质量四、
总输出支撑质量十三以及 $`\Gamma=9/8`$。
[可运行的完整代码](guide/single-scale.md#六边复形的精确算子)逐项读取这些结果。

若边界矩阵保持不变而把全部权重改为一，三个非零类的最短质量均为三。
这三个三边代表之和是非零边界，无法同时作为线性截面的输出。
所以某个非零输出至少有四条边；取两个三边基代表达到 $`\Gamma_*=4/3`$。
两组权重有相同的同调和固定过滤 barcode，却有不同的最优伸长与质量。

## 7. 核之间的传输实现持久同调

给定有限有序过滤的窗口，$`J_{ij}`$ 为中间链空间的包含，三个次数的包含共同满足链映射条件。
在每个阶段独立构造合法的 $`P_i,L_i`$，记 $`\mathcal H_i=\ker L_i`$。
定义

```math
T_{ij}=P_jJ_{ij}|_{\mathcal H_i}.
```

**传输定理。** 若 $`f_{ij}:H_i\to H_j`$ 是原诱导同调映射，则

```math
T_{ij}=s_j f_{ij}q_i|_{\mathcal H_i},\qquad
q_jT_{ij}=f_{ij}q_i,\qquad T_{ii}=I,\qquad T_{j\ell}T_{ij}=T_{i\ell}.
```

**证明。** $`J_{ij}x`$ 对 $`x\in\mathcal H_i`$ 为循环，故
$`P_jJ_{ij}x=s_jq_jJ_{ij}x=s_jf_{ij}q_ix`$。
复合时 $`q_js_j=I`$，与 $`f_{j\ell}f_{ij}=f_{i\ell}`$ 一起给出复合律。
各 $`q_i|_{\mathcal H_i}`$ 为同构，所以得到的是整个持久同调模的同构。
阶段独立选代表是允许的，包含之后的目标投影保证传输落在目标核中。

因而

```math
\mathrm{rank}\,T_{ij}=\mathrm{rank}\,f_{ij}
=\dim(J_{ij}Z_i+B_j)-\dim B_j.
```

阶段 Betti 数不足以确定条形码：两个一维阶段之间的恒等和零映射有不同的存活行为。
这里保留完整映射。令 $`r(i,j)=\mathrm{rank}\,T_{ij}`$、$`r(-1,j)=0`$，阶段为 $`0,\ldots,N`$。
区间 $`[b,d)`$ 的重数为

```math
r(b,d-1)-r(b-1,d-1)-r(b,d)+r(b-1,d),
```

常量末端延拓下 $`[b,\infty)`$ 的重数为 $`r(b,N)-r(b-1,N)`$。
产品从相邻 transport 读取同一 rank invariant；完整 rank 表与历史区间基是显式查询。
重复尺度仍按阶段次序处理。

### 7.1 同一类的几何追踪

若权重由包含原样继承，则对 $`x\in\mathcal H_i`$，

```math
m_j(T_{ij}x)\le\Gamma_{w_j}(P_j)m_i(x).
```

因为 $`J_{ij}x`$ 是终点循环且质量不变，终点 stretch 的定义直接给出估计。
多步传输等于直达传输，界只需终点常数。
若权重改变，引入 $`\alpha_{ij}=\max_{\sigma\in C_{k,i}}w_j(\sigma)/w_i(\sigma)`$，
右边乘 $`\alpha_{ij}`$；源坐标为空时源空间为零，约定 $`\alpha_{ij}=1`$。
对 $`x+y`$ 应用同一估计还得到类距离的传输界。
死亡类给出零代表、零质量和空支撑；不同阶段同编号的任意核基向量不一定是同一个类。
实际追踪见 [过滤指南](guide/filtration.md)。

## 8. 比较条件、算术与当前实现

固定边界矩阵、原链基和投影，若 $`aw_i\le w_i'\le bw_i`$，$`0<a\le b`$，则

```math
\frac ab\Gamma_w(P)\le\Gamma_{w'}(P)\le\frac ba\Gamma_w(P),\qquad
\frac ab\Gamma_*(w)\le\Gamma_*(w')\le\frac ba\Gamma_*(w).
```

每个循环的分子、分母分别受 $`a,b`$ 倍控制；取最大值，再对相同可行集合取最小值即得。
统一缩放不改变 stretch，质量和距离则按比例缩放。
这一结论只比较固定链窗口的权重，不保证最优代表连续，也不涵盖重采样或网格变化。

同调基重编号保持上述类集合的含义；一般链基变换会改变 Hamming 质量和支撑。
结果的可比性需要固定链基、权重含义、并列规则及投影身份。

| 数学结论或计算 | 当前实现 |
| --- | --- |
| 构造与完整合法性 | Python/Rust 构造，独立 verifier 检查四项条件 |
| 核、代表、质量、距离、支撑 | 从当前存储的同一个 $`P`$ 读取 |
| 当前 $`\Gamma`$ | `stretch()` 在预算内完整枚举；耗尽单独表达 |
| 最优 $`\Gamma_*`$ | 支持域内的精确 solver 与独立最优证书 |
| 持久同调模与 barcode | `OperatorFamily` 的核传输与 rank invariant |
| 真正最短类质量 $`\mu_w`$ | 数学分析中定义；公共查询当前不可用 |

精确整数和有理权支持精确几何；浮点权下二元代数仍精确，但几何与最优值的精确性另行表达。
Rust 的 packed、Factorized 与 HC 表示实现同一作用；具体支持域见 [native 指南](guide/native.md)。
一般精确优化的规模、代表对输入变化的稳定性和下游应用收益，须分别建立证据。

## 9. 来源与进一步阅读

广义逆、线性分裂、有限域消元和有限单参数模的区间分解是本构造使用的既有数学工具。
本项目的算子定义、最小循环伸长目标及同一作用的联合读取，见上述固定理论来源。
与最短基、实循环空间投影和持久拉普拉斯有关的背景可从原文参考文献继续阅读：

- [Rossman, Subspace-Invariant AC0 Formulas, Lemma 5](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.ICALP.2017.93)：贪心回缩上界的背景。
- [Rathod, Fast Algorithms for Minimum Cycle Basis and Minimum Homology Basis](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.SoCG.2020.64)：最小基目标。
- [Dilworth, Kutzarova, Ostrovskii, Cycle Spaces: Invariant Projections and Applications to Transportation Cost](https://arxiv.org/abs/2305.12582)：实循环空间投影的背景。
- [Mémoli, Wan, Wang, Persistent Laplacians: Properties, Algorithms and Implications](https://doi.org/10.1137/21M1435471)：实数持久拉普拉斯及其核定理。

工程模块划分见 [架构](ARCHITECTURE.md)，调用与输入域见 [API](INTERFACE.md)，
六身份、精确性和恢复规则见 [结果模型](RESULT_MODEL.md)。
