"""Distribution summaries and drift indicators: PSI, KS statistic, Jensen-Shannon distance.

PSI binning: bin edges are the reference deciles (``bins`` quantile bins computed on the
reference sample only), extended to minus and plus infinity. Bins are laplace-smoothed
with ``epsilon`` on each side so a bin empty in one sample does not produce an infinite
term. The same reference edges are used for the Jensen-Shannon distance.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.spatial.distance import jensenshannon
from scipy.stats import ks_2samp

EPSILON = 1e-4


@dataclass(frozen=True)
class ReferenceBins:
    edges: np.ndarray            # length bins + 1, first -inf, last +inf
    reference_counts: np.ndarray
    n_reference: int

    def to_dict(self) -> dict[str, Any]:
        finite = [None if not np.isfinite(e) else float(e) for e in self.edges]
        return {"edges": finite, "reference_counts": self.reference_counts.astype(int).tolist(), "n_reference": self.n_reference}


def reference_bins(reference: np.ndarray, bins: int = 10) -> ReferenceBins:
    ref = _clean(reference)
    if ref.size < bins:
        raise ValueError(f"need at least {bins} reference values to build {bins} quantile bins, got {ref.size}")
    quantiles = np.quantile(ref, np.linspace(0, 1, bins + 1)[1:-1])
    edges = np.concatenate(([-np.inf], np.unique(quantiles), [np.inf]))
    counts, _ = np.histogram(ref, bins=edges)
    return ReferenceBins(edges=edges, reference_counts=counts, n_reference=int(ref.size))


def _clean(values: np.ndarray | list[Any]) -> np.ndarray:
    arr = np.asarray([v for v in values if v is not None], dtype=float)
    return arr[np.isfinite(arr)]


def _proportions(counts: np.ndarray, epsilon: float) -> np.ndarray:
    smoothed = counts.astype(float) + epsilon
    return smoothed / smoothed.sum()


def psi(bins: ReferenceBins, current: np.ndarray | list[Any], epsilon: float = EPSILON) -> dict[str, Any]:
    cur = _clean(current)
    if cur.size == 0:
        return {"value": None, "n": 0, "bin_counts": None}
    counts, _ = np.histogram(cur, bins=bins.edges)
    p = _proportions(bins.reference_counts, epsilon)
    q = _proportions(counts, epsilon)
    value = float(np.sum((q - p) * np.log(q / p)))
    return {"value": round(value, 6), "n": int(cur.size), "bin_counts": counts.astype(int).tolist()}


def ks_statistic(reference: np.ndarray | list[Any], current: np.ndarray | list[Any]) -> dict[str, Any]:
    ref, cur = _clean(reference), _clean(current)
    if ref.size == 0 or cur.size == 0:
        return {"value": None, "p_value": None, "n": int(cur.size)}
    result = ks_2samp(ref, cur, method="asymp")
    return {"value": round(float(result.statistic), 6), "p_value": float(result.pvalue), "n": int(cur.size)}


def js_distance(bins: ReferenceBins, current: np.ndarray | list[Any], epsilon: float = EPSILON) -> dict[str, Any]:
    cur = _clean(current)
    if cur.size == 0:
        return {"value": None, "n": 0}
    counts, _ = np.histogram(cur, bins=bins.edges)
    value = float(jensenshannon(_proportions(bins.reference_counts, epsilon), _proportions(counts, epsilon), base=2))
    return {"value": round(value, 6), "n": int(cur.size)}


def summary(values: np.ndarray | list[Any]) -> dict[str, Any]:
    arr = _clean(values)
    if arr.size == 0:
        return {"n": 0, "mean": None, "std": None, "q05": None, "q50": None, "q95": None, "min": None, "max": None}
    q05, q50, q95 = np.quantile(arr, [0.05, 0.5, 0.95])
    return {
        "n": int(arr.size),
        "mean": round(float(arr.mean()), 6),
        "std": round(float(arr.std(ddof=0)), 6),
        "q05": round(float(q05), 6),
        "q50": round(float(q50), 6),
        "q95": round(float(q95), 6),
        "min": round(float(arr.min()), 6),
        "max": round(float(arr.max()), 6),
    }
