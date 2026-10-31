#!/usr/bin/env python3
"""Create EPIC-style random XOR/XNOR locked structural-Verilog benchmark folders.

Input: combinational structural Verilog (.v) or ISCAS-style BENCH (.bench). Python standard library only.
This does NOT implement SLL or EPIC's chip-activation protocol.
"""
import argparse
import hashlib
import json
import random
import re
from pathlib import Path

NAME = r'[A-Za-z_][A-Za-z0-9_$]*'
DECL = re.compile(r'^\s*(INPUT|OUTPUT)\s*\(\s*(' + NAME + r')\s*\)\s*$', re.I)
GATE = re.compile(r'^\s*(' + NAME + r')\s*=\s*(' + NAME + r')\s*\(\s*(.*?)\s*\)\s*$', re.I)
SUPPORTED = {'and', 'or', 'nand', 'nor', 'xor', 'xnor', 'not', 'buf'}


def read_bench(path):
    ins, outs, gates = [], [], []
    for lineno, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        m = DECL.fullmatch(line)
        if m:
            (ins if m.group(1).upper() == 'INPUT' else outs).append(m.group(2))
            continue
        m = GATE.fullmatch(line)
        if not m:
            raise ValueError(f'{path}:{lineno}: unsupported BENCH line: {line}')
        dest, kind, raw_args = m.groups()
        kind = kind.lower()
        if kind not in SUPPORTED:
            raise ValueError(f'{path}:{lineno}: unsupported gate {kind} (sequential gates are not supported)')
        args = [s.strip() for s in raw_args.split(',')]
        if not args or any(not re.fullmatch(NAME, a) for a in args):
            raise ValueError(f'{path}:{lineno}: unsupported gate inputs: {raw_args}')
        if kind in {'not', 'buf'} and len(args) != 1:
            raise ValueError(f'{path}:{lineno}: {kind} expects one input')
        if kind not in {'not', 'buf'} and len(args) < 2:
            raise ValueError(f'{path}:{lineno}: {kind} expects two or more inputs')
        gates.append((dest, kind, args))
    if not ins or not outs or not gates:
        raise ValueError('Expected nonempty INPUT, OUTPUT, and gate declarations')
    if len(set(ins)) != len(ins) or len(set(outs)) != len(outs):
        raise ValueError('Duplicate primary inputs or outputs')
    destinations = [g[0] for g in gates]
    if len(set(destinations)) != len(destinations):
        raise ValueError('Multiple drivers for a gate output')
    all_known = set(ins) | set(destinations)
    for dest, kind, args in gates:
        for a in args:
            if a not in all_known:
                raise ValueError(f'Undefined net {a} used by {dest}')
    if any(o not in all_known for o in outs):
        raise ValueError('Undriven primary output')
    return ins, outs, gates



