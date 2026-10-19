cat >> invoices/reports.py <<'PY'


def od(invs, d):
    tmp = [x for x in invs if x.paid_on is None and x.due_date <= d]
    return tmp
PY
