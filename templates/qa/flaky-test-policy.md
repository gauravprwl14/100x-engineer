# Flaky-test policy

A flaky test passes and fails on the same code. Google measured that about 1.5% of its
test runs reported a flaky result, and almost 16% of its tests had some flakiness
(John Micco, "Flaky Tests at Google and How We Mitigate Them", Google Testing Blog, 2016,
https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html).
Retrying forever hides real races; deleting hides coverage. This policy does neither.
The numbers below (2 flakes / 7 days, 14-day expiry, 2% budget) are starting defaults,
`SOURCE: original`; tune them, but keep an owner and an expiry on every entry.

| rule | detail |
|---|---|
| rerun | CI retries a failed test **once** (`retries: 1` in Playwright). A pass on retry is reported as *flaky*, never silently green |
| quarantine | a test flaky twice in 7 days moves to the quarantine list below and out of the blocking suite; it still runs, non-blocking |
| owner + expiry | every quarantined test has a named owner and an expiry date at most 14 days out |
| expiry | on expiry the test is fixed, or deleted with its AC re-covered by another test (`100x testplan trace` must still pass) |
| no sleeps | a fix that adds a fixed sleep is rejected; wait on a condition or inject a clock |
| budget | if quarantine holds more than 2% of the suite, new feature work pauses for a fix-it |

## Quarantine list

| test | AC id | owner | quarantined | expires | issue |
|---|---|---|---|---|---|
