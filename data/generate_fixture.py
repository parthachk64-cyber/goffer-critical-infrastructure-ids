"""Regenerate (or verify) the synthetic fixtures and their checksums.

    python data/generate_fixture.py            # rewrite fixtures + SHA256SUMS (seed 42)
    python data/generate_fixture.py --check    # fail if committed files differ from regeneration
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from infra_ids.synthetic import generate_pair, sha256_of, write_test_fixtures

ROOT = Path(__file__).resolve().parent
FIX = ROOT / "fixtures"
SEED = 42


def sums(directory: Path) -> str:
    names = ["synthetic_train.csv", "synthetic_test.csv"]
    return "".join(f"{sha256_of(directory / n)}  {n}\n" for n in names)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()

    if args.check:
        with tempfile.TemporaryDirectory() as tmp:
            generate_pair(args.seed, Path(tmp))
            expected, committed = sums(Path(tmp)), (FIX / "SHA256SUMS").read_text()
        if expected != committed:
            print("MISMATCH: committed fixtures differ from regeneration", file=sys.stderr)
            return 1
        print("fixtures match SHA256SUMS")
        return 0

    generate_pair(args.seed, FIX)
    (FIX / "SHA256SUMS").write_text(sums(FIX), newline="\n")
    write_test_fixtures(ROOT.parent / "tests" / "fixtures", args.seed)
    print((FIX / "SHA256SUMS").read_text(), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
