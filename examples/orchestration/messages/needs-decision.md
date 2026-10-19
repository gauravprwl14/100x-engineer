Stopped: a C-class question blocks the service.

```json
{
  "schema": 1,
  "agent": "backend-engineer",
  "task_id": "T1",
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
      "why_it_matters": "Decides the column collation and the validation rule.",
      "options": [
        "yes, utf8mb4",
        "no, ASCII only"
      ],
      "recommendation": "yes, utf8mb4",
      "blocking": true
    },
    {
      "id": "Q2",
      "question": "Should tag removal be soft-deleted for audit?",
      "why_it_matters": "Retention is the user's call.",
      "options": [
        "soft delete",
        "hard delete"
      ],
      "recommendation": "soft delete",
      "blocking": false
    }
  ],
  "plan_issues": [
    {
      "id": "P1",
      "issue": "T0's contract has no max label length.",
      "impact": "T1 and T2 may validate differently.",
      "proposal": "Add maxLength 40 to CreateTagDto.",
      "blocking": false
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