def read_structural_verilog(path):
    """Read single-module, scalar, primitive-gate structural Verilog.

    Rejects unsupported syntax rather than silently changing circuit semantics.
    """
    raw = path.read_text()
    raw = re.sub(r'/\*.*?\*/', '', raw, flags=re.S)
    raw = re.sub(r'//[^\n]*', '', raw)
    statements = [x.strip() for x in raw.split(';') if x.strip()]
    ins, outs, wires, gates = [], [], [], []
    module_name = None
    module_ports = None
    saw_end = False
    for statement in statements:
        if saw_end:
            raise ValueError('Unexpected content after endmodule')
        if module_name is None:
            match = re.fullmatch(r'module\s+(' + NAME + r')\s*\((.*?)\)', statement, flags=re.S)
            if not match:
                raise ValueError('Expected a single non-ANSI module declaration: module name(ports);')
            module_name = match.group(1)
            module_ports = [v.strip() for v in match.group(2).split(',')]
            if any(not re.fullmatch(NAME, v) for v in module_ports):
                raise ValueError('Unsupported module port declaration')
            continue
        if statement == 'endmodule':
            saw_end = True
            continue
        if statement.endswith('endmodule'):
            statement = statement[:-len('endmodule')].strip()
            saw_end = True
            if not statement:
                continue
        decl = re.fullmatch(r'(input|output|wire)\s+(.+)', statement, flags=re.S)
        if decl:
            kind, content = decl.groups()
            names = [v.strip() for v in content.split(',')]
            if any(not re.fullmatch(NAME, v) for v in names):
                raise ValueError(f'Only scalar declarations are supported: {statement[:100]}')
            {'input': ins, 'output': outs, 'wire': wires}[kind].extend(names)
            continue
        gate = re.fullmatch(r'(' + NAME + r')\s+(' + NAME + r')\s*\((.*?)\)', statement, flags=re.S)
        if not gate:
            raise ValueError(f'Unsupported structural Verilog statement: {statement[:120]}')
        kind, instance, pins = gate.groups()
        kind = kind.lower()
        if kind not in SUPPORTED:
            raise ValueError(f'Unsupported gate primitive {kind} in {instance}')
        args = [v.strip() for v in pins.split(',')]
        if any(not re.fullmatch(NAME, v) for v in args):
            raise ValueError(f'Unsupported pin syntax in {instance}')
        if (kind in {'not', 'buf'} and len(args) != 2) or (kind not in {'not', 'buf'} and len(args) < 3):
            raise ValueError(f'Wrong pin count in {instance}')
        gates.append((args[0], kind, args[1:]))
    if not saw_end or not ins or not outs or not gates:
        raise ValueError('Missing endmodule, primary I/O, or primitive gates')
    if len(set(ins)) != len(ins) or len(set(outs)) != len(outs):
        raise ValueError('Duplicate primary I/O declaration')
    if set(ins) & set(outs):
        raise ValueError('Inout ports are not supported')
    if set(module_ports) != set(ins + outs) or len(module_ports) != len(ins + outs):
        raise ValueError('Module ports do not match input/output declarations')
    destinations = [d for d, _, _ in gates]
    if len(set(destinations)) != len(destinations):
        raise ValueError('Multiple drivers in circuit')
    if set(destinations) & set(ins):
        raise ValueError('Primary input driven by gate')
    known = set(ins) | set(destinations)
    for dest, kind, args in gates:
        for a in args:
            if a not in known:
                raise ValueError(f'Undefined signal {a} used in gate output {dest}')
    if not set(outs) <= known:
        raise ValueError('Undriven output(s)')
    return ins, outs, gates


def read_circuit(path):
    if path.suffix.lower() in {'.v', '.sv'}:
        return read_structural_verilog(path)
    if path.suffix.lower() == '.bench':
        return read_bench(path)
    raise ValueError('Input must be a .v, .sv, or .bench file')


def emit_verilog(module, ins, outs, gates):
    ports = list(ins) + [o for o in outs if o not in ins]
    wires = sorted({dest for dest, _, _ in gates} - set(ins) - set(outs))
    lines = [f'module {module}({", ".join(ports)});',
             f'  input {", ".join(ins)};',
             f'  output {", ".join(outs)};']
    if wires:
        lines.append(f'  wire {", ".join(wires)};')
    for idx, (dest, kind, args) in enumerate(gates):
        lines.append(f'  {kind} gate_{idx} ({", ".join([dest] + args)});')
    lines.append('endmodule')
    return '\n'.join(lines) + '\n'


def lock_gates(ins, outs, gates, size, rng):
    candidates = [i for i, (dest, _, _) in enumerate(gates) if dest not in set(outs)]
    if size > len(candidates):
        raise ValueError(f'Requested {size} key gates, but only {len(candidates)} internal gate outputs are eligible')
    selected = rng.sample(candidates, size)
    selected_by_index = {gate_index: bit_index for bit_index, gate_index in enumerate(selected)}
    used_names = set(ins) | set(outs) | {dest for dest, _, _ in gates}
    locked, bits, placements = [], [], []
    for i, (dest, kind, args) in enumerate(gates):
        if i not in selected_by_index:
            locked.append((dest, kind, args))
            continue
        bit_index = selected_by_index[i]
        pre = f'__ll_pre_{bit_index}'
        while pre in used_names:
            pre += '_'
        used_names.add(pre)
        locked.append((pre, kind, args))
        correct_bit = rng.randrange(2)
        key_gate = 'xor' if correct_bit == 0 else 'xnor'
        locked.append((dest, key_gate, [pre, f'keyinput{bit_index}']))
        bits.append((bit_index, correct_bit))
        placements.append({'key_input': f'keyinput{bit_index}', 'original_net': dest, 'gate': key_gate})
    key = ''.join(str(b) for _, b in sorted(bits))
    return locked, key, sorted(placements, key=lambda p: int(p['key_input'][8:]))


