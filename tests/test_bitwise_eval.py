import itertools
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from z3 import Bool, BoolVal, is_true, simplify, substitute

import benchmarks
from bitwise_eval import evaluate_packed, gate_order
from circuit import Circuit

# Every gate type the parser produces, with reconvergent fanout and a key.
NETLIST = """module t(a, b, c, keyinput0, y, z);
  input a, b, c, keyinput0;
  output y, z;
  wire n1, n2, n3, n4, n5, n6;
  and g0(n1, a, b);
  or g1(n2, n1, c);
  nand g2(n3, n2, a);
  nor g3(n4, n3, b);
  xor g4(n5, n4, keyinput0);
  not g5(n6, n5);
  xnor g6(y, n6, n1);
  and g7(z, n3, n5);
endmodule
"""


class TestBitwiseEval(unittest.TestCase):
    def test_matches_z3_on_every_assignment(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.v"
            path.write_text(NETLIST)
            nodes, outputs = benchmarks.read_nodes(path)
        ckt = Circuit.from_nodes(nodes, outputs)
        names = ["a", "b", "c", "keyinput0"]
        rows = list(itertools.product([False, True], repeat=len(names)))

        # One lane per row of the truth table, all evaluated in one pass.
        mask = (1 << len(rows)) - 1
        packed_inputs = {
            name: sum(1 << i for i, row in enumerate(rows) if row[j])
            for j, name in enumerate(names)
        }
        packed = evaluate_packed(nodes, gate_order(nodes, outputs), outputs, packed_inputs, mask)

        for i, row in enumerate(rows):
            subs = [(Bool(n), BoolVal(v)) for n, v in zip(names, row)]
            for out in outputs:
                expected = is_true(simplify(substitute(ckt.outputs()[out], *subs)))
                self.assertEqual(bool(packed[out] >> i & 1), expected, (row, out))


if __name__ == "__main__":
    unittest.main()
