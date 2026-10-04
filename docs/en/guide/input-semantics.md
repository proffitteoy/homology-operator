# Input semantics

[中文](../../guide/input-semantics.md)

## Input and arithmetic

A `ChainWindow` represents one fixed degree:

$$
C_{k+1}\xrightarrow{D}C_k\xrightarrow{A}C_{k-1},\qquad AD=0.
$$

`A` has shape m×n and `D` has shape n×p, using column vectors. Supply ordered,
unique nonempty basis identifiers for each space and n finite positive weights.
Empty spaces are supported. Invalid dimensions, bases, coordinates, weights, or
`AD≠0` raise `InvalidInput`, a `ValueError` subclass.

```python
from homology_operator import Matrix

matrix = Matrix.from_rows(((1, 1, 0), (0, 1, 1)))
assert matrix.kernel_basis() == ((1, 1, 1),)
assert matrix.solve((1, 0)) == (1, 0, 0)
assert Matrix.from_rows((), ncols=3) == Matrix.zero(0, 3)
```

Coordinates must be integer 0/1 values; booleans, floats, truncation, and implicit
reduction modulo 2 are rejected. `solve(b)` returns a deterministic solution with
free variables set to zero, or `None` when no solution exists. A valid empty
solution is `()`.

| `arithmetic` | Accepted weights | Geometry |
| --- | --- | --- |
| `ExactInteger` | Arbitrary-precision integers | Exact; objective ratios use `Fraction` |
| `ExactRational` (default) | Integers and `fractions.Fraction` | Exact rational arithmetic |
| `FloatingPoint` | Integers, floats, fractions converted to finite positive binary64 | Numerical `fsum`; no exact geometric optimality certificate |

The caller declares `weight_semantics` and `unit`. Positive costs do not imply
that weights are areas or volumes. Original coordinates determine geometry.