def evaluate(ins, outs, gates, assignment):
    vals = dict(assignment)
    todo = list(gates)
    while todo:
        remaining = []
        progress = False
        for dest, kind, args in todo:
            if any(a not in vals for a in args):
                remaining.append((dest, kind, args))
                continue
            a = [vals[n] for n in args]
            if kind == 'and': v = int(all(a))
            elif kind == 'or': v = int(any(a))
            elif kind == 'nand': v = int(not all(a))
            elif kind == 'nor': v = int(not any(a))
            elif kind == 'xor': v = sum(a) % 2
            elif kind == 'xnor': v = 1 - (sum(a) % 2)
            elif kind == 'not': v = 1 - a[0]
            elif kind == 'buf': v = a[0]
            vals[dest] = v
            progress = True
        if not progress:
            raise ValueError('Combinational loop or unresolved input in netlist')
        todo = remaining
    return tuple(vals[o] for o in outs)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--bench', type=Path, required=True, help='Unlocked combinational structural Verilog (.v) or BENCH (.bench) file')
    ap.add_argument('--scheme', choices=['rnd', 'sll'], required=True,
                    help='Locking scheme (rnd implemented; sll reserved for future support)')
    ap.add_argument('--key-size', type=int, required=True)
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--instance', type=int, default=0)
    ap.add_argument('--out', type=Path, default=Path('../benchmarks'))
    ap.add_argument('--verify-vectors', type=int, default=128)
    args = ap.parse_args()
    if args.scheme == 'sll':
        ap.error('SLL is not implemented yet; use --scheme rnd')
    if args.key_size < 1 or args.verify_vectors < 1:
        ap.error('--key-size and --verify-vectors must be positive')
    ins, outs, gates = read_circuit(args.bench)
    rng = random.Random(args.seed)
    locked, key, placements = lock_gates(ins, outs, gates, args.key_size, rng)
    key_inputs = [f'keyinput{i}' for i in range(args.key_size)]
    # Verify the correct key by simulation on random inputs before writing.
    for _ in range(args.verify_vectors):
        x = {n: rng.randrange(2) for n in ins}
        expected = evaluate(ins, outs, gates, x)
        observed = evaluate(ins + key_inputs, outs, locked,
                            {**x, **{n: int(b) for n, b in zip(key_inputs, key)}})
        if expected != observed:
            raise AssertionError('Correct-key functional check failed')
    name = args.bench.stem
    tag = f'{name}-{args.scheme.upper()}{args.key_size}{args.instance}'
    folder = args.out / tag
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f'{name}-oracle.v').write_text(emit_verilog(name, ins, outs, gates))
    (folder / f'{tag}.v').write_text(emit_verilog(name, ins + key_inputs, outs, locked))
    metadata = {
        'benchmark': name, 'scheme': args.scheme,
        'locking': 'random XOR/XNOR on internal gate outputs',
        'note': 'EPIC-style combinational locking only; NOT Secure Logic Locking (SLL)',
        'key_size': args.key_size, 'seed': args.seed, 'instance': args.instance,
        'correct_key': key, 'key_bit_order': key_inputs,
        'primary_inputs': len(ins), 'primary_outputs': len(outs),
        'source_sha256': hashlib.sha256(args.bench.read_bytes()).hexdigest(),
        'random_vector_checks_passed': args.verify_vectors,
        'placements': placements,
    }
    (folder / 'key_metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    (folder / f'ReadMe_{tag}.txt').write_text(
        f'{tag}\nOriginal circuit: {name} ({args.bench.name})\n'
        f'Locking: random XOR/XNOR gates on internal gate outputs (NOT SLL)\n'
        f'Key size: {args.key_size}\nSeed: {args.seed}\n'
        f'Original inputs: {len(ins)}; locked inputs: {len(ins)+args.key_size}\n'
        f'Outputs: {len(outs)}\n'
        f'Correct-key random-vector checks: {args.verify_vectors} passed\n'
        f'Oracle: {name}-oracle.v\nLocked: {tag}.v\n'
        'Correct key and gate placements: key_metadata.json (evaluation only; do not expose to attack).\n'
        'No synthesized netlist is generated. Use a separate synthesis tool if required.\n'
        'Random simulation is not a formal equivalence proof.\n')
    print(f'Created: {folder}')
    print(f'Locked file: {folder / (tag + ".v")}')
    print(f'Oracle file: {folder / (name + "-oracle.v")}')
    print(f'Correct-key random-vector tests passed: {args.verify_vectors}')


if __name__ == '__main__':
    main()
