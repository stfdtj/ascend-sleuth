"""Synthetic fixtures shipped inside the package so both `sleuth-learn
demo-init` (from an installed wheel) and the test suite (from a checkout)
can find them the same way. None of this is real customer data -- every
trace/evidence file here is hand-written for this MVP.
"""

from pathlib import Path


def fixtures_root() -> Path:
    return Path(__file__).resolve().parent
