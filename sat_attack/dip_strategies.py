# dip_strategies.py

from abc import ABC, abstractmethod

import sat_model


class DIPStrategy(ABC):

    @abstractmethod
    def find_dip(self, context):
        """Return a DIP or None if no DIP exists."""
        pass


class StandardSATStrategy(DIPStrategy):

    def find_dip(self, context):
        """Returns a standard dip for the circuit given the current constraints"""
        model = context.solver.model()
        primary_inputs = context.miter_ckt.primary_inputs()
        return sat_model.extract_from_model(model, primary_inputs, completion=True)


class PartitioningStrategy(DIPStrategy):

    def find_dip(self, context):
        raise NotImplementedError(
            "Sampled-key partitioning is not implemented yet"
        )


class MaxSATStrategy(DIPStrategy):

    def find_dip(self, context):
        raise NotImplementedError(
            "MaxSAT DIP selection is not implemented yet"
        )


def create_strategy(method):

    strategies = {
        "standard_sat": StandardSATStrategy,
        "partitioning": PartitioningStrategy,
        "maxsat": MaxSATStrategy,
    }

    if method not in strategies:
        raise ValueError(
            f"Unsupported attack method: {method}"
        )

    return strategies[method]()