
# presentation_graphs.py

# Draws the graphs G1-G10 specified in docs/presentation/slides_script.md from
# one run_benchmarks.py invocation, and writes a summary table of the headline
# numbers. Figures go to <results_folder>/presentation/, sized for 16:9 slides.
# G1 and G3 are the existing plots from analyze_benchmark_results.py.
#
# Usage (from the repo root):
#   .venv/bin/python analysis/presentation_graphs.py analysis/results/2026-11-02_12-28-22

import argparse
import math
import statistics
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter, NullFormatter

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_benchmark_results as abr
from analyze_benchmark_results import (
    GRID, INK, INK_MUTED, INK_SECONDARY, METHOD_COLORS, METHOD_LABELS, SURFACE,
    VARIANT_TITLES, VARIANTS, load_records, mean, style_axes,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sat_attack"))
from io_model import T_RT


# Presentation order: baseline first, then the two proposals.
METHODS = ["standard_sat", "partitioning", "maxsat"]
BASELINE_METHOD = "standard_sat"
KEY_BITS = {"RND320": 32, "RND640": 64, "RND1280": 128}

# G6: per-query latencies to sweep, in seconds (0.1 ms to 1 s).
LATENCIES = [10 ** (e / 4) for e in range(-16, 1)]

# G8: circuits whose partitioning runs are traced iteration by iteration.
TRACE_CIRCUITS = ["c432", "c1355", "c2670"]

# G9: partition scoring time on c432-RND320 before and after the bit-parallel
# evaluator (commit e44cb2e), measured with cProfile; not part of run_benchmarks output.
SCORING_BEFORE_SECONDS = 31.8
SCORING_AFTER_SECONDS = 0.03

SLIDE_SIZE = (12, 6.75)


def records_of(data, variant, circuit, method):
    return data[variant].get(circuit, {}).get(method, [])


def metric_mean(data, variant, circuit, method, key):
    values = [r[key] for r in records_of(data, variant, circuit, method) if r.get(key) is not None]
    return mean(values)


def methods_in(data):
    return [m for m in METHODS if any(records_of(data, v, c, m) for v in VARIANTS for c in data[v])]


def circuits_in(data, variant):
    return sorted(data[variant], key=lambda name: int(name.lstrip("c")))


def complete_circuits(data, variant, methods):
    """
    Circuits where every method recorded every run, so sums compare like with
    like. Timed-out runs leave no record, and dropping them would favour the
    method that timed out.
    """
    circuits = circuits_in(data, variant)
    runs = max((len(records_of(data, variant, c, m)) for c in circuits for m in methods), default=0)
    return [c for c in circuits if all(len(records_of(data, variant, c, m)) == runs for m in methods)]


def solver_checks(record):
    """
    Solver checks spent choosing DIPs. For partitioning, sat_iterations omits
    the sampling checks: per DIP, candidate_dips - 1 miter checks (the first
    candidate reuses the existing model) and candidate_keys key-solver checks.
    The extra unsat check that ends a short enumeration is not counted, so this is a lower bound.
    """
    sampling = sum(s["candidate_dips"] - 1 + s["candidate_keys"] for s in record.get("partition_selections") or [])
    return record["sat_iterations"] + sampling


def plain_log(ax):
    """Log y-axis with plain tick labels (0.6, 20) instead of 6×10⁻¹."""
    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}"))
    ax.yaxis.set_minor_formatter(NullFormatter())


def geometric_mean(values):
    return math.exp(sum(math.log(v) for v in values) / len(values)) if values else None


def legend(fig, methods, **kwargs):
    handles = [Line2D([], [], color=METHOD_COLORS[m], marker="o", linestyle="-", label=METHOD_LABELS[m])
               for m in methods]
    fig.legend(handles=handles, loc="upper center", ncol=len(methods), frameon=False,
               labelcolor=INK_SECONDARY, **kwargs)


def finish(fig, title, output_path, top=0.88):
    fig.suptitle(title, x=0.01, ha="left", color=INK, fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, top))
    fig.savefig(output_path, dpi=200, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)
    print(f"  {output_path.name}")


def variant_axes(data, sharey=False):
    variants = [v for v in VARIANTS if data[v]]
    fig, axes = plt.subplots(1, len(variants), figsize=SLIDE_SIZE, facecolor=SURFACE,
                             squeeze=False, sharey=sharey)
    return fig, list(zip(axes[0], variants))


