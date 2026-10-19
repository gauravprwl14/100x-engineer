#!/usr/bin/env python3
"""Print the content fingerprint that verification receipts are bound to.

    100x verify_fingerprint

Compare it with the `fingerprint` field of the receipt, at
`git rev-parse --git-path 100x/verification-receipt.json`: equal
means the receipt describes the current content. Exits 1 outside a git repository.
"""
import pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "hooks"))
from verify_fingerprint import fingerprint

if __name__ == "__main__":
    if any(a in ("-h", "--help") for a in sys.argv[1:]):
        print(__doc__.strip())
        sys.exit(0)
    fp = fingerprint()
    if not fp:
        print("not a git repository", file=sys.stderr)
        sys.exit(1)
    print(fp)
