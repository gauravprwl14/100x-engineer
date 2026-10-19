Stopped: my task is not in the plan.

```json
{
  "schema": 1,
  "agent": "backend-engineer",
  "task_id": "T9",
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
  "questions": [],
  "plan_issues": [
    {
      "id": "P1",
      "issue": "T9 is not in the plan.",
      "impact": "no owned files",
      "proposal": "add T9",
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
