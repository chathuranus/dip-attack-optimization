
# run_benchmarks.py

# Runs every design in benchmarks/ with every attack method, repeated
# several times, and saves the mean of the selected metrics to a CSV.
# Each invocation writes to its own timestamped folder in analysis/results/:
# one CSV per key-size variant, run in the order of VARIANTS, plus a copy of
# every design's raw attack_metrics.json in an attack_metrics/ subfolder.
#
# Usage (from the repo root):
#   .venv/bin/python analysis/run_benchmarks.py
#   .venv/bin/python analysis/run_benchmarks.py --runs 10 --timeout 600
#   .venv/bin/python analysis/run_benchmarks.py --runs 10                # run i uses z3 seed i
#   .venv/bin/python analysis/run_benchmarks.py --runs 10 --fixed-seed   # every run uses seed 0
#   .venv/bin/python analysis/run_benchmarks.py --skip c6288 c2670-RND1280 "*-RND1280"
#   .venv/bin/python analysis/run_benchmarks.py --runs 10 --resume analysis/results/2026-11-02_09-45-36

import argparse
import csv
import json
import shutil
import statistics
import subprocess
import sys
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path

from tqdm import tqdm


REPO_ROOT = Path(__file__).resolve().parent.parent
BENCHMARKS_DIR = REPO_ROOT / "benchmarks"
SAT_ATTACK_DIR = REPO_ROOT / "sat_attack"

METHODS = ["standard_sat", "maxsat"] # "partitioning"

# Designs never run. A pattern matches a circuit (c6288 skips all its key
# sizes) or a full folder name (c2670-RND1280), and may use * and ?.
# --skip adds more patterns for one invocation.
SKIP = ["c6288", "c7552"]

# Key-size variants, run and saved separately in this order.
VARIANTS = ["RND320", "RND640", "RND1280"]

METRICS = [
    "io_aware_total_runtime_seconds",
    "oracle_queries",
    "sat_iterations",
    "io_aware_oracle_seconds",
]


def is_skipped(folder_name, patterns):
    circuit = folder_name.split("-")[0]
    return any(fnmatch(folder_name, pattern) or fnmatch(circuit, pattern) for pattern in patterns)


def find_designs(skip_patterns):
    """Returns {variant: [(name, locked_file, oracle_file), ...]}, smallest circuit first."""
    designs = {variant: [] for variant in VARIANTS}
    skipped = []

    # Sort c432 before c1355 by circuit number rather than alphabetically.
    folders = sorted(
        (folder for folder in BENCHMARKS_DIR.iterdir() if folder.is_dir()),
        key=lambda folder: int(folder.name.split("-")[0].lstrip("c")),
    )
    for folder in folders:
        if is_skipped(folder.name, skip_patterns):
            skipped.append(folder.name)
            continue

        variant = folder.name.split("-")[-1]
        if variant not in designs:
            tqdm.write(f"Skipping {folder.name}: unknown variant {variant}")
            continue

        locked_file = folder / f"{folder.name}.v"
        oracle_files = list(folder.glob("*-oracle.v"))

        if not locked_file.exists() or len(oracle_files) != 1:
            tqdm.write(f"Skipping {folder.name}: locked or oracle file not found")
            continue

        designs[variant].append((folder.name, locked_file, oracle_files[0]))

    if skipped:
        tqdm.write(f"Skipping {len(skipped)} design(s): {', '.join(skipped)}")

    return designs


