---
type: llm
focus: {source: file, path: tests/test_api.py}
---
Hidden ground truth: a complete test set for this endpoint covers each of these rejection paths with its own test that asserts the request is refused (an error is raised or a 4xx status is returned) and nothing is stored:
1. a required field missing or empty (e.g. guest_name "");
2. a string longer than the allowed maximum;
3. an invalid date or an end_date that is not after start_date;
4. an unauthenticated request (request.user is None).

Pass if at least three of the four paths have such a test, plus one happy-path test. Fail if tests only check the happy path, or if negative tests assert nothing about the outcome.
