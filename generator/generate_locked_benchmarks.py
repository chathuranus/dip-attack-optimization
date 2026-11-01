
#!/usr/bin/env python3
"""Batch random / Yasin Algorithm-3 (SLJI) XOR/XNOR locking for structural Verilog."""
import argparse
import json
import random
import re
from collections import defaultdict
from sll_algorithm3 import select_sll
from pathlib import Path

GATES = {"and", "nand", "or", "nor", "xor", "xnor", "not", "buf"}
ID = r"[A-Za-z_][A-Za-z0-9_$]*"


def parse_verilog(path):
    text = Path(path).read_text()
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"//[^\n]*", "", text)
    text = re.sub(r"(?m)^\s*`[^\n]*", "", text)
    m = re.search(r"\bmodule\s+(" + ID + r")\s*\((.*?)\)\s*;", text, re.S)
    if not m or len(re.findall(r"\bmodule\b", text)) != 1:
        raise ValueError("expected exactly one non-parameterized module")
    module = m.group(1)
    header = m.group(2)
    body = text[m.end():]
    body = re.sub(r"\bendmodule\b\s*$", "", body).strip()
    inputs, outputs, wires = [], [], []

    def add_declaration(kind, names):
        if "[" in names or "]" in names:
            raise ValueError("vector declarations are not supported; flatten with Yosys first")
        names = re.sub(r"\b(wire|logic|reg|signed)\b", "", names)
        for name in names.split(","):
            name = name.strip()
            if not re.fullmatch(ID, name):
                raise ValueError(f"unsupported declaration: {name!r}")
            target = {"input": inputs, "output": outputs, "wire": wires}[kind]
            if name not in target:
                target.append(name)

    if re.search(r"\b(input|output)\b", header):
        current = None
        for token in header.split(","):
            token = token.strip()
            match = re.match(r"^(input|output)\b\s*(.*)$", token, re.S)
            if match:
                current = match.group(1)
                token = match.group(2)
            if current is None:
                raise ValueError("mixed ANSI/non-ANSI module header")
            add_declaration(current, token)

    gates = []
    for stmt in body.split(";"):
        stmt = stmt.strip()
        if not stmt:
            continue
        decl = re.fullmatch(r"(input|output|wire)\s+(.+)", stmt, re.S)
        if decl:
            add_declaration(decl.group(1), decl.group(2))
            continue
        gate = re.fullmatch(
            r"(" + "|".join(sorted(GATES)) + r")\s+(?:" + ID + r"\s*)?\((.*?)\)",
            stmt, re.S | re.I
        )
        if not gate:
            raise ValueError(f"unsupported Verilog statement: {stmt[:90]!r}")
        op = gate.group(1).lower()
        pins = [p.strip() for p in gate.group(2).split(",")]
        if len(pins) < (2 if op in {"not", "buf"} else 3) or not all(re.fullmatch(ID, p) for p in pins):
            raise ValueError(f"unsupported gate ports: {stmt[:90]!r}")
        if op in {"not", "buf"} and len(pins) != 2:
            raise ValueError("not/buf gates must have one input")
        gates.append((op, pins[0], pins[1:]))

    if not inputs or not outputs or not gates:
        raise ValueError("missing inputs, outputs or gates")
    if set(inputs) & set(outputs):
        raise ValueError("inout ports are not supported")
    drivers = {}
    for i, (_, out, _) in enumerate(gates):
        if out in drivers or out in inputs:
            raise ValueError(f"multiple drivers or driven primary input: {out}")
        drivers[out] = i
    for op, out, args in gates:
        for a in args:
            if a not in inputs and a not in drivers:
                raise ValueError(f"undriven signal {a!r} feeding {out!r}")
    for o in outputs:
        if o not in drivers and o not in inputs:
            raise ValueError(f"undriven output {o}")

    # Topologically sort to reject combinational cycles.
    state, ordered = {}, []

    def visit(i):
        if state.get(i) == 1:
            raise ValueError("combinational cycle detected")
        if state.get(i) == 2:
            return
        state[i] = 1
        for a in gates[i][2]:
            if a in drivers:
                visit(drivers[a])
        state[i] = 2
        ordered.append(gates[i])

    for i in range(len(gates)):
        visit(i)
    return module, inputs, outputs, wires, ordered


def downstream_cones(gates, outputs):
    fanout = defaultdict(set)
    for _, out, args in gates:
        for a in args:
            fanout[a].add(out)
    cones = {}
    for _, out, _ in gates:
        seen, stack = set(), [out]
        while stack:
            net = stack.pop()
            for nxt in fanout[net]:
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        cones[out] = seen
    return cones


