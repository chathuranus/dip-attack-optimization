
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
from matplotlib import patheffects

# Base size for tick labels, axis labels and legends (matplotlib default: 10).
plt.rcParams["font.size"] = 18
from matplotlib.patches import Patch, Polygon
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

# Runtime components (key, legend label, colour), bottom to top. Together they
# add up to io_aware_total_runtime_seconds.
TIME_COMPONENTS = [
    ("other", "Other", "#e66101"),
    ("oracle_io", "Off-chip I/O + oracle evaluation", "#fdb863"),
    ("dip_generation", "DIP generation", "#b2abd2"),
    ("constraint_update", "Update miter circuit", "#5e3c99"),
]
SURFACE = "#fcfcfb"
# y-axis cap in seconds per runtime panel. Bars taller than the cap run off
# the top, labelled with their value. Panels not listed are not capped.
RUNTIME_Y_CAPS = {"RND640": 10}
# Method whose runtime split is shown in runtime_share_standard_sat.png, and the
# narrowest segment (in %) that still gets a percentage label.
SHARE_METHOD = "standard_sat"
SHARE_LABEL_MIN = 4

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
        # The final DIP check is the last DIP search (the one that finds no DIP).
        "dip_generation": mean([r["dip_generation_seconds"] + r["final_dip_check_seconds"] for r in records]),
        "constraint_update": mean([r["constraint_update_seconds"] for r in records]),
        "oracle_io": mean([r["oracle_seconds"] + r["io_aware_oracle_seconds"] for r in records]),
    }
    # Whatever measured time the components above do not cover. The modelled
    # I/O is not part of total_runtime_seconds, so only the oracle part of
    # oracle_io is subtracted.
    measured = mean([r["total_runtime_seconds"] for r in records])
    oracle = mean([r["oracle_seconds"] for r in records])
    parts["other"] = max(measured - parts["dip_generation"] - parts["constraint_update"] - oracle, 0.0)
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


def draw_runtime_bars(ax, data, variant, methods, circuits):
    """
    Draws the stacked runtime bars of one variant. Returns (x position, height,
    standard deviation of the total across runs, or None for a single run) per bar.
    """
    width = 0.8 / len(methods)
    bars = []
    for i, method in enumerate(methods):
        for x, circuit in enumerate(circuits):
            position = x - 0.4 + width * (i + 0.5)
            records = data[variant].get(circuit, {}).get(method, [])
            parts = time_breakdown(records)
            if parts is None:
                mark_missing(ax, position)
                continue

            bottom = 0.0
            for key, _, color in TIME_COMPONENTS:
                # The surface-coloured edge is the gap between stacked segments.
                ax.bar(position, parts[key], width * 0.9, bottom=bottom, color=color,
                       edgecolor=SURFACE, linewidth=0.8)
                bottom += parts[key]
            totals = [r["io_aware_total_runtime_seconds"] for r in records]
            std = statistics.stdev(totals) if len(totals) >= 2 else None
            bars.append((position, bottom, std))
    return bars


def draw_total_error_bars(ax, bars, cap=None):
    """
    Standard deviation of the total runtime across runs, on top of each bar.
    Skipped for bars cut off by the y-axis cap, whose top is not shown.
    """
    for position, total, std in bars:
        if std is None or (cap is not None and total > cap):
            continue
        container = ax.errorbar(position, total, yerr=std, fmt="none", ecolor=INK,
                                elinewidth=1.2, capsize=3, capthick=1.2, zorder=4)
        # A light outline keeps the black bar visible over the dark segments.
        for artist in container.get_children():
            artist.set_path_effects([patheffects.withStroke(linewidth=3, foreground=SURFACE)])


def set_runtime_xticks(ax, methods, circuits):
    """Method under each bar, circuit name centred below its group."""
    width = 0.8 / len(methods)
    ticks = [x - 0.4 + width * (i + 0.5) for i in range(len(methods)) for x in range(len(circuits))]
    labels = [METHOD_SHORT_LABELS[m] for m in methods for _ in circuits]
    ax.set_xticks(ticks, labels, minor=True, fontsize=13)
    ax.set_xticks(range(len(circuits)), circuits)
    # No x tick marks here: one at the group centre would sit between the Std and Max labels.
    ax.tick_params(axis="x", which="major", pad=26, length=0)
    ax.tick_params(axis="x", which="minor", colors=INK, length=0)


