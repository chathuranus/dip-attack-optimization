
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
#   .venv/bin/python analysis/run_benchmarks.py --runs 10 --vary-seeds   # run i uses z3 seed i
#   .venv/bin/python analysis/run_benchmarks.py --skip c6288 c2670-RND1280 "*-RND1280"

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

            if metric == "oracle_queries":
                # Sample standard deviation across runs; needs at least two runs.
                row["std_oracle_queries"] = statistics.stdev(values) if len(values) >= 2 else None

        rows.append(row)

    return rows


def main():
    parser = argparse.ArgumentParser(description="Run all benchmarks with every attack method.")
    parser.add_argument("--runs", type=int, default=1,
        help="number of runs per design and method (default: 1)")
    parser.add_argument("--timeout", type=float, default=None,
        help="time limit in seconds for a single run (default: no limit)")
    parser.add_argument("--results-dir", type=Path, default=REPO_ROOT / "analysis" / "results",
        help="folder in which each invocation creates a timestamped folder (default: analysis/results)")
    parser.add_argument("--vary-seeds", action="store_true",
        help="give run i z3 seed i (0, 1, ..., runs-1); otherwise every run uses seed 0")
    parser.add_argument("--skip", nargs="+", default=[], metavar="PATTERN",
        help="circuits or designs to skip in addition to SKIP, e.g. c6288 c2670-RND1280 '*-RND1280'")
    args = parser.parse_args()

    designs = find_designs(SKIP + args.skip)
    fieldnames = ["benchmark", "method", "runs_requested", "runs_recorded", "runs_successful"]
    for metric in METRICS:
        fieldnames.append(f"mean_{metric}")
        if metric == "oracle_queries":
            fieldnames.append("std_oracle_queries")

    output_dir = args.results_dir / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    json_dir = output_dir / "attack_metrics"
    json_dir.mkdir(parents=True)

    # One bar over every design, so it shows progress through the whole invocation.
    progress = tqdm(total=sum(len(group) for group in designs.values()), desc="Benchmarks", unit="design")

    for variant in VARIANTS:
        output_csv = output_dir / f"benchmark_results_{variant}.csv"

        with output_csv.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for name, locked_file, oracle_file in designs[variant]:
                # Start each design from an empty results file so only these runs are averaged.
                metrics_file = locked_file.parent / "attack_metrics.json"
                metrics_file.unlink(missing_ok=True)

                for method in METHODS:
                    # With --vary-seeds every method uses the same seeds 0..runs-1.
                    for run in range(args.runs):
                        seed = run if args.vary_seeds else 0
                        progress.set_postfix_str(f"{name} {method} run {run + 1}/{args.runs} seed {seed}")
                        run_attack(locked_file, oracle_file, method, seed, args.timeout)

                writer.writerows(summarise(name, metrics_file, args.runs))
                # Keep the raw records, since the next invocation deletes them.
                if metrics_file.exists():
                    shutil.copy2(metrics_file, json_dir / f"{name}.json")
                # Write each design as it finishes so partial results survive an interruption.
                f.flush()
                progress.update()

    progress.close()

    print(f"Saved results to {output_dir}")


if __name__ == "__main__":
    main()
