Implemented the tagging service.

```json
{
  "schema": 1,
  "agent": "frontend-engineer",
  "task_id": "T1",
  "status": "done",
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
  "plan_issues": [],
  "decisions": [
    {
      "id": "D1",
      "decision": "Keep the author check in the service, not the controller.",
      "door": "two-way",
      "basis": "precedent:backend/src/album/"
    }
  ],
  "changes": [
    {
      "path": "backend/src/tagging/services/tag.service.ts",
      "summary": "add/list/remove"
    },
    {
      "path": "backend/src/tagging/tagging.module.ts",
      "summary": "register the service"
    }
  ],
  "evidence": [
    {
      "cmd": "test -f plan.json",
      "exit_code": 0,
      "output_tail": ""
    },
    {
      "cmd": "python3 -c \"import json; json.load(open('plan.json'))\"",
      "exit_code": 0,
      "output_tail": ""
    }
  ],
  "follow_ups": []
}
```
