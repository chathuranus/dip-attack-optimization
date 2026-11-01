# dip_strategies.py

from abc import ABC, abstractmethod

from z3 import AtLeast, is_true, sat, unsat

import sat_model


# z3's value for "no timeout"; pop() does not undo a timeout, so it must be restored.
NO_TIMEOUT = 4294967295


def hamming_distance(model, output_xors):
    """Returns the number of outputs on which the two locked circuit copies differ in a model"""
    return sum(is_true(model.eval(x, model_completion=True)) for x in output_xors)


class DIPStrategy(ABC):

    @abstractmethod
    def find_dip(self, context):
        """Return a DIP or None if no DIP exists."""
        pass


class StandardSATStrategy(DIPStrategy):

    def find_dip(self, context):
        """Returns a standard dip for the circuit given the current constraints"""
        model = context.solver.model()

        if context.metrics is not None:
            # Baseline for comparison; costs no extra solver calls.
            context.metrics.record_hamming(hamming_distance(model, context.output_xors))

        primary_inputs = context.miter_ckt.primary_inputs()
        return sat_model.extract_from_model(model, primary_inputs, completion=True)


class PartitioningStrategy(DIPStrategy):

    def find_dip(self, context):
        raise NotImplementedError(
            "Sampled-key partitioning is not implemented yet"
        )


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
        "standard_sat": StandardSATStrategy,
        "partitioning": PartitioningStrategy,
        "maxsat": MaxSATStrategy,
    }

    if method not in strategies:
        raise ValueError(
            f"Unsupported attack method: {method}"
        )

    return strategies[method](**options)
