from z3 import Solver, Xor, sat

import sat_model
from circuit import Circuit
from dip_strategies import create_strategy


class DipFinder:
    def __init__(
        self,
        nodes,
        output_names,
        method="standard_sat",
        metrics=None, 
        strategy_options=None,
    ):
        self.nodes = nodes
        self.output_names = output_names
        self.metrics = metrics

        self.locked_ckt0 = Circuit.from_nodes(
            nodes, output_names, key_suffix="__ckt0"
        )
        self.locked_ckt1 = Circuit.from_nodes(
            nodes, output_names, key_suffix="__ckt1"
        )
        self.miter_ckt = Circuit.miter(self.locked_ckt0, self.locked_ckt1)

        # Per-output differences between the two copies. z3 shares these terms
        # with the miter's diff signal, so they add no new circuitry.
        self.output_xors = [Xor(self.locked_ckt0.outputs()[name], self.locked_ckt1.outputs()[name])
                            for name in output_names]

        # The ordinary two-key miter, including the requirement that outputs differ.
        self.solver = Solver()
        self.solver.add(self.miter_ckt.outputs()["diff"] == True)

        # Separate feasible-key solver: ONLY previous oracle observations,
        # never the two-copy miter's output-difference condition.
        self.key_solver = Solver()

        self.method = method
        self.strategy = create_strategy(method, **(strategy_options or {}))
        self.last_selection = None

    def can_find_dip(self):
        """True when two remaining keys can be distinguished."""
        return self.solver.check() == sat

    def find_dip(self):
        """Return a DIP selected by the configured strategy."""
        return self.strategy.find_dip(self)

    def find_key(self, key_names):
        """
        Returns a key satisfying every DIP/output pair added so far; it is in
        the correct key class once no DIP remains. key_solver already holds
        those constraints, on locked_ckt0's copy of the key inputs.

        key_names: the key input names as they appear in the netlist
        """
        if self.key_solver.check() != sat:
            raise RuntimeError("No key satisfies the oracle observations")
        model = self.key_solver.model()
        key = sat_model.extract_from_model(model, [name + "__ckt0" for name in key_names], completion=True)
        return {name.removesuffix("__ckt0"): value for name, value in key.items()}

    def add_constraint(self, dip, outputs):
        """Add the observed DIP/output pair to both attack and key samplers."""
        constraint_ckt0 = Circuit.specify_inputs(
            dip, self.nodes, self.output_names, key_suffix="__ckt0"
        )
        constraint_ckt1 = Circuit.specify_inputs(
            dip, self.nodes, self.output_names, key_suffix="__ckt1"
        )

        output_constraints0 = []
        output_constraints1 = []
        for name in constraint_ckt0.outputs():
            output_constraints0.append(
                constraint_ckt0.outputs()[name] == outputs[name]
            )
            output_constraints1.append(
                constraint_ckt1.outputs()[name] == outputs[name]
            )

        self.solver.add(*output_constraints0)
        self.solver.add(*output_constraints1)
        self.key_solver.add(*output_constraints0)