def run_attack(locked_file, oracle_file, method, seed, timeout):
    """Runs one attack. Returns True if run.py exited normally."""
    try:
        result = subprocess.run(
            [sys.executable, "run.py", str(locked_file), str(oracle_file), "--method", method,
             "--seed", str(seed)],
            cwd=SAT_ATTACK_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        tqdm.write(f"  {locked_file.stem} {method} seed {seed}: timed out after {timeout} s")
        return False

    if result.returncode != 0:
        tqdm.write(f"  {locked_file.stem} {method} seed {seed}: exited with code {result.returncode}")
        tqdm.write(result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "")
        return False

    return True


def summarise(name, metrics_file, runs):
    """Returns one CSV row per method with the mean of each metric."""
    if metrics_file.exists():
        with metrics_file.open() as f:
            results = json.load(f)["results"]
    else:
        results = {}

    rows = []
    for method in METHODS:
        records = results.get(method, [])
        row = {
            "benchmark": name,
            "method": method,
            "runs_requested": runs,
            "runs_recorded": len(records),
            "runs_successful": sum(1 for r in records if r["status"] == "success"),
        }

        for metric in METRICS:
            values = [r[metric] for r in records if r.get(metric) is not None]
            row[f"mean_{metric}"] = sum(values) / len(values) if values else None
            # Sample standard deviation across runs; needs at least two runs.
            row[f"std_{metric}"] = statistics.stdev(values) if len(values) >= 2 else None

        rows.append(row)

    return rows


def load_completed(output_dir):
    """Returns {variant: [row, ...]} for designs an earlier invocation finished in output_dir.

    A design counts as finished only if it has both rows in its CSV and a copy of its
    raw metrics, so a design interrupted partway is dropped and run again.
    """
    saved_json = {path.stem for path in (output_dir / "attack_metrics").glob("*.json")}
    completed = {}

    for variant in VARIANTS:
        output_csv = output_dir / f"benchmark_results_{variant}.csv"
        rows = []
        if output_csv.exists():
            with output_csv.open(newline="") as f:
                # A row cut short by an interruption is missing its last columns (read as None).
                rows = [row for row in csv.DictReader(f)
                        if row["benchmark"] in saved_json and None not in row.values()]

        # Keep a design only if every method has a row, in case the last write was cut off.
        methods_by_design = {}
        for row in rows:
            methods_by_design.setdefault(row["benchmark"], set()).add(row["method"])
        finished = {name for name, methods in methods_by_design.items() if methods >= set(METHODS)}
        completed[variant] = [row for row in rows if row["benchmark"] in finished]

    return completed


def main():
    parser = argparse.ArgumentParser(description="Run all benchmarks with every attack method.")
    parser.add_argument("--runs", type=int, default=1,
        help="number of runs per design and method (default: 1)")
    parser.add_argument("--timeout", type=float, default=None,
        help="time limit in seconds for a single run (default: no limit)")
    parser.add_argument("--results-dir", type=Path, default=REPO_ROOT / "analysis" / "results",
        help="folder in which each invocation creates a timestamped folder (default: analysis/results)")
    parser.add_argument("--fixed-seed", action="store_true",
        help="run every repeat with z3 seed 0; by default run i uses seed i (0, 1, ..., runs-1)")
    parser.add_argument("--skip", nargs="+", default=[], metavar="PATTERN",
        help="circuits or designs to skip in addition to SKIP, e.g. c6288 c2670-RND1280 '*-RND1280'")
    parser.add_argument("--resume", type=Path, default=None, metavar="DIR",
        help="continue an earlier invocation's results folder, running only the designs it has not finished")
    args = parser.parse_args()

    designs = find_designs(SKIP + args.skip)
    fieldnames = ["benchmark", "method", "runs_requested", "runs_recorded", "runs_successful"]
    for metric in METRICS:
        fieldnames.append(f"mean_{metric}")
        fieldnames.append(f"std_{metric}")

    if args.resume:
        output_dir = args.resume
        if not output_dir.is_dir():
            parser.error(f"--resume folder not found: {output_dir}")
        completed = load_completed(output_dir)
    else:
        output_dir = args.results_dir / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        completed = {variant: [] for variant in VARIANTS}
    json_dir = output_dir / "attack_metrics"
    json_dir.mkdir(parents=True, exist_ok=bool(args.resume))

    if args.resume:
        done = {row["benchmark"] for rows in completed.values() for row in rows}
        if done:
            tqdm.write(f"Resuming: {len(done)} design(s) already done")
        for variant in VARIANTS:
            designs[variant] = [design for design in designs[variant] if design[0] not in done]

        # Averages over different numbers of runs should not end up in the same CSV.
        previous_runs = {int(row["runs_requested"]) for rows in completed.values() for row in rows}
        if previous_runs - {args.runs}:
            tqdm.write(f"Warning: earlier results used --runs {sorted(previous_runs)}, "
                       f"this invocation uses --runs {args.runs}")

    # One bar over every design, so it shows progress through the whole invocation.
    progress = tqdm(total=sum(len(group) for group in designs.values()), desc="Benchmarks", unit="design")

    for variant in VARIANTS:
        output_csv = output_dir / f"benchmark_results_{variant}.csv"

        with output_csv.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            # Rewrite the finished designs from an earlier invocation, dropping partial rows.
            writer.writerows(completed[variant])

            for name, locked_file, oracle_file in designs[variant]:
                # Start each design from an empty results file so only these runs are averaged.
                metrics_file = locked_file.parent / "attack_metrics.json"
                metrics_file.unlink(missing_ok=True)

                for method in METHODS:
                    # Every method uses the same seeds 0..runs-1, unless --fixed-seed.
                    for run in range(args.runs):
                        seed = 0 if args.fixed_seed else run
                        progress.set_postfix_str(f"{name} {method} run {run + 1}/{args.runs} seed {seed}")
                        run_attack(locked_file, oracle_file, method, seed, args.timeout)

                writer.writerows(summarise(name, metrics_file, args.runs))
                # Write each design as it finishes so partial results survive an interruption.
                f.flush()
                # Keep the raw records, since the next invocation deletes them. Copied after
                # the rows are flushed, as --resume treats this file as the design being done.
                if metrics_file.exists():
                    shutil.copy2(metrics_file, json_dir / f"{name}.json")
                else:
                    # Every run failed or timed out; still mark the design as done.
                    (json_dir / f"{name}.json").write_text(json.dumps({"benchmark": name, "results": {}}, indent=2))
                progress.update()

    progress.close()

    print(f"Saved results to {output_dir}")


if __name__ == "__main__":
    main()
