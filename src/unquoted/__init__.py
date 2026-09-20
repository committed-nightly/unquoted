"""Show what YAML's plain scalars actually become, and where implementations disagree."""

from .report import PLAIN, QUIET, RETYPED, REWRITTEN, SPLIT, Finding, judge, judge_all
from .scan import PlainScalar, ScanError, scan, scan_file

__version__ = "0.1.0"

__all__ = [
    "PLAIN",
    "QUIET",
    "RETYPED",
    "REWRITTEN",
    "SPLIT",
    "Finding",
    "PlainScalar",
    "ScanError",
    "__version__",
    "judge",
    "judge_all",
    "scan",
    "scan_file",
]
