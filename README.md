# SAT-Based Logic-Locking Attack: DIP Selection Experiments

This project evaluates how **Distinguishing Input Pattern (DIP)** selection affects SAT-based recovery of combinational logic-locked circuits. It compares the classical SAT attack with two proposed DIP-selection strategies on the same locked netlists and oracle circuits.

## Requirements

- Ubuntu/Linux with Python 3 and Git
- Python virtual environment with `z3-solver`
- A working copy of the `lnestor/sat_attack` implementation, extended to accept `--method`
- Matching structural Verilog locked and oracle circuits

Example environment setup (adapt to your repository's dependencies):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install z3-solver
```

## Running an attack

From the SAT attack repository root, use:

```bash
python3 sat_attack/run.py \
  benchmarks/c432-RND320/c432-RND320.v \
  benchmarks/c432-RND320/c432-oracle.v \
  --method standard_sat
```

The two positional arguments are:

1. **Locked circuit:** Structural Verilog netlist containing key inputs.
2. **Oracle circuit:** Corresponding unlocked Verilog netlist used to provide correct outputs.

The optional `--method` flag chooses the DIP-selection strategy. If omitted, it defaults to `standard_sat`.

| `--method` value | DIP selection | Status |
|---|---|---|
| `standard_sat` | First valid DIP returned by the SAT solver | Baseline; existing implementation |
| `partitioning` | Select a candidate DIP with high estimated output entropy over sampled feasible keys | Planned; implement before enabling |
| `maxsat` | Maximize output Hamming distance between two feasible-key circuit copies using Z3 Optimize | Planned; implement before enabling |

**Important:** The upstream `lnestor/sat_attack` repository does not natively support this `--method` option. The examples above work only **after** updating `run.py`, the attack constructor, and the DIP finder to propagate and dispatch the flag. Until the new selectors are implemented, `partitioning` and `maxsat` should raise `NotImplementedError` rather than silently run the baseline.

### Example invocations

Standard SAT:

```bash
python3 sat_attack/run.py LOCKED.v ORACLE.v --method standard_sat
```

Sampled-key partitioning (once implemented):

```bash
python3 sat_attack/run.py LOCKED.v ORACLE.v --method partitioning
```

MaxSAT-style Hamming-distance selection (once implemented):

```bash
python3 sat_attack/run.py LOCKED.v ORACLE.v --method maxsat
```

`LOCKED.v` and `ORACLE.v` are placeholders: replace them with real paths.

## Implementing the method flag

Add the option to the existing argument parser in `sat_attack/run.py`:

```python
parser.add_argument(
    "--method",
    choices=["standard_sat", "partitioning", "maxsat"],
    default="standard_sat",
    help="DIP-selection strategy",
)
```

Pass `args.method` into the existing attack initialization, then into the DIP finder. Keep oracle querying, accumulated constraints, termination conditions, and final key validation identical across all strategies. Do not replace the repository's current constructor signatures with illustrative examples without inspecting the code.

## Recording results

For each attack run, record:

- Benchmark identifier (e.g., `c432-RND320`)
- Method (`standard_sat`, `partitioning`, or `maxsat`)
- Number of actual oracle queries
- Total wall-clock runtime
- DIP-selection / solver time
- Final status (success, timeout, or error)
- Functional equivalence of the recovered-key circuit and oracle

Initialize the metrics collector from the locked filename and selected method:

```python
from pathlib import Path

metrics = AttackMetrics(
    benchmark=Path(args.locked_file).stem,
    method=args.method,
)
```

The `args.locked_file` name is illustrative; adapt it to your parser's actual positional argument name. Count an oracle query only when an oracle evaluation occurs, not when a SAT solver call returns UNSAT. Mark success only after checking functional equivalence.

## Benchmark preparation

Generate combinational XOR/XNOR-locked structural Verilog circuits from ISCAS'85 or EPFL designs using the separate benchmark generator. Keep the generated correct key in private validation metadata, not in the SAT attack's DIP-selection inputs. Use the same locked circuit and oracle for every strategy.

For generated SLL-style instances, distinguish the strict published placement algorithm from any experimental retry extension; do not label the latter as an exact reproduction of Yasin et al. (2016).

## Suggested validation sequence

1. Verify that the original baseline attack still succeeds without `--method`.
2. Verify that `--method standard_sat` yields equivalent baseline behavior.
3. Verify that unimplemented methods fail clearly.
4. Implement and test each selector independently on small circuits.
5. Run paired experiments on identical locked/oracle pairs and compare runtime and oracle-query counts.

## References

- [lnestor/sat_attack](https://github.com/lnestor/sat_attack)
- [Z3](https://github.com/Z3Prover/z3)
- [ISCAS benchmark resources](https://github.com/TrustworthyComputing/hdl-benchmarks)
