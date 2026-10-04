Stopped on the contract.

```json
{
  "schema": 1,
  "agent": "frontend-engineer",
  "task_id": "T2",
  "status": "needs-decision",
  "understanding": "Implement the tagging service against the T0 contract: add, list newest-first, remove by author or admin.",
  "inputs_read": [
    "spec.md#acceptance-criteria",
    "backend/src/tagging/dto/create-tag.dto.ts"
  ],
  "assumptions": [
    {
      "id": "A1",
      "text": "Every tag query is scoped by companyId from the JWT.",
      "class": "A",
      "basis": "baseline:api.authz-every-endpoint"
    }
  ],
  "questions": [
    {
      "id": "Q1",
      "question": "May a tag label contain emoji?",
      "why_it_matters": "The chip width depends on it.",
      "options": [
        "yes",
        "no"
      ],
      "recommendation": "yes",
      "blocking": true
    },
    {
      "id": "Q2",
      "question": "Non-blocking UI question 2?",
      "blocking": false,
      "options": [
        "a",
        "b"
      ],
      "recommendation": "a"
    },
    {
      "id": "Q3",
      "question": "Non-blocking UI question 3?",
      "blocking": false,
      "options": [
        "a",
        "b"
      ],
      "recommendation": "a"
    },
    {
      "id": "Q4",
      "question": "Non-blocking UI question 4?",
      "blocking": false,
      "options": [
        "a",
        "b"
      ],
      "recommendation": "a"
    },
    {
      "id": "Q5",
      "question": "Non-blocking UI question 5?",
      "blocking": false,
      "options": [
        "a",
        "b"
      ],
      "recommendation": "a"
    },
    {
      "id": "Q6",
      "question": "Non-blocking UI question 6?",
      "blocking": false,
      "options": [
        "a",
        "b"
      ],
      "recommendation": "a"
    }
  ],
  "plan_issues": [
    {
      "id": "P1",
      "issue": "T2 needs the T0 list response to include the author's display name.",
      "impact": "UI cannot render author",
      "proposal": "add authorName to TagDto",
      "blocking": true
    }
  ],
  "decisions": [
    {
      "id": "D1",
      "decision": "Keep the author check in the service, not the controller.",
      "door": "two-way",
      "basis": "precedent:backend/src/album/"
    }
  ],
  "changes": [],
  "evidence": [],
  "follow_ups": []
}
```
