from z3 import *

from circuit import Circuit

from dip_strategies import create_strategy

class DipFinder:
    def __init__(self, nodes, output_names, method="standard_sat"):
        self.nodes = nodes
        self.output_names = output_names

        self.locked_ckt0 = Circuit.from_nodes(nodes, output_names, key_suffix = "__ckt0")
        self.locked_ckt1 = Circuit.from_nodes(nodes, output_names, key_suffix = "__ckt1")
        self.miter_ckt = Circuit.miter(self.locked_ckt0, self.locked_ckt1)

        self.solver = Solver()
        self.solver.add(self.miter_ckt.outputs()["diff"] == True)

        self.method = method
        self.strategy = create_strategy(method)

    def can_find_dip(self):
        """Returns if a dip can be found given the current constraints"""
        return self.solver.check() == sat

    def find_dip(self):
        """Returns a dip for the circuit given the current constraints"""
        return self.strategy.find_dip(self)

    def add_constraint(self, dip, outputs):
        """
        Adds a new dip/output constraint to the SAT solver.

        dip: the DIP for the constraint
        outputs: the oracle outputs for the DIP passed in
        """
        constraint_ckt0 = Circuit.specify_inputs(dip, self.nodes, self.output_names, key_suffix = "__ckt0")
        constraint_ckt1 = Circuit.specify_inputs(dip, self.nodes, self.output_names, key_suffix = "__ckt1")

        output_constraints0 = []
        output_constraints1 = []

        for name in constraint_ckt0.outputs():
            output_constraints0.append(constraint_ckt0.outputs()[name] == outputs[name])
            output_constraints1.append(constraint_ckt1.outputs()[name] == outputs[name])

        self.solver.add(*output_constraints0)
        self.solver.add(*output_constraints1)
