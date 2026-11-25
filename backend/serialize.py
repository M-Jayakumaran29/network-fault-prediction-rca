"""JSON-safe conversion of numpy/pandas scalar types returned by the
prediction and RCA modules (numpy.int64, numpy.float64, numpy.bool_, NaN, etc.)."""
import math
import numpy as np


def to_native(value):
    if isinstance(value, dict):
        return {k: to_native(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_native(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        f = float(value)
        return None if math.isnan(f) else f
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, float) and math.isnan(value):
        return None
    return value
