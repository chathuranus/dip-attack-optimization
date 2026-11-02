
# analyze_benchmark_results.py

# Plots the results of one run_benchmarks.py invocation. Reads the raw
# records in <results_folder>/attack_metrics/ and writes the figures to
# <results_folder>/plots/. Each figure stacks the RND320 and RND640 variants
# vertically.
#
# Usage (from the repo root):
#   .venv/bin/python analysis/analyze_benchmark_results.py analysis/results/2026-11-02_12-28-22

import argparse
import csv
import json
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Base size for tick labels, axis labels and legends (matplotlib default: 10).
plt.rcParams["font.size"] = 18
from matplotlib.patches import Patch
from matplotlib.ticker import MultipleLocator


# Same order as run_benchmarks.py.
VARIANTS = ["RND320", "RND640"]
VARIANT_TITLES = {
    "RND320": "32-bit key",
    "RND640": "64-bit key",
}

METHOD_LABELS = {
    "standard_sat": "Standard SAT",
    "maxsat": "MaxSAT (Hamming)",
    "maxsat_optimize": "MaxSAT (z3 Optimize)",
    "partitioning": "Partitioning",
}
METHOD_SHORT_LABELS = {
    "standard_sat": "Std",
    "maxsat": "Max",
    "maxsat_optimize": "Opt",
    "partitioning": "Part",
}

# Bar colour per method in the oracle queries plot. Fixed per method so a
# method keeps its colour whichever other methods are present.
METHOD_COLORS = {
    "standard_sat": "#f1a340",
    "maxsat": "#998ec3",
    "maxsat_optimize": "#1baf7a",
    "partitioning": "#2a78d6",
}

# Runtime components, bottom to top. Together they add up to
# io_aware_total_runtime_seconds.
TIME_COMPONENTS = [
    ("dip_generation", "DIP generation"),
    ("final_dip_check", "Final DIP check"),
    ("oracle", "Oracle evaluation"),
    ("io", "Off-chip I/O (modelled)"),
    ("constraint_update", "Update Miter"),
    ("other", "Other (parsing, key recovery, verification)"),
]

# Categorical palette in fixed slot order (blue, orange, aqua, yellow, green, magenta).
COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#008300", "#e87ba4"]
SURFACE = "#fcfcfb"
# Panel title position, as a fraction of the axes width from the y-axis.
TITLE_X = 0.02
INK = "#000000"  # all text, axes and error bars
GRID = "#e1e0d9"


def load_records(results_dir):
    """Returns {variant: {circuit: {method: [record, ...]}}} from attack_metrics/*.json."""
    data = {variant: {} for variant in VARIANTS}

    for path in (results_dir / "attack_metrics").glob("*.json"):
        circuit, variant = path.stem.rsplit("-", 1)
        if variant not in data:
            continue
        with path.open() as f:
            data[variant][circuit] = json.load(f)["results"]

    return data


def present_methods(data):
    """Methods with at least one record, in METHOD_LABELS order."""
    found = {
        method
        for circuits in data.values()
        for results in circuits.values()
        for method, records in results.items()
        if records
    }
    return [method for method in METHOD_LABELS if method in found]


def circuit_order(data, results_dir):
    """
    Every circuit seen in any variant, smallest ISCAS-85 number first. The
    CSVs also list circuits whose runs all timed out and so have no JSON.
    """
    circuits = {circuit for circuits in data.values() for circuit in circuits}
    for path in results_dir.glob("benchmark_results_*.csv"):
        with path.open() as f:
            circuits.update(row["benchmark"].rsplit("-", 1)[0] for row in csv.DictReader(f))
    return sorted(circuits, key=lambda name: int(name.lstrip("c")))


def mean(values):
    return sum(values) / len(values) if values else None


def time_breakdown(records):
    """Mean seconds per runtime component, or None without records."""
    if not records:
        return None

    parts = {
        "dip_generation": mean([r["dip_generation_seconds"] for r in records]),
        "final_dip_check": mean([r["final_dip_check_seconds"] for r in records]),
        "oracle": mean([r["oracle_seconds"] for r in records]),
        "io": mean([r["io_aware_oracle_seconds"] for r in records]),
        "constraint_update": mean([r["constraint_update_seconds"] for r in records]),
    }
    measured = mean([r["total_runtime_seconds"] for r in records])
    parts["other"] = max(
        measured - parts["dip_generation"] - parts["final_dip_check"] - parts["oracle"] - parts["constraint_update"],
        0.0,
    )
    return parts


def style_axes(ax):
    ax.set_facecolor(SURFACE)
    ax.grid(axis="y", color=GRID, linewidth=1)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(INK)
        ax.spines[side].set_linewidth(1.2)
    ax.tick_params(colors=INK, direction="out", length=6, width=1.2)


def new_figure(rows):
    fig, axes = plt.subplots(rows, 1, figsize=(11, 4.2 * rows), facecolor=SURFACE, squeeze=False)
    return fig, [row[0] for row in axes]


