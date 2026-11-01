"""Bit-parallel evaluation of a parsed netlist with every input fixed.

Each signal is a Python int whose bit i is the signal's value in lane i,
so one pass over the gates evaluates the circuit for many input sets at once.
"""
from functools import reduce
from operator import and_, or_, xor

INPUT_TYPES = ("Primary Input", "Key Input")


def gate_order(nodes, output_names):
    """Returns the gate names feeding output_names, each after all of its fanin."""
    order, done = [], set()
    for root in output_names:
        stack = [(root, False)]
        while stack:
            name, expanded = stack.pop()
            if name in done:
                continue
            node = nodes[name]
            if node.type in INPUT_TYPES:
                done.add(name)
            elif expanded:
                done.add(name)
                order.append(name)
            else:
                stack.append((name, True))
                stack.extend((child, False) for child in node.inputs if child not in done)
    return order


def evaluate_packed(nodes, order, output_names, inputs, mask):
    """
    Evaluates the circuit on packed inputs.

    order: gate names from gate_order
    inputs: maps every input name to its packed lanes
    mask: int with one set bit per lane in use
    returns: maps each output name to its packed lanes
    """
    values = dict(inputs)
    for name in order:
        node = nodes[name]
        fanin = [values[child] for child in node.inputs]
        kind = node.type
        if kind in ("And", "Nand"):
            v = reduce(and_, fanin)
        elif kind in ("Or", "Nor"):
            v = reduce(or_, fanin)
        elif kind in ("Xor", "Xnor"):
            v = reduce(xor, fanin)
        elif kind == "Not":
            v = fanin[0] ^ mask
        else:
            raise ValueError(f"Unknown node type {node}")
        if kind in ("Nand", "Nor", "Xnor"):
            v ^= mask
        values[name] = v
    return {name: values[name] for name in output_names}
