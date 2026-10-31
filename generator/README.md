# Random XOR/XNOR Locked Benchmark Generator

Structural Verilog input.

**Requires:** Python 3.9+ (standard library only).

## Usage

Example:

```bash
python3 generate_locked_benchmarks.py --bench c432.v --scheme rnd --key-size 32
```

Reproducible instances:

```bash
python3 generate_locked_benchmarks.py --bench c432.v --scheme rnd --key-size 32 --seed 1 --instance 1
```

## Input formats

- **`.v` or `.sv`:** one combinational structural Verilog module with scalar `input`/`output`/`wire` declarations and built-in positional gate primitives (`and`/`or`/`nand`/`nor`/`xor`/`xnor`/`not`/`buf`).
- **`.bench`:** ISCAS-style combinational BENCH netlist (retained for compatibility).

**Unsupported:** behavioral RTL (`always`, `assign`), bus/vector declarations, flip-flops, multi-module hierarchy, cell-library gates, named-port instances, constants.
Synthesis or conversion to structural primitives is required for unsupported input formats.

## Output folder naming

```
generated_benchmarks/<design>-RND<key_size><instance>/
  <design>-RND<key_size><instance>.v
  <design>-oracle.v
  ReadMe_<design>-RND<key_size><instance>.txt
  key_metadata.json
```

## Notes

- Only `--scheme rnd` is implemented. `--scheme sll` is reserved and fails clearly.
- The key metadata is for experiment validation, **NOT** for the SAT attack.
- The generator checks correct-key equivalence with randomized vectors, not a formal proof.

## Testing status

Tested with the `c1355-oracle.v` file in the user's `c1355-SL320` example (32 key bits, 128 random vectors passed). Compatibility with the lnestor SAT attack parser has not been confirmed by execution.