def plot_query_ratio(data, methods, output_path):
    """G2: oracle queries relative to standard_sat, per circuit, log scale."""
    proposals = [m for m in methods if m != BASELINE_METHOD]
    fig, panels = variant_axes(data, sharey=True)

    for ax, variant in panels:
        style_axes(ax)
        circuits = complete_circuits(data, variant, methods)
        offsets = {m: (i - (len(proposals) - 1) / 2) * 0.25 for i, m in enumerate(proposals)}
        for method in proposals:
            ratios = [metric_mean(data, variant, c, method, "oracle_queries")
                      / metric_mean(data, variant, c, BASELINE_METHOD, "oracle_queries") for c in circuits]
            xs = [x + offsets[method] for x in range(len(circuits))]
            ax.scatter(xs, ratios, color=METHOD_COLORS[method], s=36, zorder=3)
            ax.vlines(xs, 1, ratios, color=METHOD_COLORS[method], linewidth=2, zorder=2)
            # Geometric mean, the fair average for ratios, at the right edge.
            gm = geometric_mean(ratios)
            ax.scatter([len(circuits) + offsets[method]], [gm], color=METHOD_COLORS[method], marker="D", s=50, zorder=3)
            ax.annotate(f"{gm:.2f}", (len(circuits) + offsets[method], gm), textcoords="offset points",
                        xytext=(0, 7), ha="center", fontsize=8, color=METHOD_COLORS[method])

        ax.axhline(1, color=INK_MUTED, linewidth=1, linestyle="--")
        plain_log(ax)
        ax.set_xticks(range(len(circuits) + 1), circuits + ["geo\nmean"], rotation=45, fontsize=8)
        ax.set_title(VARIANT_TITLES[variant], loc="left", color=INK, fontsize=11)

    panels[0][0].set_ylabel("Oracle queries / Standard SAT (log)", color=INK_SECONDARY)
    legend(fig, proposals, bbox_to_anchor=(0.5, 0.93))
    finish(fig, "G2: Query ratio vs Standard SAT (below 1 = fewer queries)", output_path)


def plot_checks_vs_queries(data, methods, output_path):
    """G4: solver checks against oracle queries; lines join one circuit's methods."""
    fig, panels = variant_axes(data)

    for ax, variant in panels:
        style_axes(ax)
        ax.grid(axis="x", color=GRID, linewidth=1)
        for circuit in complete_circuits(data, variant, methods):
            points = []
            for method in methods:
                records = records_of(data, variant, circuit, method)
                points.append((mean([r["oracle_queries"] for r in records]),
                               mean([solver_checks(r) for r in records]), method))
            ax.plot([p[0] for p in points], [p[1] for p in points], color=GRID, linewidth=1, zorder=1)
            for queries, checks, method in points:
                ax.scatter(queries, checks, color=METHOD_COLORS[method], s=30, zorder=2)
            # Label each circuit once, at its baseline point.
            ax.annotate(circuit, points[0][:2], textcoords="offset points", xytext=(4, -3), fontsize=7, color=INK_MUTED)

        plain_log(ax)
        ax.set_xlabel("Oracle queries (mean)", color=INK_SECONDARY)
        ax.set_title(VARIANT_TITLES[variant], loc="left", color=INK, fontsize=11)

    panels[0][0].set_ylabel("Solver checks for DIP selection (mean)", color=INK_SECONDARY)
    legend(fig, methods, bbox_to_anchor=(0.5, 0.93))
    finish(fig, "G4: Solver checks vs oracle queries (partitioning includes its sampling checks)", output_path)


def plot_hamming(data, methods, output_path):
    """G5: mean output Hamming distance per DIP. Partitioning does not record it."""
    compared = [m for m in methods if m in ("standard_sat", "maxsat")]
    fig, panels = variant_axes(data)
    width = 0.8 / len(compared)

    for ax, variant in panels:
        style_axes(ax)
        circuits = complete_circuits(data, variant, compared)
        for i, method in enumerate(compared):
            for x, circuit in enumerate(circuits):
                distances = [d for r in records_of(data, variant, circuit, method) for d in r["hamming_distances"]]
                ax.bar(x - 0.4 + width * (i + 0.5), mean(distances), width * 0.9, color=METHOD_COLORS[method])
        if len(compared) == 2:
            for x, circuit in enumerate(circuits):
                base, best = (mean([d for r in records_of(data, variant, circuit, m) for d in r["hamming_distances"]])
                              for m in compared)
                ax.annotate(f"{best / base:.1f}×", (x, max(base, best)), textcoords="offset points",
                            xytext=(0, 3), ha="center", fontsize=7, color=INK_SECONDARY)
        ax.set_xticks(range(len(circuits)), circuits, rotation=45, fontsize=8)
        ax.set_title(VARIANT_TITLES[variant], loc="left", color=INK, fontsize=11)

    panels[0][0].set_ylabel("Outputs differing per DIP (mean)", color=INK_SECONDARY)
    legend(fig, compared, bbox_to_anchor=(0.5, 0.93))
    finish(fig, "G5: Outputs on which the two key copies differ, per DIP (label: MaxSAT / Standard)", output_path)


