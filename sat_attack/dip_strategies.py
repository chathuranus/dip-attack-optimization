"""Interchangeable DIP selectors for offline logic-locking benchmarks."""
from abc import ABC, abstractmethod
from time import perf_counter

import z3
import sat_model
from partitioning import evaluate_partition


class DIPStrategy(ABC):
    @abstractmethod
    def find_dip(self, context):
        """Return a DIP mapping or None when no DIP exists."""


class StandardSATStrategy(DIPStrategy):
    def find_dip(self, context):
        # The attack loop already called can_find_dip(), so the model exists.
        model = context.solver.model()
        return sat_model.extract_from_model(
            model, context.miter_ckt.primary_inputs(), completion=True
        )


def _bool_value(model, name):
    return z3.is_true(model.eval(z3.Bool(name), model_completion=True))


class PartitioningStrategy(DIPStrategy):
    def __init__(self, key_samples=32, dip_candidates=8):
        if key_samples < 2 or dip_candidates < 1:
            raise ValueError("key_samples >= 2 and dip_candidates >= 1 required")
        self.key_samples = key_samples
        self.dip_candidates = dip_candidates

    def _candidate_dips(self, context):
        """Temporarily enumerate distinct miter DIPs without changing it."""
        names = context.miter_ckt.primary_inputs()
        solver = context.solver
        dips = []
        solver.push()
        try:
            for _ in range(self.dip_candidates):
                status = solver.check()
                if status == z3.unsat:
                    break
                if status != z3.sat:
                    raise RuntimeError(f"Miter solver returned {status}")
                model = solver.model()
                dip = {name: _bool_value(model, name) for name in names}
                dips.append(dip)
                # Block this INPUT pattern, not a particular key pair.
                if not names:
                    break
                solver.add(z3.Or(*[
                    z3.Bool(name) != z3.BoolVal(dip[name]) for name in names
                ]))
        finally:
            solver.pop()
        return dips

    def _candidate_keys(self, context):
        """Enumerate keys satisfying all previous oracle observations."""
        names = context.locked_ckt0.key_inputs()
        if not names:
            raise ValueError("No key inputs found in the locked circuit")
        solver = context.key_solver
        keys = []
        solver.push()
        try:
            for _ in range(self.key_samples):
                status = solver.check()
                if status == z3.unsat:
                    break
                if status != z3.sat:
                    raise RuntimeError(f"Key sampler returned {status}")
                model = solver.model()
                key = {name: _bool_value(model, name) for name in names}
                keys.append(key)
                # Exclude this exact key in the TEMPORARY solver scope.
                solver.add(z3.Or(*[
                    z3.Bool(name) != z3.BoolVal(key[name]) for name in names
                ]))
        finally:
            solver.pop()
        return keys

    @staticmethod
    def _evaluate_outputs(context, dip, key):
        """Evaluate the known locked netlist without consulting the oracle."""
        assignments = {**dip, **key}
        substitutions = [
            (z3.Bool(name), z3.BoolVal(value))
            for name, value in assignments.items()
        ]
        values = []
        for name in context.output_names:
            expr = context.locked_ckt0.outputs()[name]
            grounded = z3.simplify(z3.substitute(expr, *substitutions))
            if z3.is_true(grounded):
                values.append(True)
            elif z3.is_false(grounded):
                values.append(False)
            else:
                raise ValueError(
                    f"Output {name} is not ground after assigning inputs/key: "
                    f"{grounded}"
                )
        return tuple(values)

    def find_dip(self, context):
        start = perf_counter()
        dips = self._candidate_dips(context)
        if not dips:
            return None
        keys = self._candidate_keys(context)
        if not keys:
            raise RuntimeError("No feasible keys remain after oracle observations")

        best_dip = None
        best_score = None
        for dip in dips:
            outputs = [self._evaluate_outputs(context, dip, key) for key in keys]
            score = evaluate_partition(outputs)
            # Entropy first; smallest worst-case class breaks ties.
            priority = (score["entropy"], -score["largest_class"])
            if best_score is None or priority > best_score:
                best_dip, best_score = dip, priority
                best_details = score

        context.last_selection = {
            "method": "partitioning",
            "candidate_dips": len(dips),
            "candidate_keys": len(keys),
            "selection_seconds": perf_counter() - start,
            **best_details,
        }
        return best_dip


class MaxSATStrategy(DIPStrategy):
    def find_dip(self, context):
        raise NotImplementedError("MaxSAT DIP selection is not implemented yet")


def create_strategy(method, partition_key_samples=32, partition_dip_candidates=8):
    strategies = {
        "standard_sat": lambda: StandardSATStrategy(),
        "partitioning": lambda: PartitioningStrategy(
            key_samples=partition_key_samples,
            dip_candidates=partition_dip_candidates,
        ),
        "maxsat": lambda: MaxSATStrategy(),
    }
    if method not in strategies:
        raise ValueError(f"Unsupported attack method: {method}")
    return strategies[method]()
