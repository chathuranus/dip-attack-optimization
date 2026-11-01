
"""Strong Logic Locking placement implementation.

Based on Yasin et al., IEEE TCAD, 2016, Algorithm 3.

Includes:
- Convergence-based ranking
- SAT-based pairwise sensitization checks
- Postdominator analysis
- Theorem 1-inspired inference shortcut
- Optional rejected-candidate retry

Research note:
This implementation has not been formally validated as an exact
reproduction of the published SLL algorithm.
"""

from collections import defaultdict
from dataclasses import dataclass
from functools import reduce
from itertools import product


@dataclass
class SLLResult:
    locations: list
    cliques: list
    nonmutable_edges: list
    atpg_checks: int
    atpg_unknown: int
    candidates_rejected: int
    convergence_ranks: dict
    theorem1_inferences: int = 0
    clique_retries: int = 0


def topology(gates):
    """Compute downstream reachable gates and convergence ranks."""

    drivers = {
        out: i
        for i, (_, out, _) in enumerate(gates)
    }

    fanout = defaultdict(set)

    for _, out, args in gates:
        for arg in args:
            if arg in drivers:
                fanout[arg].add(out)

    reachable = {}

    for _, out, _ in gates:
        seen = {out}
        stack = [out]

        while stack:
            current = stack.pop()

            for nxt in fanout[current]:
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)

        reachable[out] = seen

    nodes = list(reachable)
    rank = {}

    for a in nodes:
        rank[a] = sum(
            1
            for b in nodes
            if b != a
            and a not in reachable[b]
            and b not in reachable[a]
            and bool(reachable[a] & reachable[b])
        )

    return reachable, rank


def _gate_value(op, values, z3):
    """Convert a logic gate into a Z3 Boolean expression."""

    if op == "and":
        return z3.And(*values)

    if op == "nand":
        return z3.Not(z3.And(*values))

    if op == "or":
        return z3.Or(*values)

    if op == "nor":
        return z3.Not(z3.Or(*values))

    if op == "xor":
        return reduce(z3.Xor, values)

    if op == "xnor":
        return z3.Not(reduce(z3.Xor, values))

    if op == "not":
        return z3.Not(values[0])

    if op == "buf":
        return values[0]

    raise ValueError(f"Unsupported gate: {op}")


def _four_cofactors(
    gates,
    inputs,
    outputs,
    target,
    other,
    z3,
):
    """Construct four circuit evaluations for two key-gate locations.

    The four configurations correspond to:

        target=0, other=0
        target=0, other=1
        target=1, other=0
        target=1, other=1

    All other potential key gates are neutralized.
    """

    x = {
        name: z3.Bool(f"PI_{name}")
        for name in inputs
    }

    result = {}

    for t, b in product((0, 1), repeat=2):
        values = dict(x)

        for op, out, args in gates:
            gate_inputs = [
                values[arg]
                for arg in args
            ]

            value = _gate_value(
                op,
                gate_inputs,
                z3,
            )

            if (
                (out == target and t == 1)
                or (out == other and b == 1)
            ):
                value = z3.Not(value)

            values[out] = value

        result[t, b] = [
            values[name]
            for name in outputs
        ]

    return result


def sensitization_exists_z3(
    gates,
    inputs,
    outputs,
    target,
    other,
    timeout_ms=10000,
):
    """Check whether the target key can be observed independently.

    SAT:
        A sensitizing input exists.

    UNSAT:
        No such input exists under this pairwise model.
    """

    try:
        import z3
    except ImportError as exc:
        raise RuntimeError(
            "Install Z3 using: pip install z3-solver"
        ) from exc

    cofactors = _four_cofactors(
        gates,
        inputs,
        outputs,
        target,
        other,
        z3,
    )

    conditions = []

    for i in range(len(outputs)):
        y00 = cofactors[0, 0][i]
        y01 = cofactors[0, 1][i]
        y10 = cofactors[1, 0][i]
        y11 = cofactors[1, 1][i]

        conditions.append(
            z3.And(
                y00 == y01,
                y10 == y11,
                y00 != y10,
            )
        )

    solver = z3.Solver()
    solver.set(timeout=timeout_ms)
    solver.add(z3.Or(*conditions))

    status = solver.check()

    if status == z3.sat:
        return True

    if status == z3.unsat:
        return False

    raise TimeoutError(
        "ATPG SAT solver returned unknown: "
        + solver.reason_unknown()
    )


