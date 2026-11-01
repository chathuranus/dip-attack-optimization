"""Interchangeable DIP selectors for offline logic-locking benchmarks."""
from abc import ABC, abstractmethod
from time import perf_counter

from z3 import is_true, AtLeast, sat, unsat, Bool, BoolRef, Not
from z3.z3core import Z3_get_bool_value, Z3_mk_or
from z3.z3types import Ast
from z3.z3consts import Z3_L_TRUE

from z3 import AtLeast, is_true, sat, unsat

import sat_model
from bitwise_eval import evaluate_packed, gate_order
from partitioning import evaluate_partition


# z3's value for "no timeout"; pop() does not undo a timeout, so it must be restored.
NO_TIMEOUT = 4294967295

# Key suffix DipFinder gives locked_ckt0, whose key names the key sampler returns.
CKT0_KEY_SUFFIX = "__ckt0"


def _fast_or(literals):
    """Or() without the Python wrapper's per-argument checks (~50x faster)."""
    ctx = literals[0].ctx
    args = (Ast * len(literals))(*[lit.as_ast() for lit in literals])
    return BoolRef(Z3_mk_or(ctx.ref(), len(literals), args), ctx)


def _fast_is_true(model, var):
    """is_true(model.eval(var, model_completion=True)) with one C call for the test."""
    return Z3_get_bool_value(var.ctx.ref(), model.eval(var, model_completion=True).as_ast()) == Z3_L_TRUE


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
    
class PartitioningStrategy(DIPStrategy):
    def __init__(self, key_samples=32, dip_candidates=8):
        if key_samples < 2 or dip_candidates < 1:
            raise ValueError("key_samples >= 2 and dip_candidates >= 1 required")
        self.key_samples = key_samples
        self.dip_candidates = dip_candidates
        self._gate_order = None
        # name -> (Bool(name), Not(Bool(name))), built once; making z3 terms
        # per model dominated sampling time.
        self._literals = {}

    def _literal_pairs(self, names):
        missing = [name for name in names if name not in self._literals]
        for name in missing:
            var = Bool(name)
            self._literals[name] = (var, Not(var))
        return [(name, *self._literals[name]) for name in names]

    def _enumerate(self, solver, names, limit, model=None):
        """
        Returns up to limit distinct assignments to names that satisfy solver,
        blocking each one in a temporary scope. model: an already-checked
        model to use as the first assignment instead of a fresh check.
        """
        literals = self._literal_pairs(names)
        found = []
        solver.push()
        try:
            while len(found) < limit:
                if model is None:
                    status = solver.check()
                    if status == unsat:
                        break
                    if status != sat:
                        raise RuntimeError(f"Solver returned {status}")
                    model = solver.model()
                values = {name: _fast_is_true(model, var) for name, var, _ in literals}
                found.append(values)
                model = None
                if not names:
                    break
                solver.add(_fast_or([neg if values[name] else var for name, var, neg in literals]))
        finally:
            solver.pop()
        return found

    def _candidate_dips(self, context):
        """Temporarily enumerate distinct miter DIPs without changing it."""
        # can_find_dip() just checked the miter, so its model is the first DIP.
        # Blocking an INPUT pattern, not a particular key pair.
        return self._enumerate(context.solver, context.miter_ckt.primary_inputs(),
                               self.dip_candidates, model=context.solver.model())

    def _candidate_keys(self, context):
        """Enumerate keys satisfying all previous oracle observations."""
        names = context.locked_ckt0.key_inputs()
        if not names:
            raise ValueError("No key inputs found in the locked circuit")
        return self._enumerate(context.key_solver, names, self.key_samples)

    def _evaluate_partition_outputs(self, context, dips, keys):
        """
        Evaluate the known locked netlist without consulting the oracle.
        All sampled keys run in parallel as bit lanes; returns, per DIP,
        one output vector per key.
        """
        if self._gate_order is None:
            self._gate_order = gate_order(context.nodes, context.output_names)
        mask = (1 << len(keys)) - 1
        # Sampled keys are named after locked_ckt0's copy; the netlist uses the bare names.
        packed_keys = {
            name.removesuffix(CKT0_KEY_SUFFIX): sum(1 << i for i, key in enumerate(keys) if key[name])
            for name in keys[0]
        }
        results = []
        for dip in dips:
            inputs = {**{name: mask if value else 0 for name, value in dip.items()}, **packed_keys}
            packed = evaluate_packed(context.nodes, self._gate_order, context.output_names, inputs, mask)
            lanes = [packed[name] for name in context.output_names]
            results.append([tuple(bool(v >> i & 1) for v in lanes) for i in range(len(keys))])
        return results

    def find_dip(self, context):
        start = perf_counter()
        dips = self._candidate_dips(context)
        dip_seconds = perf_counter() - start
        if not dips:
            return None

        start = perf_counter()
        keys = self._candidate_keys(context)
        key_seconds = perf_counter() - start
        if not keys:
            raise RuntimeError("No feasible keys remain after oracle observations")

        start = perf_counter()
        best_dip = None
        best_score = None
        for dip, outputs in zip(dips, self._evaluate_partition_outputs(context, dips, keys)):
            score = evaluate_partition(outputs)
            # Entropy first; smallest worst-case class breaks ties.
            priority = (score["entropy"], -score["largest_class"])
            if best_score is None or priority > best_score:
                best_dip, best_score = dip, priority
                best_details = score

        context.last_selection = {
            "candidate_dips": len(dips),
            "candidate_keys": len(keys),
            "selected_dip_entropy": best_details["entropy"],
            "num_classes": best_details["num_classes"],
            "largest_class": best_details["largest_class"],
            "worst_case_eliminated": best_details["worst_case_eliminated"],
            "key_sampling_seconds": key_seconds,
            "candidate_dip_generation_seconds": dip_seconds,
            "partition_scoring_seconds": perf_counter() - start,
        }
        if context.metrics is not None:
            context.metrics.record_partition(context.last_selection)
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
        raise ValueError(
            f"Unsupported attack method: {method}"
        )

    return strategies[method](**options)
