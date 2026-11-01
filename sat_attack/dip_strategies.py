"""Interchangeable DIP selectors for offline logic-locking benchmarks."""
from abc import ABC, abstractmethod
from time import perf_counter

from z3 import BoolVal, is_true, is_false, AtLeast, sat, substitute, simplify, unsat, Bool, Or 

import sat_model
from partitioning import evaluate_partition


# z3's value for "no timeout"; pop() does not undo a timeout, so it must be restored.
NO_TIMEOUT = 4294967295


def hamming_distance(model, output_xors):
    """Returns the number of outputs on which the two locked circuit copies differ in a model"""
    return sum(is_true(model.eval(x, model_completion=True)) for x in output_xors)


class DIPStrategy(ABC):
    @abstractmethod
    def find_dip(self, context):
        """Return a DIP mapping or None when no DIP exists."""


class StandardSATStrategy(DIPStrategy):
    def find_dip(self, context):
        # The attack loop already called can_find_dip(), so the model exists.
        model = context.solver.model()
        if context.metrics is not None:
            # Baseline for comparison; costs no extra solver calls.
            context.metrics.record_hamming(hamming_distance(model, context.output_xors))

        primary_inputs = context.miter_ckt.primary_inputs()
        return sat_model.extract_from_model(model, primary_inputs, completion=True)
    
def _bool_value(model, name):
    return is_true(model.eval(Bool(name), model_completion=True))


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
                if status == unsat:
                    break
                if status != sat:
                    raise RuntimeError(f"Miter solver returned {status}")
                model = solver.model()
                dip = {name: _bool_value(model, name) for name in names}
                dips.append(dip)
                # Block this INPUT pattern, not a particular key pair.
                if not names:
                    break
                solver.add(Or(*[
                    Bool(name) != BoolVal(dip[name]) for name in names
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
                if status == unsat:
                    break
                if status != sat:
                    raise RuntimeError(f"Key sampler returned {status}")
                model = solver.model()
                key = {name: _bool_value(model, name) for name in names}
                keys.append(key)
                # Exclude this exact key in the TEMPORARY solver scope.
                solver.add(Or(*[
                    Bool(name) != BoolVal(key[name]) for name in names
                ]))
        finally:
            solver.pop()
        return keys

    @staticmethod
    def _evaluate_outputs(context, dip, key):
        """Evaluate the known locked netlist without consulting the oracle."""
        assignments = {**dip, **key}
        substitutions = [
            (Bool(name), BoolVal(value))
            for name, value in assignments.items()
        ]
        values = []
        for name in context.output_names:
            expr = context.locked_ckt0.outputs()[name]
            grounded = simplify(substitute(expr, *substitutions))
            if is_true(grounded):
                values.append(True)
            elif is_false(grounded):
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
    """
    Selects the DIP that maximizes the output Hamming distance between the
    two locked circuit copies. Starting from the model found by can_find_dip,
    it repeatedly asks the solver for a model where at least one more output
    differs, until that is unsat (optimum proven), times out, or hits the cap.
    """

    def __init__(self, timeout_ms=None, max_extra_checks=None):
        """
        timeout_ms: optional time limit for each extra solver check
        max_extra_checks: optional cap on extra solver checks per DIP
        """
        self.timeout_ms = timeout_ms
        self.max_extra_checks = max_extra_checks

    def find_dip(self, context):
        """Returns the dip with the maximum output Hamming distance given the current constraints"""
        solver = context.solver
        metrics = context.metrics
        output_xors = context.output_xors

        best = solver.model()
        best_distance = hamming_distance(best, output_xors)
        optimal = best_distance == len(output_xors)
        extra_checks = 0

        if self.timeout_ms is not None:
            solver.set("timeout", self.timeout_ms)

        try:
            while not optimal:
                if self.max_extra_checks is not None and extra_checks >= self.max_extra_checks:
                    break

                # The cardinality constraint is temporary; the attack's
                # permanent constraints must stay the same as standard_sat's.
                solver.push()
                solver.add(AtLeast(*output_xors, best_distance + 1))
                result = solver.check()
                if result == sat:
                    best = solver.model()
                solver.pop()

                extra_checks += 1
                if metrics is not None:
                    metrics.record_iteration()

                if result == sat:
                    best_distance = hamming_distance(best, output_xors)
                    optimal = best_distance == len(output_xors)
                elif result == unsat:
                    optimal = True
                else:
                    break  # unknown (timeout): keep the best model found so far
        finally:
            if self.timeout_ms is not None:
                solver.set("timeout", NO_TIMEOUT)

        if metrics is not None:
            metrics.record_hamming(best_distance, optimal)

        primary_inputs = context.miter_ckt.primary_inputs()
        return sat_model.extract_from_model(best, primary_inputs, completion=True)


def create_strategy(method, **options):
    strategies = {
        "standard_sat": lambda: StandardSATStrategy(),
        "partitioning": lambda: PartitioningStrategy(
            key_samples=options.get("partition_key_samples", 32),
            dip_candidates=options.get("partition_dip_candidates", 8),
        ),
        "maxsat": lambda: MaxSATStrategy(
            timeout_ms=options.get("timeout_ms"),
            max_extra_checks=options.get("max_extra_checks"),
        ),
    }
    if method not in strategies:
        raise ValueError(f"Unsupported attack method: {method}")
    return strategies[method]()