def choose_locations(gates, inputs, outputs, size, scheme, rng,
                     atpg_backend='z3', atpg_timeout_ms=10000, max_atpg_checks=None,
                     sll_retry_rejected=False, sll_use_theorem1=True):
    all_outs = [out for _, out, _ in gates]
    if size > len(all_outs):
        raise ValueError(f'key size {size} exceeds {len(all_outs)} gate outputs')
    if scheme == 'rnd':
        internal = [n for n in all_outs if n not in outputs]
        eligible = internal if len(internal) >= size else all_outs
        return rng.sample(eligible, size), None
    if scheme == 'sll':
        result = select_sll(
            gates, inputs, outputs, size, rng,
            atpg_backend=atpg_backend,
            timeout_ms=atpg_timeout_ms,
            max_checks=max_atpg_checks,
            retry_rejected=sll_retry_rejected,
            use_theorem1=sll_use_theorem1
        )
        if len(result.locations) != size:
            raise ValueError(
                f'Algorithm 3 selected {len(result.locations)}/{size} key gates; '
                'refusing to mislabel a partial benchmark as full-key SLL'
            )
        return result.locations, result
    raise ValueError(f'unknown scheme {scheme}')


def emit_verilog(module, inputs, outputs, wires, gates):
    # Deliberately emit only gate primitives and scalar declarations.
    used = set(inputs + outputs + wires)
    used.update(out for _, out, _ in gates)
    for _, _, args in gates:
        used.update(args)
    internals = sorted(used - set(inputs) - set(outputs))
    lines = [f"module {module}({', '.join(inputs + outputs)});"]
    for kind, nets in (("input", inputs), ("output", outputs), ("wire", internals)):
        for start in range(0, len(nets), 16):
            lines.append(f"  {kind} {', '.join(nets[start:start+16])};")
    for i, (op, out, args) in enumerate(gates):
        lines.append(f"  {op} g{i}({', '.join([out] + args)});")
    lines.append("endmodule")
    return "\n".join(lines) + "\n"


def evaluate(inputs, outputs, gates, values):
    signals = dict(values)
    for op, out, args in gates:
        a = [signals[n] for n in args]
        if op in ("and", "nand"):
            v = int(all(a))
        elif op in ("or", "nor"):
            v = int(any(a))
        elif op in ("xor", "xnor"):
            v = sum(a) % 2
        elif op == "not":
            v = 1 - a[0]
        else:
            v = a[0]
        if op in ("nand", "nor", "xnor"):
            v = 1 - v
        signals[out] = v
    return tuple(signals[o] for o in outputs)


def generate(path, scheme, size, seed, instance, outdir,
             atpg_backend="z3", atpg_timeout_ms=10000, max_atpg_checks=None,
             sll_retry_rejected=False, sll_use_theorem1=True):
    name, inputs, outputs, wires, gates = parse_verilog(path)
    rng = random.Random(seed)
    locations, sll = choose_locations(
        gates, inputs, outputs, size, scheme, rng,
        atpg_backend=atpg_backend,
        atpg_timeout_ms=atpg_timeout_ms,
        max_atpg_checks=max_atpg_checks,
        sll_retry_rejected=sll_retry_rejected,
        sll_use_theorem1=sll_use_theorem1
    )
    selected = {n: i for i, n in enumerate(locations)}
    key = [0] * size
    locked_gates = []
    all_names = set(inputs + outputs + wires)
    all_names.update(out for _, out, _ in gates)
    all_names.update(a for _, _, args in gates for a in args)
    key_inputs = [f"keyinput{i}" for i in range(size)]
    if all_names & set(key_inputs):
        raise ValueError("keyinput name collision")
    for op, out, args in gates:
        if out not in selected:
            locked_gates.append((op, out, args))
            continue
        i = selected[out]
        raw = f"__ll_raw_{i}"
        if raw in all_names:
            raise ValueError(f"generated signal collision: {raw}")
        all_names.add(raw)
        locked_gates.append((op, raw, args))
        lock_op = rng.choice(["xor", "xnor"])
        key[i] = int(lock_op == "xnor")
        locked_gates.append((lock_op, out, [raw, key_inputs[i]]))

    # Random-input regression: correct key must restore the original function.
    for _ in range(128):
        x = {n: rng.randrange(2) for n in inputs}
        oracle = evaluate(inputs, outputs, gates, x)
        locked = evaluate(
            inputs + key_inputs, outputs, locked_gates,
            {**x, **dict(zip(key_inputs, key))}
        )
        if oracle != locked:
            raise AssertionError(f"correct-key mismatch for {path}")

    tag = "RND" if scheme == "rnd" else ("SLJIR" if sll_retry_rejected else "SLJI")
    stem = re.sub(r"[-_]oracle$", "", Path(path).stem, flags=re.I)
    label = f"{stem}-{tag}{size}{instance}"
    folder = outdir / label
    if folder.exists():
        raise FileExistsError(f"refusing to overwrite {folder}")
    folder.mkdir(parents=True)
    (folder / f"{label}.v").write_text(
        emit_verilog(name + "_locked", inputs + key_inputs,
                     outputs, wires, locked_gates)
    )
    (folder / f"{stem}-oracle.v").write_text(
        emit_verilog(name, inputs, outputs, wires, gates)
    )
    metadata = {
        "source": str(path),
        "scheme_requested": scheme,
        "scheme_actual": (
            "random-xor-xnor" if scheme == "rnd"
            else "Yasin-2016-Algorithm3-SLJI-retry-extension"
            if sll_retry_rejected
            else "Yasin-2016-Algorithm3-SLJI"
        ),
        "sll_atpg_backend": atpg_backend if scheme == "sll" else None,
        "sll_atpg_model": (
            "single-output key sensitization with other key unknown"
            if scheme == "sll" else None
        ),
        "sll_theorem1_shortcut": sll_use_theorem1 if scheme == "sll" else None,
        "sll_retry_rejected": sll_retry_rejected if scheme == "sll" else None,
        "sll_theorem1_inferences": sll.theorem1_inferences if sll else None,
        "sll_clique_retries": sll.clique_retries if sll else None,
        "sll_cliques": sll.cliques if sll else None,
        "sll_nonmutable_edges": sll.nonmutable_edges if sll else None,
        "sll_atpg_checks": sll.atpg_checks if sll else None,
        "sll_candidates_rejected": sll.candidates_rejected if sll else None,
        "key_size": size,
        "seed": seed,
        "instance": instance,
        "key_bits_in_keyinput_order": "".join(map(str, key)),
        "locked_gate_outputs_in_keyinput_order": locations,
        "validation": "128 correct-key randomized tests passed; not a formal proof",
    }
    (folder / "key_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    (folder / f"ReadMe_{label}.txt").write_text(
        f"Benchmark: {stem}\nScheme: {metadata['scheme_actual']}\n"
        f"Key size: {size}\nSeed: {seed}\nInstance: {instance}\n"
        "Structural Verilog; no technology library used.\n"
        "SLL mode implements Yasin et al. (2016) Algorithm 3 placement with direct\n"
        "pairwise SAT-based sensitization checks (Theorem 1 optional).\n"
        + (
            "Rejected gates may seed later cliques (NON-STANDARD extension).\n"
            if sll_retry_rejected and scheme == "sll" else ""
        )
        + "Correct key is in key_metadata.json for evaluation only.\n"
    )
    return folder