def _eval(
    gates,
    inputs,
    outputs,
    x,
    target,
    other,
    t,
    b,
):
    """Evaluate a circuit under two hypothetical key bits."""

    values = dict(x)

    for op, out, args in gates:
        a = [
            values[name]
            for name in args
        ]

        if op in ("and", "nand"):
            value = int(all(a))

        elif op in ("or", "nor"):
            value = int(any(a))

        elif op in ("xor", "xnor"):
            value = sum(a) % 2

        elif op == "not":
            value = 1 - a[0]

        else:
            value = a[0]

        if op in ("nand", "nor", "xnor"):
            value = 1 - value

        if (
            (out == target and t)
            or (out == other and b)
        ):
            value = 1 - value

        values[out] = value

    return tuple(
        values[name]
        for name in outputs
    )


def sensitization_exists_exhaustive(
    gates,
    inputs,
    outputs,
    target,
    other,
):
    """Exhaustive reference check for small circuits.

    Supports circuits with at most 12 primary inputs.
    """

    if len(inputs) > 12:
        raise ValueError(
            "Exhaustive ATPG supports at most 12 inputs"
        )

    for bits in product(
        (0, 1),
        repeat=len(inputs),
    ):
        x = dict(zip(inputs, bits))

        y00 = _eval(
            gates, inputs, outputs,
            x, target, other, 0, 0,
        )

        y01 = _eval(
            gates, inputs, outputs,
            x, target, other, 0, 1,
        )

        y10 = _eval(
            gates, inputs, outputs,
            x, target, other, 1, 0,
        )

        y11 = _eval(
            gates, inputs, outputs,
            x, target, other, 1, 1,
        )

        for i in range(len(outputs)):
            if (
                y00[i] == y01[i]
                and y10[i] == y11[i]
                and y00[i] != y10[i]
            ):
                return True

    return False


def postdominators(gates, outputs):
    """Compute gate postdominators in the circuit DAG.

    A postdominator lies on every observable path from
    a gate to a primary output.
    """

    nodes = [
        out
        for _, out, _ in gates
    ]

    node_set = set(nodes)

    successors = {
        node: set()
        for node in nodes
    }

    for _, out, args in gates:
        for arg in args:
            if arg in node_set:
                successors[arg].add(out)

    sink = object()

    postdom = {
        sink: {sink}
    }

    reaches_output = {
        sink: True
    }

    output_set = set(outputs)

    for node in reversed(nodes):
        live = [
            successor
            for successor in successors[node]
            if reaches_output.get(
                successor,
                False,
            )
        ]

        if node in output_set:
            live.append(sink)

        reaches_output[node] = bool(live)

        if live:
            common = postdom[live[0]].copy()

            for successor in live[1:]:
                common.intersection_update(
                    postdom[successor]
                )

            postdom[node] = {
                node
            } | common

        else:
            postdom[node] = {node}

    return postdom, reaches_output


