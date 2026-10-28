"""Evaluation harness: datasets, scale benchmark and evidence coverage (LLM runs come later)."""

from subforest.eval.datasets import FETCHERS, Dataset, GoldSpan, Question, data_root
from subforest.eval.offline import BenchReport, CoverageReport, bench, coverage

__all__ = [
    "FETCHERS",
    "BenchReport",
    "CoverageReport",
    "Dataset",
    "GoldSpan",
    "Question",
    "bench",
    "coverage",
    "data_root",
]