def apply_axis_cap(ax, cap, bars, bar_width):
    """
    Limits the y-axis to cap. Bars taller than cap run off the top with a
    diagonal cut near the top and their true value printed above them.
    """
    ax.set_ylim(0, cap)
    ax.yaxis.set_major_locator(MultipleLocator(2))
    cut_bottom, cut_height, slant = cap * 0.86, cap * 0.035, cap * 0.05
    half = bar_width / 2 + 0.02
    for position, total, _ in bars:
        if total <= cap:
            continue
        # A surface-coloured slanted band across the bar marks where it is cut.
        ax.add_patch(Polygon(
            [(position - half, cut_bottom), (position + half, cut_bottom + slant),
             (position + half, cut_bottom + slant + cut_height), (position - half, cut_bottom + cut_height)],
            closed=True, facecolor=SURFACE, edgecolor="none", zorder=3))
        ax.text(position, cap, f"{total:.1f} s", ha="center", va="bottom",
                fontsize=15, color=INK, clip_on=False)


def plot_runtime_breakdown(data, methods, circuits, output_path):
    fig, axes = new_figure(len(VARIANTS))

    for ax, variant in zip(axes, VARIANTS):
        style_axes(ax)
        bars = draw_runtime_bars(ax, data, variant, methods, circuits)
        set_runtime_xticks(ax, methods, circuits)
        ax.set_title(VARIANT_TITLES[variant], loc="left", x=TITLE_X, color=INK, fontsize=21)
        cap = RUNTIME_Y_CAPS.get(variant)
        if cap is not None:
            apply_axis_cap(ax, cap, bars, bar_width=0.8 / len(methods) * 0.9)
        draw_total_error_bars(ax, bars, cap)

    axes[-1].set_xlabel("ISCAS-85 benchmark circuits", color=INK)
    fig.supylabel("Runtime (seconds)", color=INK)
    # Top segment first, so the legend (filled column by column) reads in the
    # same top-to-bottom order as the bars.
    handles = [Patch(color=color, label=label) for _, label, color in reversed(TIME_COMPONENTS)]
    fig.legend(handles=handles, loc="upper center", ncol=2, frameon=False,
               bbox_to_anchor=(0.5, 1.0), labelcolor=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.89))
    fig.savefig(output_path, dpi=200, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


def runtime_shares(records_per_circuit):
    """
    Mean share (0-1) of runtime per category, averaged over circuits so each
    circuit counts equally. records_per_circuit is a list of record lists.
    """
    shares = []
    for records in records_per_circuit:
        parts = time_breakdown(records)
        if parts is None:
            continue
        total = sum(parts.values())
        if total > 0:
            shares.append({key: value / total for key, value in parts.items()})
    if not shares:
        return None
    return {key: mean([share[key] for share in shares]) for key, _, _ in TIME_COMPONENTS}


def text_color_on(fill):
    """Black or white, whichever reads better on the given fill colour."""
    r, g, b = (int(fill[i:i + 2], 16) / 255 for i in (1, 3, 5))
    channel = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    luminance = 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
    # Contrast with black is (L + 0.05) / 0.05, with white 1.05 / (L + 0.05).
    return INK if (luminance + 0.05) ** 2 > 0.0525 else "#ffffff"


def plot_runtime_share(data, output_path, method=SHARE_METHOD):
    """
    A single 100% horizontal bar over the 32- and 64-bit keys together: the
    share of the method's runtime spent in each category.
    """
    records = [results.get(method, []) for v in VARIANTS for results in data[v].values()]
    shares = runtime_shares(records)
    if shares is None:
        return

    fig, ax = plt.subplots(figsize=(11, 2.6), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    # No axes: the percentage on each segment carries the values.
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)

    left = 0.0
    for key, _, color in TIME_COMPONENTS:
        width = shares[key] * 100
        ax.barh(0, width, height=0.8, left=left, color=color, edgecolor=SURFACE, linewidth=1.5)
        if width >= SHARE_LABEL_MIN:
            ax.text(left + width / 2, 0, f"{width:.0f}%", ha="center", va="center",
                    color=text_color_on(color))
        left += width

    ax.set_xlim(0, 100)
    ax.set_ylim(-0.5, 0.5)
    ax.set_xlabel(f"Share of {METHOD_LABELS[method]} runtime (%)", color=INK)

    # Legend reads right to left, bottom row first, in segment order:
    #   Update miter circuit | DIP generation
    #   Off-chip I/O + ...   | Other
    handles = [Patch(color=color, label=label) for _, label, color in TIME_COMPONENTS]
    handles = (handles[0::2] + handles[1::2])[::-1]
    fig.legend(handles=handles, loc="upper center", ncol=2, frameon=False,
               bbox_to_anchor=(0.5, 1.0), labelcolor=INK)
    # Leave about 0.9 inch at the top for the two-row legend.
    fig.tight_layout(rect=(0, 0, 1, 1 - 0.9 / fig.get_figheight()))
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
    plot_runtime_share(data, plots_dir / "runtime_share_standard_sat.png")

    print(f"Saved plots to {plots_dir}")


if __name__ == "__main__":
    main()