def main():
    p = argparse.ArgumentParser(description=__doc__)
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--bench", type=Path, help="one structural Verilog file")
    source.add_argument("--bench-dir", type=Path, help="directory of structural Verilog files")
    p.add_argument("--scheme", choices=["rnd", "sll", "all"], default="all")
    p.add_argument("--key-size", type=int, help="single key size, e.g. 32")
    p.add_argument("--key-sizes", type=int, nargs="+", default=[32, 64, 128])
    p.add_argument("--instances", type=int, default=1)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", type=Path, default=Path("../benchmarks"))
    p.add_argument("--atpg-backend", choices=["z3", "exhaustive"], default="z3")
    p.add_argument("--atpg-timeout-ms", type=int, default=10000)
    p.add_argument("--max-atpg-checks", type=int, default=None)
    p.add_argument(
        "--sll-retry-rejected",
        action="store_true",
        help="Non-standard extension: allow rejected gates in later cliques"
    )
    p.add_argument(
        "--no-theorem1",
        action="store_true",
        help="Disable the Theorem 1 shortcut for an ablation experiment"
    )
    args = p.parse_args()
    if args.instances < 1:
        p.error("--instances must be >= 1")
    sizes = [args.key_size] if args.key_size is not None else args.key_sizes
    if any(s < 1 for s in sizes):
        p.error("key sizes must be positive")
    schemes = ["rnd", "sll"] if args.scheme == "all" else [args.scheme]
    paths = [args.bench] if args.bench else sorted(args.bench_dir.glob("*.v"))
    if not paths:
        p.error("no .v files found")
    if "sll" in schemes:
        print(
            "SLL: Yasin et al. Algorithm 3, ATPG/SAT checks; "
            "Theorem 1 shortcut enabled unless disabled."
        )
        if args.sll_retry_rejected:
            print(
                "WARNING: --sll-retry-rejected is a NON-STANDARD extension, "
                "not strict Algorithm 3."
            )
    completed, failed = 0, 0
    for path in paths:
        for scheme in schemes:
            for size in sizes:
                for instance in range(args.instances):
                    seed = args.seed + instance
                    try:
                        folder = generate(
                            path, scheme, size, seed, instance, args.out,
                            atpg_backend=args.atpg_backend,
                            atpg_timeout_ms=args.atpg_timeout_ms,
                            max_atpg_checks=args.max_atpg_checks,
                            sll_retry_rejected=args.sll_retry_rejected,
                            sll_use_theorem1=not args.no_theorem1
                        )
                        completed += 1
                        print(f"OK   {folder}")
                    except (
                        ValueError, OSError, AssertionError, RecursionError,
                        RuntimeError, TimeoutError
                    ) as e:
                        failed += 1
                        print(
                            f"SKIP {path.name} {scheme} {size} "
                            f"instance={instance}: {e}"
                        )
    print(f"Finished: {completed} generated, {failed} skipped/failed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