def plot_latency_sensitivity(data, methods, output_path):
    """G6: summed runtime when each oracle query costs a given latency."""
    fig, panels = variant_axes(data)

    for ax, variant in panels:
        style_axes(ax)
        ax.grid(axis="x", color=GRID, linewidth=1)
        circuits = complete_circuits(data, variant, methods)
        for method in methods:
            totals = []
            for latency in LATENCIES:
                total = 0.0
                for circuit in circuits:
                    records = records_of(data, variant, circuit, method)
                    # Measured runtime plus the modelled I/O with T_rt swapped for this latency.
                    total += mean([r["total_runtime_seconds"] + r["io_aware_oracle_seconds"]
                                   + r["oracle_queries"] * (latency - T_RT) for r in records])
                totals.append(total)
            ax.plot(LATENCIES, totals, color=METHOD_COLORS[method], linewidth=2)

        ax.axvline(T_RT, color=INK_MUTED, linestyle="--", linewidth=1)
        ax.annotate("JTAG/USB model\n(2 ms)", (T_RT, ax.get_ylim()[1]), textcoords="offset points",
                    xytext=(4, -24), fontsize=7, color=INK_MUTED)
        ax.set_xscale("log")
        plain_log(ax)
        ax.set_xlabel("Latency per oracle query (s)", color=INK_SECONDARY)
        ax.set_title(f"{VARIANT_TITLES[variant]}, {len(circuits)} circuits", loc="left", color=INK, fontsize=11)

    panels[0][0].set_ylabel("Total I/O-aware runtime, summed (s)", color=INK_SECONDARY)
    legend(fig, methods, bbox_to_anchor=(0.5, 0.93))
    finish(fig, "G6: Total runtime as the per-query oracle latency grows", output_path)


def plot_key_size_scaling(data, methods, output_path):
    """G7: oracle queries against key size, one small panel per circuit."""
    circuits = sorted({c for v in VARIANTS for c in data[v]}, key=lambda name: int(name.lstrip("c")))
    ncols = 4
    nrows = math.ceil(len(circuits) / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=SLIDE_SIZE, facecolor=SURFACE, squeeze=False)

    for ax, circuit in zip(axes.flat, circuits):
        style_axes(ax)
        for method in methods:
            points = [(KEY_BITS[v], metric_mean(data, v, circuit, method, "oracle_queries")) for v in VARIANTS]
            points = [(bits, q) for bits, q in points if q is not None]
            ax.plot([p[0] for p in points], [p[1] for p in points], color=METHOD_COLORS[method],
                    marker="o", markersize=4, linewidth=1.5)
        ax.set_xscale("log", base=2)
        ax.set_xticks(list(KEY_BITS.values()), [str(b) for b in KEY_BITS.values()], fontsize=8)
        ax.set_title(circuit, loc="left", color=INK, fontsize=10)
    for ax in list(axes.flat)[len(circuits):]:
        ax.set_visible(False)
    for row in axes:
        row[0].set_ylabel("Oracle queries", color=INK_SECONDARY, fontsize=9)
    for ax in axes[-1]:
        ax.set_xlabel("Key bits", color=INK_SECONDARY, fontsize=9)

    legend(fig, methods, bbox_to_anchor=(0.5, 0.93))
    finish(fig, "G7: Oracle queries as the key grows (mean over seeds)", output_path)