def mark_missing(ax, x, label="no data"):
    """Labels a slot whose runs all timed out or failed, so it is not read as zero."""
    ax.text(x, 0, label, rotation=90, ha="center", va="bottom", fontsize=13, color=INK)


def plot_oracle_queries(data, methods, circuits, output_path):
    fig, axes = new_figure(len(VARIANTS))
    width = 0.8 / len(methods)

    for ax, variant in zip(axes, VARIANTS):
        style_axes(ax)
        for i, method in enumerate(methods):
            for x, circuit in enumerate(circuits):
                records = data[variant].get(circuit, {}).get(method, [])
                position = x - 0.4 + width * (i + 0.5)
                values = [r["oracle_queries"] for r in records]
                if not values:
                    mark_missing(ax, position)
                    continue
                std = statistics.stdev(values) if len(values) >= 2 else None
                ax.bar(position, mean(values), width * 0.9, color=METHOD_COLORS[method],
                       yerr=std, error_kw={"ecolor": INK, "elinewidth": 1, "capsize": 2})

        ax.set_title(VARIANT_TITLES[variant], loc="left", x=TITLE_X, color=INK, fontsize=21)
        ax.set_xticks(range(len(circuits)), circuits)
        if variant == "RND640":
            ax.yaxis.set_major_locator(MultipleLocator(20))

    axes[-1].set_xlabel("ISCAS-85 benchmark circuits", color=INK)
    fig.supylabel("# Oracle queries (mean)", color=INK)
    handles = [Patch(color=METHOD_COLORS[m], label=METHOD_LABELS[m]) for m in methods]
    fig.legend(handles=handles, loc="upper center", ncol=len(methods), frameon=False,
               bbox_to_anchor=(0.5, 1.0), labelcolor=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(output_path, dpi=200, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


def plot_runtime_breakdown(data, methods, circuits, output_path):
    fig, axes = new_figure(len(VARIANTS))
    width = 0.8 / len(methods)

    for ax, variant in zip(axes, VARIANTS):
        style_axes(ax)
        method_ticks, method_labels = [], []

        for i, method in enumerate(methods):
            for x, circuit in enumerate(circuits):
                position = x - 0.4 + width * (i + 0.5)
                method_ticks.append(position)
                method_labels.append(METHOD_SHORT_LABELS[method])

                parts = time_breakdown(data[variant].get(circuit, {}).get(method, []))
                if parts is None:
                    mark_missing(ax, position)
                    continue

                bottom = 0.0
                for (key, _), color in zip(TIME_COMPONENTS, COLORS):
                    # The surface-coloured edge is the gap between stacked segments.
                    ax.bar(position, parts[key], width * 0.9, bottom=bottom, color=color,
                           edgecolor=SURFACE, linewidth=0.8)
                    bottom += parts[key]

        # Method under each bar, circuit name centred below its group.
        ax.set_xticks(method_ticks, method_labels, minor=True, fontsize=13)
        ax.set_xticks(range(len(circuits)), circuits)
        # No x tick marks here: one at the group centre would sit between the Std and Max labels.
        ax.tick_params(axis="x", which="major", pad=26, length=0)
        ax.tick_params(axis="x", which="minor", colors=INK, length=0)

        ax.set_title(VARIANT_TITLES[variant], loc="left", x=TITLE_X, color=INK, fontsize=21)

    axes[-1].set_xlabel("ISCAS-85 benchmark circuits", color=INK)
    fig.supylabel("I/O-aware runtime (s, mean)", color=INK)
    handles = [Patch(color=color, label=label) for (_, label), color in zip(TIME_COMPONENTS, COLORS)]
    fig.legend(handles=handles, loc="upper center", ncol=2, frameon=False,
               bbox_to_anchor=(0.5, 1.0), labelcolor=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    fig.savefig(output_path, dpi=200, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description="Plot the results of one run_benchmarks.py invocation.")
    parser.add_argument("results_dir", type=Path,
        help="timestamped folder created by run_benchmarks.py, e.g. analysis/results/2026-11-02_12-28-22")
    args = parser.parse_args()

    if not (args.results_dir / "attack_metrics").is_dir():
        parser.error(f"{args.results_dir} has no attack_metrics/ folder")

    data = load_records(args.results_dir)
    methods = present_methods(data)
    circuits = circuit_order(data, args.results_dir)
    if not methods:
        parser.error(f"No attack records found in {args.results_dir / 'attack_metrics'}")

    plots_dir = args.results_dir / "plots"
    plots_dir.mkdir(exist_ok=True)

    plot_oracle_queries(data, methods, circuits, plots_dir / "oracle_queries.png")
    plot_runtime_breakdown(data, methods, circuits, plots_dir / "runtime_breakdown.png")

    print(f"Saved plots to {plots_dir}")


if __name__ == "__main__":
    main()
