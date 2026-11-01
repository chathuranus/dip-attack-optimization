
"""Unit tests for SLL benchmark generation."""

import json
import random
import unittest

from pathlib import Path
from tempfile import TemporaryDirectory

from sll_algorithm3 import (
    sensitization_exists_exhaustive,
    select_sll,
)

from generate_locked_benchmarks import (
    evaluate,
    generate,
    parse_verilog,
)


class TestSLL(unittest.TestCase):

    def test_independent_keys_are_mutable(self):
        """Independent outputs should allow key sensitization."""

        gates = [
            ("buf", "y", ["a"]),
            ("buf", "z", ["b"]),
        ]

        self.assertTrue(
            sensitization_exists_exhaustive(
                gates,
                ["a", "b"],
                ["y", "z"],
                "y",
                "z",
            )
        )

        self.assertTrue(
            sensitization_exists_exhaustive(
                gates,
                ["a", "b"],
                ["y", "z"],
                "z",
                "y",
            )
        )

    def test_two_keys_in_and_are_nonmutable(self):
        """Two keys feeding an AND gate should interfere."""

        gates = [
            ("buf", "n1", ["a"]),
            ("buf", "n2", ["b"]),
            ("and", "y", ["n1", "n2"]),
        ]

        self.assertFalse(
            sensitization_exists_exhaustive(
                gates,
                ["a", "b"],
                ["y"],
                "n1",
                "n2",
            )
        )

        self.assertFalse(
            sensitization_exists_exhaustive(
                gates,
                ["a", "b"],
                ["y"],
                "n2",
                "n1",
            )
        )

    def test_algorithm_three_clique(self):
        """Check that the selector finds two distinct locations."""

        gates = [
            ("buf", "n1", ["a"]),
            ("buf", "n2", ["b"]),
            ("and", "y", ["n1", "n2"]),
        ]

        result = select_sll(
            gates=gates,
            inputs=["a", "b"],
            outputs=["y"],
            key_size=2,
            rng=random.Random(0),
            atpg_backend="exhaustive",
        )

        self.assertEqual(
            len(result.locations),
            2,
        )

        self.assertEqual(
            len(set(result.locations)),
            2,
        )

    def test_generator(self):
        """Generate a small locked circuit and verify its outputs."""

        with TemporaryDirectory() as tmp:
            root = Path(tmp)

            source = root / "c.v"

            source.write_text(
                """
module c(a, b, c, y, z);

input a, b, c;
output y, z;

wire n1, n2, n3;

and g1(n1, a, b);
xor g2(n2, n1, c);
nor g3(n3, a, c);

or g4(y, n2, n3);
xor g5(z, n2, n3);

endmodule
"""
            )

            folder = generate(
                path=source,
                scheme="sll",
                size=2,
                seed=0,
                instance=0,
                outdir=root / "out",
                atpg_backend="exhaustive",
            )

            metadata = json.loads(
                (
                    folder / "key_metadata.json"
                ).read_text()
            )

            original = parse_verilog(
                folder / "c-oracle.v"
            )

            locked = parse_verilog(
                folder / "c-SLJI20.v"
            )

            self.assertEqual(
                metadata["key_size"],
                2,
            )

            key = {
                f"keyinput{i}": int(bit)
                for i, bit in enumerate(
                    metadata[
                        "key_bits_in_keyinput_order"
                    ]
                )
            }

            for a in (0, 1):
                for b in (0, 1):
                    for c in (0, 1):
                        x = {
                            "a": a,
                            "b": b,
                            "c": c,
                        }

                        original_output = evaluate(
                            original[1],
                            original[2],
                            original[4],
                            x,
                        )

                        locked_output = evaluate(
                            locked[1],
                            locked[2],
                            locked[4],
                            {
                                **x,
                                **key,
                            },
                        )

                        self.assertEqual(
                            original_output,
                            locked_output,
                        )


if __name__ == "__main__":
    unittest.main()