def plot_partition_trace(data, variant, output_path):
    """G8: selected DIP entropy per iteration, against its log2(sampled keys) ceiling."""
    circuits = [c for c in TRACE_CIRCUITS if records_of(data, variant, c, "partitioning")]
    if not circuits:
        print(f"  skipped {output_path.name}: no partitioning records for {TRACE_CIRCUITS} in {variant}")
        return
    fig, axes = plt.subplots(1, len(circuits), figsize=SLIDE_SIZE, facecolor=SURFACE, squeeze=False, sharey=True)

    for ax, circuit in zip(axes[0], circuits):
        style_axes(ax)
        # One run, so iterations line up; the lowest seed is the reproducible choice.
        record = min(records_of(data, variant, circuit, "partitioning"), key=lambda r: r["solver_seed"] or 0)
        selections = record["partition_selections"]
        iterations = range(1, len(selections) + 1)
        ax.plot(iterations, [s["selected_dip_entropy"] for s in selections],
                color=METHOD_COLORS["partitioning"], marker="o", markersize=3, linewidth=2)
        ax.plot(iterations, [math.log2(s["candidate_keys"]) for s in selections],
                color=INK_MUTED, linestyle="--", linewidth=1)
        ax.set_xlabel("Attack iteration", color=INK_SECONDARY)
        ax.set_title(f"{circuit}-{variant} (seed {record['solver_seed']})", loc="left", color=INK, fontsize=10)

    axes[0][0].set_ylabel("Entropy of selected DIP (bits)", color=INK_SECONDARY)
    handles = [Line2D([], [], color=METHOD_COLORS["partitioning"], marker="o", label="Selected DIP entropy"),
               Line2D([], [], color=INK_MUTED, linestyle="--", label="Ceiling: log2(sampled keys)")]
    fig.legend(handles=handles, loc="upper center", ncol=2, frameon=False, labelcolor=INK_SECONDARY,
               bbox_to_anchor=(0.5, 0.93))
    finish(fig, "G8: Entropy of the DIP partitioning selects, against its log2(sampled keys) ceiling", output_path)


def plot_scoring_speedup(output_path):
    """G9: partition scoring before and after the bit-parallel evaluator."""
    fig, ax = plt.subplots(figsize=(12, 3.5), facecolor=SURFACE)
    style_axes(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=1)
    labels = ["z3 substitute + simplify", "Bit-parallel evaluator"]
    values = [SCORING_BEFORE_SECONDS, SCORING_AFTER_SECONDS]
    ax.barh(labels, values, color=[INK_MUTED, METHOD_COLORS["partitioning"]], height=0.5)
    for y, value in enumerate(values):
        ax.annotate(f"{value:g} s", (value, y), textcoords="offset points", xytext=(5, -3), fontsize=10, color=INK)
    ax.set_xscale("log")
    ax.invert_yaxis()
    ax.set_xlabel("Partition scoring time over one c432-RND320 attack (s, log)", color=INK_SECONDARY)
    finish(fig, f"G9: Bit-parallel evaluation made scoring {SCORING_BEFORE_SECONDS / SCORING_AFTER_SECONDS:,.0f}× faster",
           output_path, top=0.9)


def plot_seed_spread(data, methods, output_path):
    """G10: oracle queries of every seed, with the mean, per circuit and method."""
    fig, axes = plt.subplots(len([v for v in VARIANTS if data[v]]), 1, figsize=(12, 9), facecolor=SURFACE, squeeze=False)
    width = 0.8 / len(methods)

    for ax, variant in zip(axes[:, 0], [v for v in VARIANTS if data[v]]):
        style_axes(ax)
        circuits = circuits_in(data, variant)
        for i, method in enumerate(methods):
            for x, circuit in enumerate(circuits):
                values = [r["oracle_queries"] for r in records_of(data, variant, circuit, method)]
                if not values:
                    continue
                position = x - 0.4 + width * (i + 0.5)
                ax.scatter([position] * len(values), values, color=METHOD_COLORS[method], s=12, alpha=0.6, zorder=2)
                ax.hlines(mean(values), position - width * 0.4, position + width * 0.4,
                          color=METHOD_COLORS[method], linewidth=2, zorder=3)
        ax.set_xticks(range(len(circuits)), circuits, fontsize=8)
        ax.set_title(VARIANT_TITLES[variant], loc="left", color=INK, fontsize=10)
        ax.set_ylabel("Oracle queries", color=INK_SECONDARY, fontsize=9)

    legend(fig, methods, bbox_to_anchor=(0.5, 0.96))
    finish(fig, "G10: Oracle queries per seed (dots) and mean (bar)", output_path, top=0.93)


