# Binary homology operators: definition, construction, and properties

[中文](../MATHEMATICS.md) · [Worked example and Python usage](guide/single-scale.md) · [Solver contract](SOLVER_CONTRACT.md)

`homology-operator` implements a binary homology operator constructed directly
from boundary data. The mathematical object is a linear operator $L=I+P$ on the
original chain space. Its kernel realizes homology, and the accompanying
projection $P$ chooses one cycle representative per class in a linear manner.
Positive coordinate weights turn the same action into representative mass,
class distance, shared support, and worst stretch. Across a filtration, projected
transport between kernels realizes the entire persistence module.

This page gives definitions, proofs, and their correspondence with the product.
They apply in any fixed degree of a finite based binary chain window.
The theory source is [D1, T1–T4, and E4 at the pinned revision](https://github.com/proffitteoy/homology-operator-lab/blob/6143729669902ee875b211b58085e954c76cdf88/docs/proof/PROOF.md).
The arguments and example needed to understand the product are given here;
installing the research repository is unnecessary.

## 1. Input and mathematical objects

Let

$$
C_{k+1}=\mathbf F_2^p\xrightarrow{D}
C=C_k=\mathbf F_2^n\xrightarrow{A}\mathbf F_2^m=C_{k-1},\qquad AD=0.
$$

Matrices act on column vectors: $A$ is $m\times n$ and $D$ is $n\times p$.
Chain arithmetic is over $\mathbf F_2$, where addition is XOR and subtraction
coincides with addition. All three spaces have fixed ordered bases; coordinates
of the middle space have strictly positive weights $w_i>0$.

Write

$$
Z=\ker A,\qquad B=\operatorname{im}D\subseteq Z,\qquad
H=Z/B,\qquad q:Z\to H.
$$

The degree-$k$ Betti number is

$$
\beta=\dim H=n-\operatorname{rank}A-\operatorname{rank}D.
$$

The weighted mass of a chain is

$$
m_w(x)=\sum_{i:x_i=1}w_i.
$$

It is strictly positive on nonzero chains and satisfies
$m_w(x+y)\le m_w(x)+m_w(y)$. Unit weights count active coordinates.
Length, area, volume, or cost interpretations must be supplied with the input.
Changing degree changes this interpretation, without changing the construction.

## 2. Definition of the projection and operator

**Definition.** A legal homology projection is a linear map $P:C\to C$ satisfying

$$
P^2=P,\qquad AP=0,\qquad PD=0,\qquad
z+Pz\in B\quad\text{for every }z\in Z.
$$

The corresponding **binary homology operator** is

$$
\boxed{L=I+P.}
$$

Idempotence makes the choice stable after one application; $AP=0$ makes outputs
cycles; $PD=0$ kills boundaries; the last condition changes a cycle only by a
boundary, preserving its class. The last condition is essential: if $H\ne0$,
the zero projection satisfies the first three while discarding all nonzero classes.

`HomologyOperator.P` and `.L` represent these maps. `project(x)` returns $Px$;
`apply_operator(x)` returns $Lx$. On a cycle, the one-step update

$$
z+Lz=Pz
$$

returns the selected representative in the same class. Raw action is defined on
all chains; the class interpretation applies to cycles.

### 2.1 Construction from boundary matrices

Choose algebraic generalized inverses

$$
G:\mathbf F_2^m\to C,\quad AGA=A,\qquad
U:C\to\mathbf F_2^p,\quad DUD=D.
$$

They always exist: choose linear preimages on the image of the matrix and extend
to its full target space. Finite-field elimination implements this choice. Define

$$
R=I+GA,\qquad Q=I+DU,\qquad
\boxed{P=QR=(I+DU)(I+GA)},\qquad L=I+P.
$$

$R$ retracts arbitrary chains to cycles; $Q$ removes boundary directions within
cycles; $P$ selects a representative in the original coordinates. The constructor
requires $A,D,w$. The quotient $H$ and map $q$ explain the construction and need
not be supplied as a precomputed homology basis.

**Proof of legality.** The generalized-inverse relations imply

$$
AR=0,\quad R^2=R,\quad R|_Z=I_Z,\qquad
Q^2=Q,\quad QD=0,\quad AQ=A.
$$

Since $QRx$ is a cycle, $RQR=QR$ and $P^2=QRQR=Q^2R=P$.
Also $RD=D$, giving $PD=QD=0$, and $AP=AQR=AR=0$.
For a cycle $z$, $Pz=Qz=z+DUz$, so $z+Pz\in B$. All four conditions hold.

## 3. The kernel realizes homology

**Kernel theorem.** Every legal projection and its operator satisfy

$$
L^2=L,\qquad\ker L=\operatorname{im}P\subseteq Z,\qquad
q|_{\ker L}:\ker L\xrightarrow{\cong}H.
$$

Consequently,

$$
\dim\ker L=\beta,\qquad
Pz=0\iff z\in B\quad(z\in Z),\qquad
Pz=Py\iff z+y\in B\quad(z,y\in Z).
$$

**Proof.** Characteristic two and $P^2=P$ yield $L^2=I+P=L$.
If $x=Py$, then $Lx=Py+P^2y=0$; if $Lx=0$, then $x=Px$.
Thus $\ker L=\operatorname{im}P$, which lies in $Z$ because $AP=0$.

For $h=qz$, define $s(h)=Pz$. If $qz=qy$, their difference is a boundary,
and $PD=0$ gives $Pz=Py$. Hence $s$ is well defined and linear.
Class preservation gives $qs(h)=qPz=qz=h$, so $qs=I_H$.
For a kernel vector, $x=Px=s(qx)$; therefore $s$ is the inverse of the restricted
quotient map. Every class has exactly one kernel representative. This proves the
isomorphism and the stated equivalence tests.

The kernel contains actual cycle representatives. It has $2^\beta$ vectors;
its cardinality and its dimension $\beta$ are different quantities.

### 3.1 Spectrum and source of information

Idempotence gives a direct sum

$$
C=\operatorname{im}P\oplus\ker P.
$$

$L$ is zero on the first summand and the identity on the second, so

$$
\chi_L(\lambda)=\lambda^\beta(\lambda+1)^{n-\beta}.
$$

The eigenvalues are only $0,1$. Geometric information comes from weighted action
and selected representatives in the original coordinates. Real inner-product
Hodge positivity does not transfer directly to $\mathbf F_2$: a single edge has
boundary $d=(1,1)^\mathsf T$ with $d^\mathsf T d=0$, although its first homology
is zero. The four conditions above establish the required kernel correspondence.

## 4. Linear representative selection and minimum stretch

The kernel theorem implies

$$
P|_Z=sq,\qquad s:H\to Z,\quad qs=I_H.
$$

$s$ is a **linear section** of the quotient. Its requirement
$s(h+g)=s(h)+s(g)$ couples representative choices. Individually shortest basis
representatives need not have a short sum.

### 4.1 All projections for a fixed retraction

Fix $R$ as above. For any section $s$, the map $T(z)=z+sqz$ retracts $Z$ onto $B$.
Choose a linear right inverse of $D$ on $B$, lift $T$ to $U_Z$, then extend it to
$C$. This gives $DU|_Z=T$, $DUD=D$, and $QR=sqR$.
The generalized-inverse construction thus covers **every** cycle section; on all
chains it covers the extensions compatible with the fixed $R$.

Set $r=\dim B$ and choose one section $s_0$. All sections and projections are

$$
s=s_0+t,\quad t\in\operatorname{Hom}_{\mathbf F_2}(H,B),\qquad
\Omega_R=\{(s_0+t)qR:t\in\operatorname{Hom}(H,B)\}.
$$

This affine space has dimension $r\beta$ and exactly $2^{r\beta}$ projections.
For $P,Q\in\Omega_R$,

$$
PQ=P,\qquad QP=Q,\qquad(P+Q)^2=0.
$$

For example, $PQ=sqR\,s'qR=sqR$, since $R|_Z=I$ and $qs'=I$.
These identities describe the space of choices. Representatives, supports, and
masses can still differ between its members.

### 4.2 Worst expansion on cycles

Define

$$
\Gamma_w(P)=\max_{0\ne z\in Z}\frac{m_w(Pz)}{m_w(z)},\qquad
\Gamma_*=\min_{P\ \mathrm{legal}}\Gamma_w(P).
$$

Finiteness guarantees an attained minimum. A fixed $R$ already covers all cycle
sections, so the optimal cycle objective is independent of $G$. Noncycle action
and tie selection can still depend on $R$. A minimum-stretch operator is
$L_*=I+P_*$ for a minimizing projection.

For analysis, define true minimum class mass

$$
\mu_w(h)=\min\{m_w(z):z\in Z,\ qz=h\}.
$$

**Section equivalence theorem.** For $\beta>0$,

$$
\boxed{\Gamma_w(P)=\max_{0\ne h\in H}\frac{m_w(sh)}{\mu_w(h)}}.
$$

**Proof.** Every cycle in one class has the same output $sh$, so that class's
largest output/input ratio occurs at a minimum-mass input. Boundary inputs give
zero. Taking the maximum over classes proves the identity, including the role
of all linear combinations in the objective.

$\mu_w$ is an analysis quantity here; the public `minimum_class_mass()` query
currently returns `Unavailable`. Solvers and `stretch()` can enumerate cycle
ratios directly without this query. If $Z=0$, stretch is declared zero with
`EmptyDomain`; if $Z\ne0$ but $H=0$, cycle projection is zero and stretch is a
legitimate `Computed` zero.

### 4.3 Universal bounds and computational cost

For $\beta>0$,

$$
1\le\Gamma_*\le\beta.
$$

The lower bound holds because $sh$ represents $h$. For the upper bound, greedily
choose a minimum-mass cycle $z_i$ whose class is outside the span of preceding
classes. The chosen masses are nondecreasing. For
$h=\sum_i a_i qz_i$, let $j$ be the largest active index. A shortest representative
of $h$ is a candidate at step $j$, hence

$$
m_w(z_i)\le m_w(z_j)\le\mu_w(h)\quad(i\le j),\qquad
m_w(sh)\le\sum_{a_i=1}m_w(z_i)\le\beta\mu_w(h).
$$

This proves the bound; it does not provide a polynomial-time general optimizer.
Full cycle evaluation has $2^{\dim Z}-1$ nonzero inputs; a full section search
for fixed $R$ has $2^{r\beta}$ candidates. The exhaustive, greedy, rank-two, and
structured solvers have distinct domains and budgets in the [solver contract](SOLVER_CONTRACT.md).
The default `FeasibleSolver` constructs a legal operator. `ExactOptimal` requires
an independently validated optimality certificate.

## 5. Geometry from the same action

For cycles $z,y$, define

$$
\ell_P([z])=m_w(Pz),\qquad d_{P,w}([z],[y])=m_w(P(z+y)).
$$

These depend on classes rather than their query-input representatives.
$d_{P,w}$ is a metric on $H$: symmetry follows from binary addition; the triangle
inequality follows from linearity and the mass triangle inequality; positive
weights and the kernel theorem give zero distance exactly for equal classes.
On $Z$, it is a pseudometric whose zero relation is homology equivalence.

For $x=Pz$ and $y'=Py$, shared support mass is

$$
m_w(\operatorname{supp}x\cap\operatorname{supp}y')
=\frac{m_w(x)+m_w(y')-m_w(x+y')}2.
$$

Each shared coordinate is counted twice in the first two terms and cancels in
XOR. Division by two is in rational or real mass arithmetic. Shared coordinates
explain reduced mass of a combined representative; the support union describes
the original coordinates occupied collectively.

| Readout | Meaning | Product entry point |
| --- | --- | --- |
| Kernel and dimension | Unique selected representatives, Betti number | `kernel_basis`, `betti` |
| Selected mass | Cost of realizing a class under the current linear rule | `selected_mass` |
| Class distance | Cost of the selected difference-class representative | `class_distance` |
| Support, intersection, union | Used, shared, and combined original coordinates | `support`, `shared_support`, `union_support` |
| Worst stretch | Current projection's maximum cycle mass ratio | `stretch` |

Geometry depends on the section, chain basis, and weights. Length weights give
length; area weights give selected chain area, which need not be enclosed area
or cavity volume. Inputs with identical homology can have different geometry,
as the following example demonstrates.

## 6. A complete six-edge example

Take the complete graph on four vertices and fill only face $012$. In edge order
$(01,02,03,12,13,23)$, use weights $(2,4,2,3,4,2)$. The boundaries are

$$
A=\begin{pmatrix}
1&1&1&0&0&0\\1&0&0&1&1&0\\0&1&0&1&0&1\\0&0&1&0&1&1
\end{pmatrix},\qquad
D=\begin{pmatrix}1\\1\\0\\1\\0\\0\end{pmatrix}.
$$

$\dim Z=3$, $B=\langle b\rangle$ for $b=01+02+12$, and $\beta=2$.
Use classes $a=[013]$, $c=[023]$. Each class has two representatives.
With $X_0=01+03+13$ and $Y_0=02+03+23$, the four sections are exhausted by

| $s(a)$ | $s(c)$ | $m(s(a)),m(s(c)),m(s(a+c))$ | $\Gamma$ |
| --- | --- | --- | --- |
| $X_0$ | $Y_0$ | $(8,8,12)$ | $4/3$ |
| $X_0$ | $Y_0+b$ | $(8,9,9)$ | $9/8$ |
| $X_0+b$ | $Y_0$ | $(13,8,9)$ | $13/8$ |
| $X_0+b$ | $Y_0+b$ | $(13,9,12)$ | $13/8$ |

True minimum class masses are $(8,8,9)$. The minimum-total-mass basis uses the
two mass-eight representatives but their sum costs twelve. The minimum-stretch
section uses the second row: one extra unit for a basis output reduces the sum
from twelve to nine, taking worst stretch from $4/3$ to $9/8$.
Exhausting all four sections proves optimality exactly.

With the current default tie rule, `ExhaustiveExactSolver` returns

$$
P_*=\begin{pmatrix}
0&0&0&0&1&1\\0&0&0&0&0&0\\0&0&0&0&1&1\\
0&0&0&0&0&1\\0&0&0&0&1&0\\0&0&0&0&0&1
\end{pmatrix},\qquad L_*=I+P_*.
$$

Its kernel is $\{0,X,Y,X+Y\}$ with $X=X_0$ and $Y=Y_0+b=01+03+12+23$.
The same operator yields Betti number two, representative masses $(8,9,9)$,
class distance nine, shared support mass four, total output support mass thirteen,
and $\Gamma=9/8$. The [runnable code](guide/single-scale.md#an-exact-operator-on-the-six-edge-complex)
reads each value from the current product.

Keep the boundaries and change all weights to one. The three minimum nonzero
class masses are now three. Those three triangles sum to the nonzero boundary,
so they cannot all be outputs of a linear section. Some output therefore has at
least four edges; selecting two triangles attains $\Gamma_*=4/3$.
Homology and the barcode of a fixed filtration remain the same, while optimal
stretch and masses change.

## 7. Kernel transport realizes persistent homology

For a finite ordered filtration, let $J_{ij}$ be the middle-degree inclusion;
inclusions in all three degrees satisfy the chain-map conditions. Independently
construct legal $P_i,L_i$ at each stage and set $\mathcal H_i=\ker L_i$. Define

$$
T_{ij}=P_jJ_{ij}|_{\mathcal H_i}.
$$

**Transport theorem.** If $f_{ij}:H_i\to H_j$ is the induced homology map, then

$$
T_{ij}=s_j f_{ij}q_i|_{\mathcal H_i},\qquad
q_jT_{ij}=f_{ij}q_i,\qquad T_{ii}=I,\qquad T_{j\ell}T_{ij}=T_{i\ell}.
$$

**Proof.** For $x\in\mathcal H_i$, $J_{ij}x$ is a cycle and
$P_jJ_{ij}x=s_jq_jJ_{ij}x=s_jf_{ij}q_ix$.
Composition uses $q_js_j=I$ and $f_{j\ell}f_{ij}=f_{i\ell}$.
Each restricted $q_i$ is an isomorphism, giving an isomorphism of whole
persistence modules. Independent section choices are permitted; projection at
the target ensures the transported representative belongs to the target kernel.

In particular,

$$
\operatorname{rank}T_{ij}=\operatorname{rank}f_{ij}
=\dim(J_{ij}Z_i+B_j)-\dim B_j.
$$

Stage Betti numbers alone do not determine a barcode: identity and zero maps
between two one-dimensional stages have different survival behavior.
Here the full maps are retained. For stages $0,\ldots,N$, set
$r(i,j)=\operatorname{rank}T_{ij}$ and $r(-1,j)=0$. The multiplicity of $[b,d)$ is

$$
r(b,d-1)-r(b-1,d-1)-r(b,d)+r(b-1,d),
$$

and under constant terminal extension the multiplicity of $[b,\infty)$ is
$r(b,N)-r(b-1,N)$. The product reads the same rank invariant through adjacent
transport; the full rank table and historical interval basis are explicit queries.
Repeated scales retain stage order.

### 7.1 Tracking geometry of the same class

When inclusions inherit weights, for $x\in\mathcal H_i$,

$$
m_j(T_{ij}x)\le\Gamma_{w_j}(P_j)m_i(x).
$$

$J_{ij}x$ is a target cycle with unchanged mass, so the target stretch definition
proves the inequality directly. Multistep transport equals direct transport,
requiring only the endpoint constant. If weights change, multiply the right
side by $\alpha_{ij}=\max_{\sigma\in C_{k,i}}w_j(\sigma)/w_i(\sigma)$;
for an empty source coordinate set take $\alpha_{ij}=1$, since the source is zero.
Applying the bound to $x+y$ gives the corresponding distance bound.
A dead class has zero representative, mass, and support. Arbitrary kernel basis
vectors with matching indices across stages need not describe the same class.
See the [filtration guide](guide/filtration.md) for actual tracking calls.

## 8. Comparison conditions, arithmetic, and implementation

For fixed boundaries, original basis, and projection, if
$aw_i\le w_i'\le bw_i$ with $0<a\le b$, then

$$
\frac ab\Gamma_w(P)\le\Gamma_{w'}(P)\le\frac ba\Gamma_w(P),\qquad
\frac ab\Gamma_*(w)\le\Gamma_*(w')\le\frac ba\Gamma_*(w).
$$

Each ratio has numerator and denominator bounded by the respective mass factors;
take the cycle maximum and then the minimum over the same feasible set.
Uniform scaling preserves stretch and scales masses and distances.
This comparison concerns weights on a fixed window. It does not ensure
continuity of selected optimal representatives or cover resampling or remeshing.

A homology-coordinate relabeling preserves the set of classes. A general chain
basis change can alter Hamming mass and support. Comparability requires fixed
chain coordinates, weight meanings, tie rules, and projection identity.

| Mathematical fact or calculation | Current implementation |
| --- | --- |
| Construction and full legality | Python/Rust construction; independent verification of all four conditions |
| Kernel, representatives, mass, distance, support | Read from the same stored $P$ |
| Current $\Gamma$ | Complete `stretch()` enumeration within a budget; exhaustion is distinct |
| Optimal $\Gamma_*$ | Exact solvers in their supported domains with independent certificates |
| Persistence module and barcode | `OperatorFamily` kernel transport and rank invariant |
| True minimum class mass $\mu_w$ | Defined for analysis; the public query is currently unavailable |

Integer and rational weights support exact geometry. Binary algebra stays exact
with floating weights, while geometric and optimality precision are reported
separately. Rust packed, Factorized, and HC representations implement the same
action; supported domains are in the [native guide](guide/native.md).
General exact optimization scale, stability of representatives under input
changes, and downstream application benefits each require their own evidence.

## 9. Sources and further reading

Generalized inverses, linear splittings, finite-field elimination, and interval
decomposition of finite one-parameter modules are established tools used in
this construction. The operator definition, minimum cycle stretch objective,
and joint readouts of one action are given in the pinned theory source above.
Its references provide background on greedy bounds, shortest bases, real cycle
projections, and persistent Laplacians:

- [Rossman, Subspace-Invariant AC0 Formulas, Lemma 5](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.ICALP.2017.93).
- [Rathod, Fast Algorithms for Minimum Cycle Basis and Minimum Homology Basis](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.SoCG.2020.64).
- [Dilworth, Kutzarova, Ostrovskii, Cycle Spaces: Invariant Projections and Applications to Transportation Cost](https://arxiv.org/abs/2305.12582).
- [Mémoli, Wan, Wang, Persistent Laplacians: Properties, Algorithms and Implications](https://doi.org/10.1137/21M1435471).

Module responsibilities are in [architecture](ARCHITECTURE.md), calls and input
domains in the [API](INTERFACE.md), and identities, precision, and recovery in
the [result model](RESULT_MODEL.md).
