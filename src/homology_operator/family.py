"""Finite coordinate filtrations of the same validated homology operators."""

from collections.abc import Mapping, Set
from dataclasses import dataclass, field
from fractions import Fraction
from math import isfinite
from types import MappingProxyType

from .algebra import Matrix
from .chain import ChainWindow, matrix_data, matrix_from_data
from .operator import HomologyOperator
from .result import OperatorResult, QueryResult, content_id, input_identity


def _ordered(value, name):
    if isinstance(value, (str, bytes, bytearray, Set, Mapping)):
        raise ValueError(f"{name} requires an ordered sequence")
    try:
        return tuple(value)
    except TypeError as error:
        raise ValueError(f"{name} requires an ordered sequence") from error


def _inclusion(source, target):
    positions = {label: index for index, label in enumerate(target)}
    if any(label not in positions for label in source):
        raise ValueError("filtration bases must include all preceding coordinates")
    return Matrix.from_columns(
        (
            tuple(int(row == positions[label]) for row in range(len(target)))
            for label in source
        ),
        nrows=len(target),
    )


@dataclass(frozen=True)
class OperatorFamily:
    """Ordered stages; repeated scales retain their distinct stage indices.

    Only coordinate inclusions are supported. The final stage extends constantly.
    Failed stages remain failed records, and are never interpreted as empty spaces.
    """

    scales: tuple
    windows: tuple
    operators: tuple
    weight_policy: str = "Inherited"
    duplicate_policy: str = "OrderedStages"
    terminal_extension: str = "Constant"
    _transports: dict = field(
        init=False, default_factory=dict, repr=False, compare=False
    )

    def __post_init__(self):
        scales = _ordered(self.scales, "scales")
        windows = _ordered(self.windows, "windows")
        operators = _ordered(self.operators, "operators")
        if not windows or len(scales) != len(windows) or len(operators) != len(windows):
            raise ValueError(
                "a finite family needs equally many nonempty stages, scales and windows"
            )
        if any(
            isinstance(x, bool)
            or not isinstance(x, (int, Fraction, float))
            or (isinstance(x, float) and not isfinite(x))
            for x in scales
        ):
            raise ValueError("scales must be finite numbers")
        if any(left > right for left, right in zip(scales, scales[1:])):
            raise ValueError("scales must be nondecreasing")
        if self.weight_policy not in ("Inherited", "Variable"):
            raise ValueError("unknown weight inheritance policy")
        if (
            self.duplicate_policy != "OrderedStages"
            or self.terminal_extension != "Constant"
        ):
            raise ValueError(
                "reference uses ordered duplicate stages and constant terminal extension"
            )
        if any(not isinstance(w, ChainWindow) for w in windows):
            raise ValueError("family inputs must be validated ChainWindows")
        if any(w.k != windows[0].k for w in windows):
            raise ValueError("all stages must have the same homological degree")
        for window, operator in zip(windows, operators):
            if isinstance(operator, HomologyOperator):
                if operator.window != window:
                    raise ValueError("stage operator input mismatch")
            elif (
                isinstance(operator, OperatorResult)
                and operator.status != "Ready"
                and operator.projection is None
            ):
                if operator.input_data != window:
                    raise ValueError("failure record must retain the stage input")
            else:
                raise ValueError(
                    "stages require validated operators or explicit failed records"
                )
        for source, target in zip(windows, windows[1:]):
            previous = _inclusion(source.basis_previous, target.basis_previous)
            current = _inclusion(source.basis_current, target.basis_current)
            following = _inclusion(source.basis_next, target.basis_next)
            if (
                target.A @ current != previous @ source.A
                or target.D @ following != current @ source.D
            ):
                raise ValueError(
                    "coordinate inclusions must commute with both boundary maps"
                )
            if (source.weight_semantics, source.unit) != (
                target.weight_semantics,
                target.unit,
            ):
                raise ValueError("weight semantics and units must agree across stages")
            if self.weight_policy == "Inherited":
                target_weights = dict(zip(target.basis_current, target.weights))
                if source.arithmetic != target.arithmetic or any(
                    target_weights[label] != weight
                    for label, weight in zip(source.basis_current, source.weights)
                ):
                    raise ValueError(
                        "Inherited weights must preserve each existing coordinate cost"
                    )
        object.__setattr__(self, "scales", scales)
        object.__setattr__(self, "windows", windows)
        object.__setattr__(self, "operators", operators)
        filtration_id = content_id(
            "filtration",
            {
                "scales": scales,
                "inputs": [input_identity(w) for w in windows],
                "weight_policy": self.weight_policy,
                "duplicate_policy": self.duplicate_policy,
                "terminal_extension": self.terminal_extension,
            },
        )
        identity = {
            "filtration_id": filtration_id,
            "operator_family_id": content_id(
                "family",
                {
                    "filtration_id": filtration_id,
                    "stages": [
                        {
                            "identity": op.identity,
                            "status": "Ready"
                            if isinstance(op, HomologyOperator)
                            else op.status,
                        }
                        for op in operators
                    ],
                },
            ),
        }
        object.__setattr__(self, "identity", MappingProxyType(identity))
        object.__setattr__(
            self,
            "status",
            "Ready"
            if all(isinstance(op, HomologyOperator) for op in operators)
            else "Partial",
        )

    def _index(self, index):
        if type(index) is not int or not 0 <= index < len(self.windows):
            raise ValueError("stage index is outside the finite filtration")
        return index

    def _interval(self, i, j):
        self._index(i)
        self._index(j)
        if i > j:
            raise ValueError("transport requires a forward interval")

    def stage(self, i):
        return self.operators[self._index(i)]

    def inclusion(self, i, j, degree=0):
        """Coordinate chain inclusion, also available for failed operator stages."""
        self._interval(i, j)
        if type(degree) is not int or degree not in (-1, 0, 1):
            raise ValueError("degree offset must be -1, 0 or 1")
        name = {-1: "basis_previous", 0: "basis_current", 1: "basis_next"}[degree]
        return _inclusion(
            getattr(self.windows[i], name), getattr(self.windows[j], name)
        )

    def _details(self, i, j):
        return {
            **self.identity,
            "source_stage": i,
            "target_stage": j,
            "source_scale": self.scales[i],
            "target_scale": self.scales[j],
            "source_identity": self.stage(i).identity,
            "target_identity": self.stage(j).identity,
        }

    def _query(self, state, value, i, j, exact=None, details=None):
        target = self.stage(j)
        identity = target.identity if isinstance(target, HomologyOperator) else None
        return QueryResult(
            state, value, identity, exact, {**self._details(i, j), **(details or {})}
        )

    def transport(self, i, j):
        """Exact action in source/target kernel coordinates, plus original-chain action."""
        self._interval(i, j)
        if (i, j) in self._transports:
            return self._transports[i, j]
        failed = [
            (index, self.stage(index).status)
            for index in dict.fromkeys((i, j))
            if not isinstance(self.stage(index), HomologyOperator)
        ]
        if failed:
            state = (
                "ResourceExhausted"
                if any(status == "ResourceExhausted" for _, status in failed)
                else "Unavailable"
            )
            return self._query(state, None, i, j, details={"failed_stages": failed})
        source, target = self.stage(i), self.stage(j)
        source_kernel = Matrix.from_columns(source.kernel_basis(), source.window.n)
        target_kernel = Matrix.from_columns(target.kernel_basis(), target.window.n)
        chain_action = target.P @ self.inclusion(i, j) @ source_kernel
        coordinates = []
        for column in chain_action.transpose().rows:
            value = target_kernel.solve(column)
            if value is None:
                raise ValueError("transport image is outside the target kernel")
            coordinates.append(value)
        action = Matrix.from_columns(coordinates, target.betti())
        result = self._query(
            "Computed",
            {
                "action": matrix_data(action),
                "chain_action": matrix_data(chain_action),
                "source_kernel_basis": source.kernel_basis(),
                "target_kernel_basis": target.kernel_basis(),
                "rank": action.rank(),
            },
            i,
            j,
            True,
        )
        self._transports[i, j] = result
        return result

    def transport_rank(self, i, j):
        result = self.transport(i, j)
        return self._query(
            result.state,
            result.value["rank"] if result.state == "Computed" else None,
            i,
            j,
            result.exact,
            result.details,
        )

    def transport_certificate(self, i, j):
        result = self.transport(i, j)
        if result.state != "Computed":
            return result
        source, target = self.stage(i), self.stage(j)
        action = matrix_from_data(result.value["action"])
        chain = matrix_from_data(result.value["chain_action"])
        source_kernel = Matrix.from_columns(source.kernel_basis(), source.window.n)
        differences = self.inclusion(i, j) @ source_kernel + chain
        quotient_preserved = all(
            target.window.D.solve(x) is not None for x in differences.transpose().rows
        )
        image_in_kernel = target.L @ chain == Matrix.zero(
            target.window.n, source.betti()
        )
        identity_verified = i != j or action == Matrix.identity(source.betti())
        for middle in range(i, j + 1):
            first, second = self.transport(i, middle), self.transport(middle, j)
            if first.state != "Computed" or second.state != "Computed":
                return self._query(
                    "Unavailable",
                    None,
                    i,
                    j,
                    details={"reason": "composition includes a failed stage"},
                )
            if (
                matrix_from_data(second.value["action"])
                @ matrix_from_data(first.value["action"])
                != action
            ):
                raise ValueError("transport composition failed")
        if not quotient_preserved or not image_in_kernel or not identity_verified:
            raise ValueError("transport validation failed")
        return self._query(
            "Computed",
            {
                "identity_verified": identity_verified,
                "composition_verified": True,
                "image_in_target_kernel": image_in_kernel,
                "induced_homology_map_verified": quotient_preserved,
            },
            i,
            j,
            True,
        )
