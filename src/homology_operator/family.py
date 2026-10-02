"""Finite coordinate filtrations of the same validated homology operators."""

from collections.abc import Mapping, Set
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
from .solver import ProjectionSolution


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

    _tracking: dict = field(init=False, default_factory=dict, repr=False, compare=False)

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
            result = self._query(state, None, i, j, details={"failed_stages": failed})
            self._transports[i, j] = result
            return result
        source, target = self.stage(i), self.stage(j)
        source_kernel = Matrix.from_columns(source.kernel_basis(), source.window.n)
        target_kernel = Matrix.from_columns(target.kernel_basis(), target.window.n)
        chain_action = target.P @ (self.inclusion(i, j) @ source_kernel)
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

    def to_result(self):
        """Immutable snapshot; serialization revalidates persisted derived readouts."""
        barcode = self.barcode()
        return OperatorFamilyResult(
            {
                "schema_version": 1,
                "identity": dict(self.identity),
                "status": self.status,
                "scales": _encode(self.scales),
                "windows": [w.to_dict() for w in self.windows],
                "stage_results": [
                    (
                        op.to_result() if isinstance(op, HomologyOperator) else op
                    ).to_dict()
                    for op in self.operators
                ],
                "weight_policy": self.weight_policy,
                "duplicate_policy": self.duplicate_policy,
                "terminal_extension": self.terminal_extension,
                "transports": {
                    f"{i}:{j}": result.to_dict()
                    for (i, j), result in self._transports.items()
                },
                "rank_readout": {
                    f"{i}:{j}": self.transport_rank(i, j).to_dict()
                    for i, j in tuple(self._transports)
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
        )

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
        transport = self.transport(i, j)
        if transport.state != "Computed":
            result = self._query(transport.state, None, i, j, details=transport.details)
        else:
            source = self.stage(i)
            kernel = Matrix.from_columns(source.kernel_basis(), source.window.n)
            coordinates = kernel.solve(source.project(x))
            if coordinates is None:
                raise ValueError("source representative is outside its kernel")
            value = matrix_from_data(transport.value["chain_action"]).apply(coordinates)
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
                value = getattr(target, name)(*(x.value for x in chains))
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

    def barcode(self):
        """Read half-open stage intervals from transport ranks only.

        A None death is essential under the constant final-stage extension.
        Repeated scale labels can yield zero scale length but distinct stage ends.
        """
        last = len(self.windows) - 1
        ranks = {}
        for i in range(last + 1):
            for j in range(i, last + 1):
                result = self.transport_rank(i, j)
                if result.state != "Computed":
                    return self._query(
                        result.state,
                        None,
                        0,
                        last,
                        details={
                            "rank_invariant_source": "operator_family",
                            "oracle_used_for_result": False,
                            "failed_interval": (i, j),
                        },
                    )
                ranks[i, j] = result.value

        def rank(i, j):
            return 0 if i < 0 or j > last else ranks[i, j]

        intervals = []
        for birth in range(last + 1):
            for death in range(birth + 1, last + 2):
                multiplicity = (
                    rank(birth, death - 1)
                    - rank(birth - 1, death - 1)
                    - rank(birth, death)
                    + rank(birth - 1, death)
                )
                if multiplicity < 0:
                    raise ValueError(
                        "rank invariant has negative interval multiplicity"
                    )
                if multiplicity:
                    essential = death == last + 1
                    intervals.append(
                        {
                            "birth_stage": birth,
                            "death_stage": None if essential else death,
                            "birth_scale": self.scales[birth],
                            "death_scale": None if essential else self.scales[death],
                            "multiplicity": multiplicity,
                            "essential": essential,
                            "zero_scale_length": False
                            if essential
                            else self.scales[birth] == self.scales[death],
                        }
                    )
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


def _restore_family(data):
    records = tuple(
        OperatorResult.from_dict(record) for record in data["stage_results"]
    )
    stages = []
    for record in records:
        if record.status != "Ready":
            stages.append(record)
            continue
        metadata = record.solver
        solution = ProjectionSolution(
            metadata["status"],
            record.identity["solver_run_id"],
            record.projection,
            record.identity,
            metadata["certificate_level"],
            QueryResult.from_dict(
                metadata.get(
                    "objective",
                    QueryResult("NotComputed", identity=record.identity).to_dict(),
                )
            ),
            record.certificate,
            metadata.get("resource_usage", {}),
            tie_break_policy=metadata.get("tie_break_policy", "StableBasisOrder"),
            method=metadata.get("method", "FeasibleSolver"),
            arithmetic_policy=metadata.get("arithmetic_policy"),
            lower_bound=metadata.get("lower_bound"),
            upper_bound=metadata.get("upper_bound"),
            solver_config=metadata.get("solver_config"),
            diagnostics=metadata.get("diagnostics", ()),
        )
        operator = HomologyOperator(
            record.input_data,
            solution,
            record.provenance.get("repository_revision", "unknown"),
        )
        object.__setattr__(operator, "_provenance", record.provenance)
        # Preserve queried states for the next snapshot. These entries are history,
        # not substitutes for recomputing an operator action or a kernel basis.
        operator._queries.update(record.query_results)
        kernel = record.query_results.get("kernel_basis")
        if kernel is not None and kernel.state == "Computed":
            if canonical_json(kernel.value) != canonical_json(operator.kernel_basis()):
                raise ValueError("persisted stage kernel does not match its projection")
        stages.append(operator)
    family = OperatorFamily(
        _decode(data["scales"]),
        tuple(ChainWindow.from_dict(w) for w in data["windows"]),
        tuple(stages),
        data["weight_policy"],
        data["duplicate_policy"],
        data["terminal_extension"],
    )
    return family, records


@dataclass(frozen=True)
class OperatorFamilyResult:
    """Validated immutable JSON snapshot, including full stage failure records."""

    data: Mapping

    def __post_init__(self):
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
        if not isinstance(self.data, Mapping) or set(self.data) != fields:
            raise ValueError("invalid operator family result fields")
        data = _thaw_metadata(self.data)
        if type(data["schema_version"]) is not int or data["schema_version"] != 1:
            raise ValueError("unsupported family result schema")
        try:
            json.dumps(data, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise ValueError("family snapshot must be finite JSON wire data") from error
        try:
            family, records = _restore_family(data)
        except (TypeError, KeyError, AttributeError) as error:
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
        return _restore_family(self.to_dict())[0]

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
