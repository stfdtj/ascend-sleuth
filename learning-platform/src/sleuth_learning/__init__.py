"""sleuth_learning -- offline MVP of the Ascend Sleuth Learning Platform.

Pipeline: Local Trace -> Collector -> Ingestion -> Generator -> Validation ->
Stored Learning Case -> Reader. Everything in this package runs locally,
against synthetic or explicitly-provided trace files; nothing here performs
network I/O. See ../README.md for scope, CLI usage and deviations from the
Astra design proposal this package implements a slice of.
"""

__version__ = "0.1.0"
