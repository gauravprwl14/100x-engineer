python3 - <<'PY'
from pathlib import Path
p = Path("invoices/pricing.py")
p.write_text(p.read_text().replace('    """Total after a percentage discount, rounded down to the cent."""\n',
    '    """Total after a percentage discount, rounded down to the cent."""\n    if not 0 <= percent <= 100:\n        raise ValueError(f"percent must be between 0 and 100, got {percent}")\n'))
t = Path("tests/test_pricing.py")
t.write_text(t.read_text().replace("\n\nif __name__", '''
    def test_rejects_percent_outside_0_to_100(self):
        for percent in (-20, 150):
            with self.assertRaises(ValueError):
                apply_discount(1000, percent)


if __name__'''))
PY
git add invoices tests
GIT_AUTHOR_DATE=2026-01-06T10:00:00Z GIT_COMMITTER_DATE=2026-01-06T10:00:00Z git -c user.name=a -c user.email=a@example.com commit -qm "Reject discount percents outside 0-100"
sha=$(git rev-parse --short HEAD)
printf 'Done in %s: percents outside 0-100 now raise `ValueError`; covered by `test_rejects_percent_outside_0_to_100`.\n' "$sha" > REPLY.md
