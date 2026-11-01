# Logic-Locking Benchmark Generator

Generate reproducible, XOR/XNOR-locked **combinational structural Verilog** benchmarks for SAT-attack experiments. The project includes a single-circuit generator and a JSON-driven batch runner.

## 1. Files

```text
benchmark_generator/
├── generate_locked_benchmarks.py   # Core locking generator
├── sll_algorithm3.py               # Experimental SLL-style placement
├── original_benchmarks/            # Input structural Verilog files
│   ├── c432.v
│   ├── c880.v
│   └── c1908.v
└── generated_benchmarks/           # Created automatically
```

Place the runner, configuration, and generator scripts together, or adjust the `generator` path in the JSON file. The batch runner calls the existing generator; it does not reimplement the locking algorithms.

## 2. Requirements

- Ubuntu/Linux or another environment with Python 3.10+.
- `z3-solver` for the SLL SAT checks (not required for random locking alone).
- Standard-library Python modules for the batch runner.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install z3-solver
```

## 3. Supported input format

Inputs must be **single-module, combinational, structural Verilog** (`.v`) using scalar `input`, `output`, and `wire` declarations and primitive `and`, `nand`, `or`, `nor`, `xor`, `xnor`, `not`, and `buf` gates. The parser topologically sorts gates and rejects combinational cycles.

Not supported directly: behavioral RTL (`always`), `assign`, buses/vectors, sequential logic, multiple modules, parameterized modules, and technology-specific standard-cell instances. Flatten/convert unsupported designs to the supported gate-level representation before generation. The input folder should contain *original, unlocked* circuits.

## 4. Locking schemes

| Scheme | CLI value | Output label | Description |
|---|---|---|---|
| Random logic locking | `rnd` | `RND` | Random XOR/XNOR key-gate insertion |
| Experimental SLL-style placement | `sll` | `SLJI` | Convergence-ranked, pairwise SAT-checked placement with optional dominance shortcut |
| SLL-style with rejected-candidate retry | `sll` plus retry option | `SLJIR` | Non-standard extension that may construct additional cliques |
| Both | `all` | Scheme-specific | Generates both variants |

**Research limitation:** The SLL implementation and its Theorem 1-inspired shortcut have not been independently validated as an exact reproduction of Yasin et al., *On Improving the Security of Logic Locking* (IEEE TCAD, 2016). In particular, `--sll-retry-rejected` is **not** part of the strict published Algorithm 3. Label and report these variants separately; do not present them as verified original SLL benchmarks.

## 5. Generate a single locked benchmark

```bash
python3 generate_locked_benchmarks.py \
  --bench original_benchmarks/c432.v \
  --scheme rnd \
  --key-size 32 \
  --seed 0 \
  --instance 0 \
  --out generated_benchmarks
```

For experimental SLL-style placement:

```bash
python3 generate_locked_benchmarks.py \
  --bench original_benchmarks/c432.v \
  --scheme sll \
  --key-size 32 \
  --seed 0 \
  --sll-retry-rejected
```

SLL placement can select fewer locations than requested. In that case the generator **skips** the configuration rather than writing a falsely labeled full-key benchmark. The dominance shortcut is enabled by default; use `--no-theorem1` to disable it.

## 6. Output files

A successful random-locking job with `c432.v`, 32 key bits, and instance 0 creates:

```text
generated_benchmarks/
├── c432-RND320/
│   ├── c432-RND320.v           # Locked structural Verilog
│   ├── c432-oracle.v           # Original circuit for oracle simulation
│   ├── ReadMe_c432-RND320.txt  # Benchmark description
│   └── key_metadata.json       # Correct key and placement metadata

```

## 6. Validation before SAT experiments

1. Run the bundled tests (in `tests/` at the repo root), from the repo root:

   ```bash
   python3 -m unittest -v
   ```

2. Start with one small random-locking instance (`c432`, 16 or 32 key bits).
3. Confirm the locked netlist has the requested number of key inputs and that the generated files parse correctly.
4. Prove **correct-key functional equivalence** between the locked circuit and the original oracle using a formal equivalence checker. The generator's 128 random-input tests are a regression check, **not a proof**.
5. Verify the SAT attack accepts the structural Verilog and can recover a functionally correct key.
6. For SLL-style experiments, compare shortcut-enabled versus direct pairwise checks and validate inferred security relations. Record clique sizes, number of cliques, and SAT check counts.
7. Only then expand to 64-/128-bit keys and multiple seeds.

The `lnestor/sat_attack` parser may require specific gate syntax or key-input naming. A successful generation does not guarantee downstream parser compatibility.

## 7. Known limitations

- Random locking is **EPIC-style XOR/XNOR locking**, not the full EPIC activation protocol.
- Experimental SLL placement is not yet independently verified as paper-faithful.
- Large SLL jobs can be slow, time out, or fail to reach the requested key size.
- The generator does not produce a technology-mapped `synt_*.v` file or require the SAED90nm library.
- Generation time is **not** SAT attack runtime. Benchmark-generation logs should be kept separate from later attack performance measurements.

## 8. Reference

M. Yasin et al., “On Improving the Security of Logic Locking,” *IEEE Transactions on Computer-Aided Design of Integrated Circuits and Systems*, vol. 35, no. 9, pp. 1411–1424, 2016.

## Live progress bar and estimated remaining time

The JSON runner displays a live terminal progress bar, the number and percentage of
completed jobs, elapsed time, estimated time remaining (ETA), and the currently
running benchmark. It refreshes while a generator subprocess is running, not only
when each job finishes. The progress bar uses only Python's standard library.

```bash
python3 run_benchmark_generation.py --config generation_config.json
```

Optional JSON setting:

```json
"progress_interval_seconds": 1.0
```

This controls how frequently the display refreshes (default: one second). The
ETA is estimated from the durations of completed generation jobs, preferring
samples with the same scheme and key size. Before any job has completed, ETA
shows `calculating...`. Since SLL SAT/ATPG costs vary considerably across
circuits, ETA is approximate and may change substantially as jobs finish.

When stdout is a terminal, the bar updates in place during the active job.
When stdout is redirected to a file or a non-interactive environment, the
runner prints a progress snapshot after each completed job instead of filling
the log with repeated updates. Generator stdout and stderr remain in the
per-job `_generation_logs/*.log` files. The runner preserves the CSV manifest,
JSON summary, skip-existing behavior, timeout enforcement, and dry-run mode.
