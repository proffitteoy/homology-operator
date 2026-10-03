"""Finite coordinate filtrations of the same validated homology operators."""

from collections.abc import Mapping, Set
from collections import OrderedDict, Counter
from dataclasses import dataclass, field
from fractions import Fraction
from math import isfinite
import json
from types import MappingProxyType

from .algebra import Matrix
from .chain import ChainWindow, matrix_data, matrix_from_data, _thaw_metadata
from .operator import HomologyOperator, THEORY_REVISION
from .result import (
    OperatorResult,
    QueryResult,
    content_id,
    input_identity,
    _encode,
    _decode,
    _freeze,
    canonical_json,
)


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


def _pack(vector):
    return sum(bit << i for i, bit in enumerate(vector))


def _unpack(vector, size):
    return tuple((vector >> i) & 1 for i in range(size))


def _insert(pivots, vector, combination):
    """Reduce a packed column, retaining its expression in accepted columns."""
    while vector:
        pivot = vector.bit_length() - 1
        if pivot not in pivots:
            pivots[pivot] = (vector, combination)
            return True, combination
        other, coefficients = pivots[pivot]
        vector ^= other
        combination ^= coefficients
    return False, combination


def _adjacent_intervals(dimensions, maps, histories=False):
    """Birth-prefix elimination; optional backward corrections of dying vectors.

    Maps are packed columns in the *same family's* kernel coordinates. The
    proof and historical basis correction are in docs/S4_FILTRATION.md.
    """
    alive = [(0, 1 << i, [1 << i] if histories else None) for i in range(dimensions[0])]
    ended = []
    for stage, columns in enumerate(maps, 1):
        pivots, following = {}, []
        for birth, vector, history in alive:
            image = 0
            for i, column in enumerate(columns):
                if vector >> i & 1:
                    image ^= column
            independent, combination = _insert(pivots, image, 1 << len(following))
            if independent:
                following.append(
                    (birth, image, history + [image] if histories else None)
                )
            else:
                if histories:
                    history = list(history)
                    for i, (older_birth, _, older_history) in enumerate(following):
                        if combination >> i & 1:
                            for s in range(birth, stage):
                                history[s - birth] ^= older_history[s - older_birth]
                ended.append((birth, stage, history))
        for i in range(dimensions[stage]):
            vector = 1 << i
            if _insert(pivots, vector, 1 << len(following))[0]:
                following.append((stage, vector, [vector] if histories else None))
        if len(following) != dimensions[stage]:
            raise ValueError("adjacent transport basis does not span its target")
        alive = following
    ended.extend((birth, None, history) for birth, _, history in alive)
    return sorted(
        ended, key=lambda bar: (bar[0], len(dimensions) if bar[1] is None else bar[1])
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
    cache_limit: int = 64
    _transports: dict = field(
        init=False, default_factory=OrderedDict, repr=False, compare=False
    )

    _actions: dict = field(
        init=False, default_factory=OrderedDict, repr=False, compare=False
    )
    _ranks: dict = field(
        init=False, default_factory=OrderedDict, repr=False, compare=False
    )
    _kernels: dict = field(init=False, default_factory=dict, repr=False, compare=False)
    _barcode_basis: object = field(init=False, default=None, repr=False, compare=False)
    _schema_version: int = field(init=False, default=2, repr=False, compare=False)

    _tracking: dict = field(init=False, default_factory=dict, repr=False, compare=False)

    def __post_init__(self):
        if type(self.cache_limit) is not int or self.cache_limit < 0:
            raise ValueError("cache_limit must be a nonnegative integer")
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
        basis_names = ("basis_previous", "basis_current", "basis_next")
        positions = tuple(
            {label: i for i, label in enumerate(getattr(windows[-1], name))}
            for name in basis_names
        )
        try:
            active = tuple(
                tuple(
                    tuple(pos[label] for label in getattr(w, name))
                    for pos, name in zip(positions, basis_names)
                )
                for w in windows
            )
        except KeyError as error:
            raise ValueError(
                "filtration bases must include all preceding coordinates"
            ) from error
        object.__setattr__(self, "_active", active)
        for stage, (source, target) in enumerate(zip(windows, windows[1:])):
            indices = []
            for degree in range(3):
                locations = {
                    value: i for i, value in enumerate(active[stage + 1][degree])
                }
                try:
                    indices.append(
                        tuple(locations[value] for value in active[stage][degree])
                    )
                except KeyError as error:
                    raise ValueError(
                        "filtration bases must include all preceding coordinates"
                    ) from error
            for left, right, rows, columns in (
                (source.A, target.A, indices[0], indices[1]),
                (source.D, target.D, indices[1], indices[2]),
            ):
                row_locations = {target_row: row for row, target_row in enumerate(rows)}
                if any(
                    right.rows[r][target_column]
                    != (
                        left.rows[row_locations[r]][column] if r in row_locations else 0
                    )
                    for column, target_column in enumerate(columns)
                    for r in range(right.nrows)
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

    def _indices(self, i, j, degree=1):
        positions = {
            value: index for index, value in enumerate(self._active[j][degree])
        }
        return tuple(positions[value] for value in self._active[i][degree])

    def _embed(self, vector, indices, size):
        result = [0] * size
        for bit, index in zip(vector, indices):
            result[index] = bit
        return tuple(result)

    def _kernel(self, i):
        operator = self.stage(i)
        key = operator.identity["projection_id"]
        if key not in self._kernels:
            # Family-owned workspace never changes the existing operator's caches.
            basis = operator.L.kernel_basis()
            pivots = {}
            for column, vector in enumerate(basis):
                if not _insert(pivots, _pack(vector), 1 << column)[0]:
                    raise ValueError("stage kernel basis is dependent")
            self._kernels[key] = (basis, pivots)
        return self._kernels[key]

    def _solve_many(self, i, vectors):
        basis, pivots = self._kernel(i)
        result = []
        for vector in vectors:
            residual, coordinates = _pack(vector), 0
            while residual:
                pivot = residual.bit_length() - 1
                if pivot not in pivots:
                    raise ValueError("transport image is outside the target kernel")
                column, coefficients = pivots[pivot]
                residual ^= column
                coordinates ^= coefficients
            result.append(_unpack(coordinates, len(basis)))
        return tuple(result)

    def _cached(self, cache, key, value):
        if self.cache_limit:
            cache[key] = value
            cache.move_to_end(key)
            while len(cache) > self.cache_limit:
                cache.popitem(last=False)
        return value

    def _failure(self, i, j):
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
        return None

    def _coordinate_action(self, i, j):
        key = (i, j)
        if key in self._actions:
            self._actions.move_to_end(key)
            return self._actions[key]
        source_basis = self._kernel(i)[0]
        if i == j:
            action = Matrix.identity(len(source_basis))
        else:
            target = self.stage(j)
            indices = self._indices(i, j)
            projected = tuple(
                target.P.apply(self._embed(x, indices, target.window.n))
                for x in source_basis
            )
            action = Matrix.from_columns(
                self._solve_many(j, projected), len(self._kernel(j)[0])
            )
        return self._cached(self._actions, key, action)

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
            self._transports.move_to_end((i, j))
            return self._transports[i, j]
        failure = self._failure(i, j)
        if failure is not None:
            return self._cached(self._transports, (i, j), failure)
        target = self.stage(j)
        action = self._coordinate_action(i, j)
        target_kernel = Matrix.from_columns(self._kernel(j)[0], target.window.n)
        chain_action = target_kernel @ action
        result = self._query(
            "Computed",
            {
                "action": matrix_data(action),
                "chain_action": matrix_data(chain_action),
                "source_kernel_basis": self._kernel(i)[0],
                "target_kernel_basis": self._kernel(j)[0],
                "rank": action.rank(),
            },
            i,
            j,
            True,
        )
        return self._cached(self._transports, (i, j), result)

    def transport_rank(self, i, j):
        self._interval(i, j)
        if (i, j) in self._ranks:
            self._ranks.move_to_end((i, j))
            return self._ranks[i, j]
        result = self._failure(i, j)
        if result is None:
            result = self._query(
                "Computed", self._coordinate_action(i, j).rank(), i, j, True
            )
        return self._cached(self._ranks, (i, j), result)

    def rank_table(self):
        """Explicit quadratic rank output; does not retain all chain actions."""
        values = {}
        last = len(self.windows) - 1
        for i in range(last + 1):
            for j in range(i, last + 1):
                rank = self.transport_rank(i, j)
                if rank.state != "Computed":
                    return self._query(
                        rank.state, None, 0, last, details={"failed_interval": (i, j)}
                    )
                values[f"{i}:{j}"] = rank.value
        return self._query("Computed", values, 0, last, True)

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

    def to_result(self, schema_version=None):
        """Immutable snapshot; serialization revalidates persisted derived readouts."""
        barcode = self.barcode()
        version = self._schema_version if schema_version is None else schema_version
        if type(version) is not int or version not in (1, 2):
            raise ValueError("unsupported family result schema")
        stage_results = [
            (op.to_result() if isinstance(op, HomologyOperator) else op).to_dict()
            for op in self.operators
        ]
        ranks = dict(self._ranks)
        for (i, j), result in self._transports.items():
            ranks[i, j] = self._query(
                result.state,
                result.value["rank"] if result.state == "Computed" else None,
                i,
                j,
                result.exact,
                result.details,
            )
        data = {
            "schema_version": version,
            "identity": dict(self.identity),
            "status": self.status,
            "scales": _encode(self.scales),
            "windows": [w.to_dict() for w in self.windows],
            "stage_results": stage_results,
            "weight_policy": self.weight_policy,
            "duplicate_policy": self.duplicate_policy,
            "terminal_extension": self.terminal_extension,
            "transports": {
                f"{i}:{j}": result.to_dict()
                for (i, j), result in self._transports.items()
            },
            "rank_readout": {
                f"{i}:{j}": result.to_dict() for (i, j), result in ranks.items()
            },
            "barcode_readout": barcode.to_dict(),
            "tracking_readout": {
                key: query.to_dict() for key, query in self._tracking.items()
            },
            "provenance": {
                "rank_invariant_source": "operator_family",
                "oracle_used_for_result": False,
                "theory_revision": THEORY_REVISION,
            },
        }
        if version == 2:
            data["windows"] = _compact_windows(self)
            for i, record in enumerate(stage_results):
                del record["input_data"]
                record["input_ref"] = i
            data["barcode_basis_readout"] = (
                self._barcode_basis
                or self._query("NotComputed", None, 0, len(self.windows) - 1)
            ).to_dict()
        return OperatorFamilyResult(data)

    def _remember(self, name, arguments, i, j, result):
        query = self._query(
            result.state,
            result.value,
            i,
            j,
            result.exact,
            {**result.details, "query": name, "arguments": arguments},
        )
        self._tracking[content_id(name, (arguments, i, j))] = query
        return query

    def track_class(self, x, i, j):
        """Transport a source cycle to the representative selected by the target P."""
        self._interval(i, j)
        from .algebra import validate_vector

        x = validate_vector(x, self.windows[i].n)
        if self.windows[i].A.apply(x) != (0,) * self.windows[i].m:
            raise ValueError("class tracking requires a source cycle")
        failure = self._failure(i, j)
        if failure is not None:
            result = failure
        else:
            source = self.stage(i)
            target = self.stage(j)
            value = target.P.apply(
                self._embed(source.project(x), self._indices(i, j), target.window.n)
            )
            result = self._query("Computed", value, i, j, True)
        return self._remember("track_class", (x,), i, j, result)

    def _track_geometry(self, name, arguments, i, j):
        arguments = tuple(tuple(x) for x in arguments)
        chains = [self.track_class(x, i, j) for x in arguments]
        missing = next((x for x in chains if x.state != "Computed"), None)
        if missing is not None:
            result = self._query(missing.state, None, i, j, details=missing.details)
        else:
            target = self.stage(j)
            try:
                supports = [
                    tuple(i for i, bit in enumerate(x.value) if bit) for x in chains
                ]
                if name == "selected_mass":
                    value = target._mass(chains[0].value)
                elif name == "support":
                    value = supports[0]
                elif name == "shared_support":
                    value = tuple(sorted(set(supports[0]) & set(supports[1])))
                else:
                    value = tuple(sorted(set(supports[0]) | set(supports[1])))
            except ValueError as error:
                if name != "selected_mass" or not str(error).startswith(
                    "NumericalFailure"
                ):
                    raise
                result = self._query(
                    "Unavailable",
                    None,
                    i,
                    j,
                    details={"reason": "NumericalFailure", "diagnostic": str(error)},
                )
                return self._remember("track_mass", arguments, i, j, result)
            result = self._query(
                "Computed",
                value,
                i,
                j,
                name != "selected_mass" or target.window.arithmetic != "FloatingPoint",
                {
                    "weight_policy": self.weight_policy,
                    "coordinate_labels": target.window.basis_current,
                    "arithmetic_policy": target.window.arithmetic,
                },
            )
        public_name = {
            "selected_mass": "track_mass",
            "support": "track_support",
            "shared_support": "track_shared_support",
            "union_support": "track_union_support",
        }[name]
        return self._remember(public_name, arguments, i, j, result)

    def track_mass(self, x, i, j):
        return self._track_geometry("selected_mass", (x,), i, j)

    def track_support(self, x, i, j):
        return self._track_geometry("support", (x,), i, j)

    def track_shared_support(self, x, y, i, j):
        return self._track_geometry("shared_support", (x, y), i, j)

    def track_union_support(self, x, y, i, j):
        return self._track_geometry("union_support", (x, y), i, j)

    def endpoint_mass_bound(self, x, i, j, limits=None):
        """One endpoint stretch times the explicit weight-change factor.

        Floating results are numerical observations, not certified bounds.
        """
        x = tuple(x)
        tracked = self.track_class(x, i, j)
        if tracked.state != "Computed":
            return tracked
        source, target = self.stage(i), self.stage(j)
        stretch = target.stretch(limits)
        if stretch.state not in ("Computed", "EmptyDomain"):
            return self._query(
                stretch.state,
                None,
                i,
                j,
                details={
                    "reason": "endpoint stretch unavailable",
                    "stretch": stretch.to_dict(),
                },
            )
        target_weights = dict(zip(target.window.basis_current, target.window.weights))
        exact = (
            source.window.arithmetic != "FloatingPoint"
            and target.window.arithmetic != "FloatingPoint"
        )
        try:
            ratios = (
                Fraction(target_weights[label]) / Fraction(weight)
                if exact
                else target_weights[label] / weight
                for label, weight in zip(
                    source.window.basis_current, source.window.weights
                )
            )
            factor = max(ratios, default=Fraction(1) if exact else 1.0)
            mass = target.selected_mass(tracked.value)
            source_mass = source.selected_mass(x)
            bound = stretch.value * factor * source_mass
            if not exact and any(
                not isfinite(value) for value in (factor, mass, source_mass, bound)
            ):
                raise ValueError("nonfinite weight factor or mass bound")
        except (OverflowError, ValueError) as error:
            return self._query(
                "Unavailable",
                None,
                i,
                j,
                details={"reason": "NumericalFailure", "diagnostic": str(error)},
            )
        if exact and mass > bound:
            raise ValueError("endpoint stretch inequality failed")
        return self._query(
            "Computed",
            {
                "target_mass": mass,
                "source_selected_mass": source_mass,
                "weight_change_factor": factor,
                "endpoint_stretch": stretch.value,
                "mass_bound": bound,
                "bound_verified": True if exact else None,
            },
            i,
            j,
            exact,
            {
                "weight_policy": self.weight_policy,
                "arithmetic_policy": target.window.arithmetic,
                "intermediate_stretch_factors_used": False,
                "stretch": stretch.to_dict(),
            },
        )

    def _barcode_query(self, intervals):
        last = len(self.windows) - 1
        return self._query(
            "Computed",
            intervals,
            0,
            last,
            True,
            {
                "rank_invariant_source": "operator_family",
                "oracle_used_for_result": False,
                "endpoint_convention": "half-open stage indices",
                "terminal_extension": self.terminal_extension,
                "duplicate_policy": self.duplicate_policy,
            },
        )

    def _bar(self, birth, death, multiplicity=1):
        return {
            "birth_stage": birth,
            "death_stage": death,
            "birth_scale": self.scales[birth],
            "death_scale": None if death is None else self.scales[death],
            "multiplicity": multiplicity,
            "essential": death is None,
            "zero_scale_length": death is not None
            and self.scales[birth] == self.scales[death],
        }

    def _decompose(self, histories=False):
        last = len(self.windows) - 1
        for stage in range(last + 1):
            failure = self._failure(stage, stage)
            if failure is not None:
                return self._query(
                    failure.state,
                    None,
                    0,
                    last,
                    details={
                        "rank_invariant_source": "operator_family",
                        "oracle_used_for_result": False,
                        "failed_interval": (0, stage),
                    },
                )
        dimensions = [len(self._kernel(i)[0]) for i in range(last + 1)]
        # Stream one adjacent map; no chain action or all-interval rank table.
        maps = (
            tuple(map(_pack, self._coordinate_action(i, i + 1).transpose().rows))
            for i in range(last)
        )
        return _adjacent_intervals(dimensions, maps, histories)

    def barcode(self):
        """Read interval endpoints from adjacent transports of this family only."""
        bars = self._decompose()
        if isinstance(bars, QueryResult):
            return bars
        counts = Counter((birth, death) for birth, death, _ in bars)
        return self._barcode_query(
            [self._bar(b, d, count) for (b, d), count in counts.items()]
        )

    def barcode_basis(self):
        """Opt-in historical interval generators, corrected at every death.

        Vectors form a basis at each active stage, commute with adjacent maps,
        and map to zero at death. History size is charged as real output.
        """
        bars = self._decompose(histories=True)
        if isinstance(bars, QueryResult):
            result = bars
        else:
            values = []
            for birth, death, history in bars:
                vectors = []
                for stage, vector in enumerate(history, birth):
                    coordinates = _unpack(vector, len(self._kernel(stage)[0]))
                    representative = Matrix.from_columns(
                        self._kernel(stage)[0], self.windows[stage].n
                    ).apply(coordinates)
                    vectors.append(
                        {
                            "stage": stage,
                            "coordinates": coordinates,
                            "representative": representative,
                            "identity": dict(self.stage(stage).identity),
                        }
                    )
                values.append({**self._bar(birth, death), "vectors": vectors})
            result = self._barcode_query(values)
        object.__setattr__(self, "_barcode_basis", result)
        return result


def _compact_windows(family):
    """All boundaries are restrictions of the last stage in original labels."""
    final = family.windows[-1].to_dict()
    names = ("basis_previous", "basis_current", "basis_next")
    shared = {key: final[key] for key in ("A", "D", *names)}
    shared["stages"] = []
    for window, active in zip(family.windows, family._active):
        entry = window.to_dict()
        for key in ("A", "D", *names):
            del entry[key]
        entry["active"] = [list(indices) for indices in active]
        shared["stages"].append(entry)
    return shared


def _expand_windows(data):
    if data["schema_version"] == 1:
        return tuple(ChainWindow.from_dict(w) for w in data["windows"])
    shared = data["windows"]
    names = ("basis_previous", "basis_current", "basis_next")
    if not isinstance(shared, Mapping) or set(shared) != {"A", "D", *names, "stages"}:
        raise ValueError("invalid compact filtration storage")
    a, d = matrix_from_data(shared["A"]), matrix_from_data(shared["D"])
    bases = tuple(_ordered(shared[name], name) for name in names)
    if tuple(map(len, bases)) != (a.nrows, a.ncols, d.ncols) or a.ncols != d.nrows:
        raise ValueError("shared boundary and basis dimensions differ")
    matrix_pool, basis_pool, windows = {}, {}, []
    for entry in shared["stages"]:
        active = entry["active"]
        if not isinstance(active, (list, tuple)) or len(active) != 3:
            raise ValueError("compact stages need three activity index lists")
        for indices, basis in zip(active, bases):
            if (
                not isinstance(indices, (list, tuple))
                or any(type(i) is not int or not 0 <= i < len(basis) for i in indices)
                or len(set(indices)) != len(indices)
            ):
                raise ValueError("invalid compact activity indices")
        wire = {key: value for key, value in entry.items() if key != "active"}
        for name, basis, indices in zip(names, bases, active):
            selected = tuple(basis[i] for i in indices)
            wire[name] = basis_pool.setdefault(selected, selected)
        for name, matrix, rows, columns in (
            ("A", a, active[0], active[1]),
            ("D", d, active[1], active[2]),
        ):
            restricted = Matrix.from_rows(
                (tuple(matrix.rows[r][c] for c in columns) for r in rows),
                ncols=len(columns),
            )
            wire[name] = matrix_data(restricted)
        window = ChainWindow.from_dict(wire)
        # Intern only immutable algebra and bases. Weights, P, identities and
        # solver runs remain per stage; no existing operator is modified.
        object.__setattr__(window, "A", matrix_pool.setdefault(window.A, window.A))
        object.__setattr__(window, "D", matrix_pool.setdefault(window.D, window.D))
        for name in names:
            basis = getattr(window, name)
            object.__setattr__(window, name, basis_pool.setdefault(basis, basis))
        windows.append(window)
    if not windows:
        raise ValueError("compact filtration has no stages")
    if any(
        tuple(indices) != tuple(range(len(basis)))
        for indices, basis in zip(shared["stages"][-1]["active"], bases)
    ):
        raise ValueError("final compact stage must cover the shared bases in order")
    return tuple(windows)


def _restore_family(data):
    windows = _expand_windows(data)
    records = []
    if len(data["stage_results"]) != len(windows):
        raise ValueError("family stages and inputs have different lengths")
    for i, record in enumerate(data["stage_results"]):
        if data["schema_version"] == 2:
            if type(record.get("input_ref")) is not int or record["input_ref"] != i:
                raise ValueError("invalid stage input reference")
            record = {key: value for key, value in record.items() if key != "input_ref"}
            if "input_data" in record:
                raise ValueError("compact stage cannot contain a duplicate input")
            record["input_data"] = windows[i]
        records.append(OperatorResult.from_dict(record))
    records = tuple(records)
    stages = []
    for record in records:
        if record.status != "Ready":
            stages.append(record)
            continue
        stages.append(record.to_operator())
    family = OperatorFamily(
        _decode(data["scales"]),
        windows,
        tuple(stages),
        data["weight_policy"],
        data["duplicate_policy"],
        data["terminal_extension"],
    )
    object.__setattr__(family, "_schema_version", data["schema_version"])
    return family, records


@dataclass(frozen=True)
class OperatorFamilyResult:
    """Validated immutable JSON snapshot, including full stage failure records."""

    data: Mapping

    def __post_init__(self):
        version = (
            self.data.get("schema_version") if isinstance(self.data, Mapping) else None
        )
        fields = {
            "schema_version",
            "identity",
            "status",
            "scales",
            "windows",
            "stage_results",
            "weight_policy",
            "duplicate_policy",
            "terminal_extension",
            "transports",
            "rank_readout",
            "barcode_readout",
            "tracking_readout",
            "provenance",
        }
        if type(version) is int and version == 2:
            fields.add("barcode_basis_readout")
        if not isinstance(self.data, Mapping) or set(self.data) != fields:
            raise ValueError("invalid operator family result fields")
        data = _thaw_metadata(self.data)
        if type(data["schema_version"]) is not int or data["schema_version"] not in (
            1,
            2,
        ):
            raise ValueError("unsupported family result schema")
        try:
            json.dumps(data, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise ValueError("family snapshot must be finite JSON wire data") from error
        try:
            family, records = _restore_family(data)
        except (TypeError, KeyError, AttributeError, IndexError) as error:
            raise ValueError("malformed family stages or inputs") from error
        if data["identity"] != family.identity or data["status"] != family.status:
            raise ValueError(
                "family result content does not match its identity or status"
            )
        if canonical_json(data["provenance"]) != canonical_json(
            {
                "rank_invariant_source": "operator_family",
                "oracle_used_for_result": False,
                "theory_revision": THEORY_REVISION,
            }
        ):
            raise ValueError(
                "barcode provenance must reference the current operator family"
            )
        for name, method in (
            ("transports", family.transport),
            ("rank_readout", family.transport_rank),
        ):
            if not isinstance(data[name], Mapping):
                raise ValueError("family readouts must be mappings")
            for key, wire in data[name].items():
                try:
                    i, j = map(int, key.split(":"))
                except (AttributeError, TypeError, ValueError) as error:
                    raise ValueError("invalid interval key") from error
                QueryResult.from_dict(wire)
                if key != f"{i}:{j}" or canonical_json(wire) != canonical_json(
                    method(i, j).to_dict()
                ):
                    raise ValueError(
                        "persisted transport or rank differs from its operator family"
                    )
        QueryResult.from_dict(data["barcode_readout"])
        if canonical_json(data["barcode_readout"]) != canonical_json(
            family.barcode().to_dict()
        ):
            raise ValueError("persisted barcode differs from current transport ranks")
        if version == 2:
            basis = QueryResult.from_dict(data["barcode_basis_readout"])
            expected = (
                family._query("NotComputed", None, 0, len(family.windows) - 1)
                if basis.state == "NotComputed"
                else family.barcode_basis()
            )
            if canonical_json(basis.to_dict()) != canonical_json(expected.to_dict()):
                raise ValueError(
                    "persisted barcode basis differs from current transports"
                )
        if not isinstance(data["tracking_readout"], Mapping):
            raise ValueError("tracking readouts must be a mapping")
        for key, wire in data["tracking_readout"].items():
            query = QueryResult.from_dict(wire)
            name = query.details.get("query")
            if name not in {
                "track_class",
                "track_mass",
                "track_support",
                "track_shared_support",
                "track_union_support",
            }:
                raise ValueError("unknown persisted tracking query")
            arguments = query.details.get("arguments")
            i, j = query.details.get("source_stage"), query.details.get("target_stage")
            if not isinstance(arguments, tuple) or key != content_id(
                name, (arguments, i, j)
            ):
                raise ValueError("invalid tracking query key or arguments")
            try:
                expected = getattr(family, name)(*arguments, i, j)
            except TypeError as error:
                raise ValueError("invalid tracking arguments") from error
            if canonical_json(wire) != canonical_json(expected.to_dict()):
                raise ValueError("persisted tracking differs from its family")
        object.__setattr__(self, "data", _freeze(data))
        object.__setattr__(self, "identity", _freeze(data["identity"]))
        object.__setattr__(self, "status", family.status)
        object.__setattr__(self, "stage_results", records)

    def to_dict(self):
        return _thaw_metadata(self.data)

    def to_json(self):
        return json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )

    def to_family(self):
        """Reconstruct actions from validated stage projections, without re-solving."""
        data = self.to_dict()
        family = _restore_family(data)[0]
        # __post_init__ already independently replayed these immutable queries.
        family._tracking.update(
            (key, QueryResult.from_dict(wire))
            for key, wire in data["tracking_readout"].items()
        )
        for name, cache in (
            ("transports", family._transports),
            ("rank_readout", family._ranks),
        ):
            cache.update(
                (tuple(map(int, key.split(":"))), QueryResult.from_dict(wire))
                for key, wire in data[name].items()
            )
        if data["schema_version"] == 2:
            basis = QueryResult.from_dict(data["barcode_basis_readout"])
            if basis.state != "NotComputed":
                object.__setattr__(family, "_barcode_basis", basis)
        return family

    @classmethod
    def from_dict(cls, data):
        return cls(data)

    @classmethod
    def from_json(cls, text):
        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate JSON keys are not allowed")
                result[key] = value
            return result

        def reject_constant(value):
            raise ValueError(f"nonfinite JSON constant: {value}")

        return cls(
            json.loads(
                text, object_pairs_hook=unique_object, parse_constant=reject_constant
            )
        )
