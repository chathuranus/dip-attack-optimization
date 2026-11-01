import time

import z3

import benchmarks
import circuit
import dip_finder
import oracle_runner

class SatAttack:
    """The main class for conducting the SAT attack."""

    def __init__(self, locked_filename, unlocked_filename, method="standard_sat", metrics=None, strategy_options=None):
        self.locked_filename = locked_filename
        self.unlocked_filename = unlocked_filename
        self.method = method
        self.metrics = metrics
        self.strategy_options = strategy_options
        self.iterations = 0

    def run(self):
        """Run the SAT attack."""
        print("Reading in locked circuit...")
        self.nodes, self.output_names = benchmarks.read_nodes(self.locked_filename)

        print("Reading in unlocked circuit...")
        self.oracle_ckt = benchmarks.read_ckt(self.unlocked_filename)

        key_inputs = [node.name for node in self.nodes.values() if node.type == "Key Input"]
        primary_inputs = [node.name for node in self.nodes.values() if node.type == "Primary Input"]

        print("\n# Primary Inputs: %i" % (len(primary_inputs)))
        print("# Key Inputs: %i" % (len(key_inputs)))

        if self.metrics is not None:
            self.metrics.num_primary_inputs = len(primary_inputs)
            self.metrics.num_outputs = len(self.output_names)

        finder = dip_finder.DipFinder(self.nodes, self.output_names, method=self.method,
                                      metrics=self.metrics, strategy_options=self.strategy_options)
        runner = oracle_runner.OracleRunner(self.oracle_ckt)

        while True:
            # DIP generation covers the satisfiability check and the strategy's
            # DIP selection. The final unsat check yields no DIP, so it is recorded separately.
            dip_start = time.perf_counter()
            if not finder.can_find_dip():
                if self.metrics is not None:
                    self.metrics.record_final_dip_check(time.perf_counter() - dip_start)
                break
            if self.metrics is not None:
                self.metrics.record_iteration()
            dip = finder.find_dip()
            if self.metrics is not None:
                self.metrics.record_dip(time.perf_counter() - dip_start)

            oracle_start = time.perf_counter()
            oracle_output = runner.run(dip)
            if self.metrics is not None:
                self.metrics.record_oracle(time.perf_counter() - oracle_start)

            finder.add_constraint(dip, oracle_output)
            self.iterations += 1

        key = finder.find_key(key_inputs)
        expected_key = benchmarks.get_expected_key(self.locked_filename)

        print("\nExpected key: %s" % (self._key_string(expected_key)))
        print("Found key:    %s" % (self._key_string(key)))

        print("\nChecking for circuit equivalence...\n")
        # self._check_key(key)
        if self._check_key(key):
            print("Locked and unlocked circuits match")
            return True
        else:
            print("Key found does not match oracle")
            return False

    def _check_key(self, key):
        """
        Check that the key returned from the SAT attack is correct. It
        does this by creating a miter circuit with a locked version
        and an oracle. If the diff signal returned from the miter circuit
        cannot be True, then the circuits are equivalent.

        key: the key returned from the SAT attaack
        """

        locked_ckt = circuit.Circuit.specify_inputs(key, self.nodes, self.output_names)
        miter = circuit.Circuit.miter(locked_ckt, self.oracle_ckt)

        s = z3.Solver()
        s.add(miter.outputs()["diff"] == True)

        return s.check() == z3.unsat

    def _key_string(self, key):
        ordered_names = sorted(key.keys(), key=lambda name: int(name[8:]))
        key_string = ""

        for name in ordered_names:
            if key[name]:
                key_string += "1"
            else:
                key_string += "0"

        return key_string




