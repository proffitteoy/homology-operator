"""Independent set enumeration for the frozen geometry corpus; no runtime imports."""

from itertools import combinations, product


def boundary(chain):
    result = set()
    for cell in chain:
        if len(cell) > 1:
            result.symmetric_difference_update(combinations(cell, len(cell) - 1))
    return result


def subsets(cells):
    for bits in product((0, 1), repeat=len(cells)):
        yield {s for s, bit in zip(cells, bits) if bit}


def histories(cells, degree):
    """Raw set-column PH reduction, used only as a control of P/T histories."""
    pivots, changes, reduced, births = {}, [], [], []
    for j, cell in enumerate(cells):
        column, change = boundary({cell}), {cell}
        while column and max(column, key=cells.index) in pivots:
            p = pivots[max(column, key=cells.index)]
            column ^= reduced[p]
            change ^= changes[p]
        reduced.append(column)
        changes.append(change)
        if column:
            pivots[max(column, key=cells.index)] = j
        else:
            births.append(j)
    return {
        (b, pivots.get(cells[b])): reduced[pivots[cells[b]]]
        if cells[b] in pivots
        else changes[b]
        for b in births
        if len(cells[b]) == degree + 1
    }


def volumes(cells, levels, degree, birth, death, weights, epsilon=None):
    """All feasible upper chains, including every tie, using raw simplex sets."""
    cutoff = None if epsilon is None else levels[birth] + epsilon
    allowed = [
        s
        for j, s in enumerate(cells)
        if j < death
        and len(s) == degree + 2
        and (j > birth if cutoff is None else levels[j] >= cutoff)
    ]
    forbidden = {
        s
        for j, s in enumerate(cells)
        if j < death
        and len(s) == degree + 1
        and (j > birth if cutoff is None else levels[j] >= cutoff)
    }
    out = []
    for free in subsets(allowed):
        chain = free | {cells[death]}
        image = boundary(chain)
        if image & forbidden or (epsilon is None and cells[birth] not in image):
            continue
        out.append((sum(weights[s] for s in chain), frozenset(chain), frozenset(image)))
    return out
