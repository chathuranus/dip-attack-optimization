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

## Sampled-key DIP selection integration

Replace `dip_finder.py` and `dip_strategies.py` in your existing SAT attack package, and add `partitioning.py`. Keep your existing `circuit.py`, `sat_model.py`, `sat_attack.py`, and other modules. The included copies of `circuit.py`, `sat_model.py`, and `sat_attack.py` are for reference only and were not modified.

### Run

Use your existing `run.py` command-line interface with `--method partitioning` (assuming the method flag has already been integrated). `standard_sat` remains unchanged and `maxsat` is still a placeholder.

Default candidate budgets are 32 feasible keys and 8 candidate DIPs. The `DipFinder` constructor supports `partition_key_samples` and `partition_dip_candidates` to adjust them.

### Important details

* `key_solver` contains only oracle-observation constraints, not the miter's output-difference requirement.
* Temporary blocking clauses are scoped with Z3 push/pop, so they do not affect later attack iterations.
* `context.last_selection` holds the most recent selection statistics; you can copy these into your metrics collector after each successful DIP.
* The sampled keys are distinct but **not uniformly sampled**. Entropy estimates may be biased.
* `MaxSATStrategy` is not implemented.

### Validation

The Python modules compile, and the two pure-scoring unit tests pass. This environment does not have the `z3-solver` package, so the actual Z3 integration has **not** been executed end-to-end. Run on your Ubuntu setup with a small known benchmark before broader experiments.

```
python3 -m unittest test_partitioning.py -v
```
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

## Results

Comparison of the three DIP-selection methods on the 32-bit random XOR/XNOR-locked (`RND320`) benchmarks, one run per method, with default strategy options (`partitioning`: 32 key samples, 8 candidate DIPs; `maxsat`: no timeout or check cap). Every run recovered a key whose circuit is functionally equivalent to the oracle.

| Benchmark | Method | Oracle queries | SAT iterations | Mean Hamming distance | DIP generation (s) | Total runtime (s) | Equivalent |
|---|---|---|---|---|---|---|---|
| c432 | `standard_sat` | 21 | 21 | 3.67 | 0.08 | 0.65 | yes |
| c432 | `partitioning` | 12 | 12 | — | 0.32 | 0.69 | yes |
| c432 | `maxsat` | **11** | 40 | 5.73 | 0.15 | **0.51** | yes |
| c499 | `standard_sat` | 12 | 12 | 3.00 | 0.07 | **0.49** | yes |
| c499 | `partitioning` | **9** | 9 | — | 0.31 | 0.66 | yes |
| c499 | `maxsat` | 10 | 44 | 7.80 | 0.27 | 0.65 | yes |
| c880 | `standard_sat` | 6 | 6 | 2.67 | 0.04 | 0.56 | yes |
| c880 | `partitioning` | 7 | 7 | — | 0.23 | 0.80 | yes |
| c880 | `maxsat` | **4** | 22 | 10.00 | 0.08 | **0.52** | yes |
| c1355 | `standard_sat` | 13 | 13 | 1.85 | 0.15 | **1.42** | yes |
| c1355 | `partitioning` | **11** | 11 | — | 0.46 | 1.58 | yes |
| c1355 | `maxsat` | 18 | 106 | 6.94 | 2.05 | 3.64 | yes |
| c1908 | `standard_sat` | **8** | 8 | 7.25 | 0.06 | **1.37** | yes |
| c1908 | `partitioning` | 11 | 11 | — | 0.40 | 1.95 | yes |
| c1908 | `maxsat` | **8** | 26 | 19.00 | 0.28 | 1.57 | yes |
| c2670 | `standard_sat` | 23 | 23 | 2.30 | 0.24 | 3.92 | yes |
| c2670 | `partitioning` | 21 | 21 | — | 0.97 | 4.37 | yes |
| c2670 | `maxsat` | **11** | 40 | 6.18 | 0.27 | **2.49** | yes |
| c3540 | `standard_sat` | 14 | 14 | 3.29 | 0.13 | 3.74 | yes |
| c3540 | `partitioning` | 13 | 13 | — | 0.53 | 3.98 | yes |
| c3540 | `maxsat` | **9** | 57 | 7.78 | 0.72 | **3.49** | yes |
| c5315 | `standard_sat` | 12 | 12 | 2.83 | 0.24 | 5.56 | yes |
| c5315 | `partitioning` | 11 | 11 | — | 0.66 | 5.70 | yes |
| c5315 | `maxsat` | **6** | 77 | 20.50 | 1.28 | **5.00** | yes |

Bold marks the best oracle-query count and total runtime per benchmark.

How to read the columns:

- **SAT iterations** counts miter solver checks. For `maxsat` it includes the extra checks spent maximizing the Hamming distance. For `partitioning` it does *not* include the candidate-DIP and key-sampling checks (about 40 per query with the defaults), so it understates that method's solver work.
- **Mean Hamming distance** is the average number of outputs on which the two locked-circuit copies differ for the selected DIP. `partitioning` does not record it; its per-DIP selection metrics are in `partition_selections` in `attack_metrics.json`.
- **DIP generation** is time spent choosing DIPs. Most of the rest of the total runtime is shared work, mainly rebuilding the circuit for each oracle observation in `add_constraint`.

Observations:

- `maxsat` used the fewest oracle queries on 6 of 8 benchmarks and was fastest on 5. Its selected DIPs differ on 2–7× more outputs than the baseline's, and every one was proven maximal.
- c1355 is the exception: `maxsat` needed more queries than the baseline (18 vs 13) and 106 solver checks, making it 2.5× slower.
- `partitioning` was never fastest, and had the fewest queries only on c499 and c1355, by 1–2 queries. With 32 sampled keys its partition estimate is coarse.
- These are single runs at one key size. Query counts depend on which models Z3 returns and can vary noticeably between runs, so repeat each method with several solver seeds, and at 64 and 128 bits, before drawing firm conclusions.
- c7552 is not included: the parser leaves its output `N387` without a driving gate, so no method can attack it yet.

## References

- [lnestor/sat_attack](https://github.com/lnestor/sat_attack)
- [Z3](https://github.com/Z3Prover/z3)
- [ISCAS benchmark resources](https://github.com/TrustworthyComputing/hdl-benchmarks)