def write_summary(data, methods, output_path):
    """The headline numbers for the results and summary slides, as Markdown tables."""
    lines = ["# Presentation summary", ""]
    for variant in VARIANTS:
        circuits = complete_circuits(data, variant, methods)
        if not circuits:
            continue
        runs = {m: [r for c in circuits for r in records_of(data, variant, c, m)] for m in methods}
        excluded = [c for c in circuits_in(data, variant) if c not in circuits]
        lines += [f"## {VARIANT_TITLES[variant]}, {len(circuits)} circuits: {', '.join(circuits)}", "",
                  *([f"Excluded, some runs timed out: {', '.join(excluded)}", ""] if excluded else []),
                  "| Method | Runs | Equivalent | Total queries | vs baseline | Geo-mean query ratio "
                  "| Fewest queries on | Total I/O-aware runtime (s) | Fastest on |",
                  "|---|---|---|---|---|---|---|---|---|"]

        queries = {m: {c: metric_mean(data, variant, c, m, "oracle_queries") for c in circuits} for m in methods}
        runtime = {m: {c: metric_mean(data, variant, c, m, "io_aware_total_runtime_seconds") for c in circuits}
                   for m in methods}
        base_total = sum(queries[BASELINE_METHOD].values())
        for method in methods:
            total = sum(queries[method].values())
            ratio = geometric_mean([queries[method][c] / queries[BASELINE_METHOD][c] for c in circuits])
            # Ties count as a win for every tied method.
            fewest = sum(queries[method][c] == min(queries[m][c] for m in methods) for c in circuits)
            fastest = sum(runtime[method][c] == min(runtime[m][c] for m in methods) for c in circuits)
            equivalent = sum(1 for r in runs[method] if r["functional_equivalence"])
            lines.append(f"| {METHOD_LABELS[method]} | {len(runs[method])} | {equivalent}/{len(runs[method])} "
                         f"| {total:.1f} | {(total / base_total - 1) * 100:+.0f}% | {ratio:.2f} "
                         f"| {fewest}/{len(circuits)} | {sum(runtime[method].values()):.1f} | {fastest}/{len(circuits)} |")

        lines += ["", "Per circuit, mean oracle queries ± sample standard deviation over seeds:", "",
                  "| Circuit | " + " | ".join(METHOD_LABELS[m] for m in methods) + " |",
                  "|---|" + "---|" * len(methods)]
        for circuit in circuits:
            cells = []
            for method in methods:
                values = [r["oracle_queries"] for r in records_of(data, variant, circuit, method)]
                spread = f" ± {statistics.stdev(values):.1f}" if len(values) >= 2 else ""
                cells.append(f"{mean(values):.1f}{spread}")
            lines.append(f"| {circuit} | " + " | ".join(cells) + " |")
        lines.append("")

    output_path.write_text("\n".join(lines))
    print(f"  {output_path.name}")


def main():
    parser = argparse.ArgumentParser(description="Draw the presentation graphs from one run_benchmarks.py invocation.")
    parser.add_argument("results_dir", type=Path,
        help="timestamped folder created by run_benchmarks.py, e.g. analysis/results/2026-11-02_12-28-22")
    parser.add_argument("--trace-variant", default="RND320", choices=VARIANTS,
        help="key size whose partitioning runs G8 traces (default: RND320)")
    args = parser.parse_args()

    if not (args.results_dir / "attack_metrics").is_dir():
        parser.error(f"{args.results_dir} has no attack_metrics/ folder")

    data = load_records(args.results_dir)
    methods = methods_in(data)
    if not methods:
        parser.error(f"No attack records found in {args.results_dir / 'attack_metrics'}")

    out = args.results_dir / "presentation"
    out.mkdir(exist_ok=True)
    print(f"Writing to {out}")

    circuits = abr.circuit_order(data, args.results_dir)
    abr.plot_oracle_queries(data, methods, circuits, out / "G1_oracle_queries.png")
    print("  G1_oracle_queries.png")
    plot_query_ratio(data, methods, out / "G2_query_ratio.png")
    abr.plot_runtime_breakdown(data, methods, circuits, out / "G3_runtime_breakdown.png")
    print("  G3_runtime_breakdown.png")
    # Baseline vs partitioning only, on the key sizes where both finish quickly.
    abr.plot_runtime_breakdown(data, [BASELINE_METHOD, "partitioning"], circuits,
                               out / "G3b_runtime_breakdown_std_vs_part.png", variants=["RND320", "RND640"])
    print("  G3b_runtime_breakdown_std_vs_part.png")
    plot_checks_vs_queries(data, methods, out / "G4_checks_vs_queries.png")
    plot_hamming(data, methods, out / "G5_hamming_distance.png")
    plot_latency_sensitivity(data, methods, out / "G6_latency_sensitivity.png")
    plot_key_size_scaling(data, methods, out / "G7_key_size_scaling.png")
    plot_partition_trace(data, args.trace_variant, out / "G8_partition_entropy.png")
    plot_scoring_speedup(out / "G9_scoring_speedup.png")
    plot_seed_spread(data, methods, out / "G10_seed_spread.png")
    write_summary(data, methods, out / "summary.md")


if __name__ == "__main__":
    main()
