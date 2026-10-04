# Exploratory testing charter

Charter shape from the "Charter Your Explorations" chapter of Elisabeth Hendrickson,
*Explore It!* (Pragmatic Bookshelf, 2013, https://pragprog.com/titles/ehxta/explore-it/):
explore a *target*, with *resources*, to discover *information*. Timeboxed sessions and
debriefs follow session-based test management (Jonathan Bach and James Bach, 2000,
https://www.satisfice.com/download/session-based-test-management). Write one charter per
risky area; automation cannot find what nobody thought to assert.

| field | value |
|---|---|
| charter | Explore `<target>` with `<resources: data, roles, devices, tools>` to discover `<information: risk to learn about>` |
| areas | `<screens, endpoints, states>` |
| risks | `<what could go wrong that no automated test asserts>` |
| timebox | 60–90 min, one tester, no interruptions |
| tester / date | |
| build / environment | |

## Notes

- what was tried (inputs, states, interrupted flows, slow network, keyboard only, screen reader)
- what was observed

## Bugs

| # | summary | steps | severity |
|---|---|---|---|

## Issues and questions

- anything blocking, unclear in the spec, or worth a follow-up charter

## Debrief

- coverage achieved vs. the charter; % time on test vs. bug investigation vs. setup
- new automated tests to add (tag with the AC id)
