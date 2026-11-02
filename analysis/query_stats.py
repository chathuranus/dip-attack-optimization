
# query_stats.py

# Compares MaxSAT (Hamming) against standard SAT on oracle queries and total
# runtime, using the raw records of one run_benchmarks.py invocation in
# <results_folder>/attack_metrics/. For each metric it reports, per key size,
# over the 32- and 64-bit keys together ("32+64", the key sizes in the plots),
# and over all key sizes ("all"):
#   - the average percentage reduction,
#   - the geometric mean ratio, maxsat / standard_sat (see below),
#   - for runtime, also the geometric mean speedup, standard_sat / maxsat, and
#   - the percentage of circuits improved (MaxSAT strictly lower).
# Each metric is reported twice: over all circuits, and without the circuits
# in EXCLUDED_CIRCUITS.
#
# Total runtime is the I/O-aware total (io_aware_total_runtime_seconds), i.e.
# the full bar height in runtime_breakdown.png.
#
# Each circuit is compared on the metric's mean over its successful runs.
#   - Percentage reduction: (standard_sat - maxsat) / standard_sat * 100, so a
#     negative value means MaxSAT was worse. The average is the plain mean of
#     the per-circuit values. Slowdowns are unbounded while reductions stop at
#     100%, so one bad circuit can dominate this average.
#   - Geometric mean ratio: the n-th root of the product of the per-circuit
#     maxsat / standard_sat ratios. A 2x improvement and a 2x regression cancel
#     out. Below 1x means MaxSAT is typically lower (0.68x = 68% as many
#     queries, or 68% of the time).
#   - Geometric mean speedup (runtime only): standard_sat / maxsat, exactly
#     1 / the geometric mean ratio. Above 1x means MaxSAT is typically faster
#     (1.25x = finishes in 1 / 1.25 = 80% of the time).
# A circuit counts only if both methods have at least one successful run on it
# and both values are above 0.
#
# Usage (from the repo root):
#   .venv/bin/python analysis/query_stats.py analysis/results/2026-11-02_09-45-36
#   add --details to also print the per-circuit numbers

import argparse
import json
import math
from pathlib import Path


BASELINE = "standard_sat"
CANDIDATE = "maxsat"

# (name, value of one record, also show speedup)
METRICS = [
    ("Oracle queries", lambda r: r["oracle_queries"], False),
    ("Total runtime (I/O-aware)", lambda r: r["io_aware_total_runtime_seconds"], True),
]

# Circuits left out of the second set of results.
EXCLUDED_CIRCUITS = {"c1355"}


def mean(values):
    return sum(values) / len(values)


def geometric_mean(values):
    return math.exp(mean([math.log(v) for v in values]))


def load_records(results_dir):
    """Returns {variant: {circuit: {method: [successful record, ...]}}}."""
    data = {}
    for path in (results_dir / "attack_metrics").glob("*.json"):
        circuit, variant = path.stem.rsplit("-", 1)
        with path.open() as f:
            results = json.load(f)["results"]
        for method, records in results.items():
            ok = [r for r in records if r["status"] == "success"]
            if ok:
                data.setdefault(variant, {}).setdefault(circuit, {})[method] = ok
    return data


def compare(circuits, value, exclude):
    """Per-circuit (circuit, baseline, candidate, reduction %) for circuits with both methods."""
    rows = []
    for circuit, methods in circuits.items():
        if circuit in exclude or BASELINE not in methods or CANDIDATE not in methods:
            continue
        base = mean([value(r) for r in methods[BASELINE]])
        cand = mean([value(r) for r in methods[CANDIDATE]])
        if base > 0 and cand > 0:
            rows.append((circuit, base, cand, (base - cand) / base * 100))
    return sorted(rows, key=lambda row: int(row[0].lstrip("c")))


def summary_line(label, rows, speedup):
    improved = sum(1 for _, base, cand, _ in rows if cand < base)
    avg = mean([r[3] for r in rows])
    ratio = geometric_mean([cand / base for _, base, cand, _ in rows])
    speedup_cell = f" {1 / ratio:>15.2f}x" if speedup else ""
    return (f"{label:<10} {len(rows):>8} {avg:>15.1f}% {ratio:>13.2f}x{speedup_cell} "
            f"{improved:>8}/{len(rows):<3} ({improved / len(rows) * 100:5.1f}%)")


def report(title, value, speedup, data, variants, exclude, details):
    per_variant = {variant: compare(data[variant], value, exclude) for variant in variants}

    print(f"\n=== {title} ===")
    if details:
        for variant in variants:
            print(f"\n{variant}")
            extra = f" {'speedup':>8}" if speedup else ""
            print(f"  {'circuit':<8} {'standard_sat':>12} {'maxsat':>10} {'reduction':>10} {'ratio':>8}{extra}")
            for circuit, base, cand, reduction in per_variant[variant]:
                extra = f" {base / cand:>7.2f}x" if speedup else ""
                print(f"  {circuit:<8} {base:>12.2f} {cand:>10.2f} {reduction:>9.1f}% {cand / base:>7.2f}x{extra}")
        print()

    extra = f" {'geomean speedup':>16}" if speedup else ""
    print(f"{'variant':<10} {'circuits':>8} {'avg reduction':>16} {'geomean ratio':>14}{extra} {'circuits improved':>21}")
    for variant in variants:
        if per_variant[variant]:
            print(summary_line(variant, per_variant[variant], speedup))
    # 32- and 64-bit keys only, matching the key sizes in the plots.
    small_rows = [row for variant in ("RND320", "RND640") for row in per_variant.get(variant, [])]
    if small_rows:
        print(summary_line("32+64", small_rows, speedup))
    all_rows = [row for variant in variants for row in per_variant[variant]]
    if all_rows:
        print(summary_line("all", all_rows, speedup))


def main():
    parser = argparse.ArgumentParser(description="Oracle query and runtime statistics: MaxSAT vs standard SAT.")
    parser.add_argument("results_dir", type=Path,
        help="timestamped folder created by run_benchmarks.py, e.g. analysis/results/2026-11-02_09-45-36")
    parser.add_argument("--details", action="store_true",
        help="also print the per-circuit numbers")
    args = parser.parse_args()

    if not (args.results_dir / "attack_metrics").is_dir():
        parser.error(f"{args.results_dir} has no attack_metrics/ folder")

    data = load_records(args.results_dir)
    variants = sorted(
        (v for v, circuits in data.items()
         if any(BASELINE in m and CANDIDATE in m for m in circuits.values())),
        key=lambda v: int("".join(ch for ch in v if ch.isdigit())),
    )
    if not variants:
        parser.error(f"No circuit has successful runs of both {BASELINE} and {CANDIDATE}")

    without = ", ".join(sorted(EXCLUDED_CIRCUITS, key=lambda c: int(c.lstrip("c"))))
    for name, value, speedup in METRICS:
        report(name, value, speedup, data, variants, set(), args.details)
        report(f"{name}, without {without}", value, speedup,
               data, variants, EXCLUDED_CIRCUITS, args.details)


if __name__ == "__main__":
    main()