def select_sll(
    gates,
    inputs,
    outputs,
    key_size,
    rng,
    atpg_backend="z3",
    timeout_ms=10000,
    max_checks=None,
    use_theorem1=True,
    retry_rejected=False,
):
    """Select key-gate locations using SLL-style clique construction.

    retry_rejected=False:
        Original-style global processed marking.

    retry_rejected=True:
        Non-standard extension allowing previously rejected
        candidates to be reconsidered in later cliques.
    """

    if atpg_backend not in ("z3", "exhaustive"):
        raise ValueError(
            "Unsupported ATPG backend"
        )

    if key_size < 1:
        raise ValueError(
            "Key size must be positive"
        )

    reachable, rank = topology(gates)

    postdom, observable = postdominators(
        gates,
        outputs,
    )

    candidates = sorted(
        node
        for node in reachable
        if observable[node]
    )

    if key_size > len(candidates):
        raise ValueError(
            f"Requested {key_size} key gates, "
            f"but only {len(candidates)} "
            "observable gates exist"
        )

    checker = (
        sensitization_exists_z3
        if atpg_backend == "z3"
        else sensitization_exists_exhaustive
    )

    def dominates(a, b):
        """Return True if b postdominates a."""

        return (
            a != b
            and b in postdom[a]
        )

    used = set()
    processed = set()

    cliques = []
    secure_edges = []
    cache = {}

    stats = {
        "checks": 0,
        "unknown": 0,
        "rejected": 0,
        "inferred": 0,
        "retries": 0,
    }

    def pair_secure(a, b):
        """Determine whether two candidate locations are secure."""

        pair = tuple(sorted((a, b)))

        if pair in cache:
            return cache[pair]

        if not (
            reachable[a] & reachable[b]
        ):
            cache[pair] = False
            return False

        for target, other in (
            (a, b),
            (b, a),
        ):
            if (
                max_checks is not None
                and stats["checks"] >= max_checks
            ):
                raise RuntimeError(
                    "ATPG check budget exhausted"
                )

            stats["checks"] += 1

            try:
                if atpg_backend == "z3":
                    mutable = checker(
                        gates,
                        inputs,
                        outputs,
                        target,
                        other,
                        timeout_ms=timeout_ms,
                    )
                else:
                    mutable = checker(
                        gates,
                        inputs,
                        outputs,
                        target,
                        other,
                    )

            except TimeoutError:
                stats["unknown"] += 1
                raise

            if mutable:
                cache[pair] = False
                return False

        cache[pair] = True
        return True

    def inferred_secure(
        candidate,
        existing,
        clique,
    ):
        """Apply the Theorem 1-inspired inference shortcut.

        This shortcut must be independently validated
        against direct SAT checks before research use.
        """

        if not use_theorem1:
            return False

        for d in clique:
            if d == existing:
                continue

            pair_ad = tuple(
                sorted((candidate, d))
            )

            pair_db = tuple(
                sorted((d, existing))
            )

            if (
                cache.get(pair_ad) is True
                and cache.get(pair_db) is True
                and (
                    dominates(candidate, d)
                    or dominates(existing, d)
                )
            ):
                pair = tuple(
                    sorted((candidate, existing))
                )

                cache[pair] = True
                stats["inferred"] += 1

                return True

        return False

    while len(used) < key_size:
        available = [
            node
            for node in candidates
            if node not in used
            and (
                retry_rejected
                or node not in processed
            )
        ]

        if not available:
            break

        max_rank = max(
            rank[node]
            for node in available
        )

        seeds = [
            node
            for node in available
            if rank[node] == max_rank
        ]

        seed = rng.choice(seeds)

        clique = [seed]
        cliques.append(clique)

        used.add(seed)
        processed.add(seed)

        rejected_here = set()

        if (
            retry_rejected
            and len(cliques) > 1
        ):
            stats["retries"] += 1

        while len(used) < key_size:
            neighbors = [
                node
                for node in candidates
                if node not in used
                and node not in rejected_here
                and (
                    retry_rejected
                    or node not in processed
                )
                and any(
                    reachable[node] & reachable[k]
                    for k in clique
                )
            ]

            if not neighbors:
                break

            neighbors.sort(
                key=lambda node: (
                    -rank[node],
                    node,
                )
            )

            added = False

            for node in neighbors:
                order = sorted(
                    clique,
                    key=lambda d: (
                        -sum(
                            dominates(k, d)
                            for k in clique
                            if k != d
                        )
                        - int(
                            dominates(node, d)
                        ),
                        -rank[d],
                        d,
                    ),
                )

                secure = True

                for k in order:
                    pair = tuple(
                        sorted((node, k))
                    )

                    if cache.get(pair) is True:
                        continue

                    if inferred_secure(
                        node,
                        k,
                        clique,
                    ):
                        continue

                    if not pair_secure(node, k):
                        secure = False
                        break

                if secure:
                    for k in clique:
                        secure_edges.append(
                            (node, k)
                        )

                    clique.append(node)
                    used.add(node)
                    processed.add(node)

                    added = True
                    break

                rejected_here.add(node)

                if not retry_rejected:
                    processed.add(node)

                stats["rejected"] += 1

            if not added:
                break

    locations = [
        node
        for clique in cliques
        for node in clique
    ]

    return SLLResult(
        locations=locations,
        cliques=cliques,
        nonmutable_edges=secure_edges,
        atpg_checks=stats["checks"],
        atpg_unknown=stats["unknown"],
        candidates_rejected=stats["rejected"],
        convergence_ranks=rank,
        theorem1_inferences=stats["inferred"],
        clique_retries=stats["retries"],
    )
