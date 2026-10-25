"""Strict reader for scalar psfascii traces saved by these Spectre testbenches."""
import re
import numpy as np

NUMBER = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")


def read_ascii(path, axis, names, complex_values=False):
    x, series = [], {name: [] for name in names}
    active = False
    with open(path, errors="strict") as stream:
        for raw in stream:
            line = raw.strip()
            if line == "VALUE":
                active = True
                continue
            if not active or not line.startswith('"'):
                continue
            _, name, rest = line.split('"', 2)
            if name != axis and name not in series:
                continue
            values = [float(value) for value in NUMBER.findall(rest)]
            expected = 2 if complex_values and name != axis else 1
            if len(values) != expected:
                raise ValueError(f"Malformed {name} sample in {path}: {line}")
            if name == axis:
                x.append(values[0])
            else:
                series[name].append(complex(*values) if complex_values else values[0])
    x = np.asarray(x)
    if len(x) < 2 or np.any(np.diff(x) <= 0) or not np.all(np.isfinite(x)):
        raise ValueError(f"Missing, nonfinite or unordered {axis} samples in {path}")
    for name, values in series.items():
        if len(values) != len(x) or not np.all(np.isfinite(values)):
            raise ValueError(f"Trace {name} has missing or nonfinite samples in {path}")
    return x, {name: np.asarray(values) for name, values in series.items()}
