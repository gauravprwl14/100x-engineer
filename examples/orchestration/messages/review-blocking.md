Security review of T1: one blocking finding.

```json
{
  "schema": 1,
  "agent": "security-reviewer",
  "task_id": "SEC-T1",
  "status": "needs-decision",
  "understanding": "Review T1's tagging service for tenancy and authorisation gaps.",
  "inputs_read": [
    "backend/src/tagging/services/tag.service.ts"
  ],
  "assumptions": [],
  "questions": [],
  "plan_issues": [],
  "decisions": [],
  "changes": [],
  "evidence": [],
  "findings": [
    {
      "id": "F1",
      "severity": "critical",
      "confidence": "probable",
      "location": "backend/src/tagging/services/tag.service.ts:remove",
      "issue": "remove() deletes by tag id without scoping by companyId.",
      "fix": "Add companyId from the JWT to the delete's where clause.",
      "blocking": true
    }
  ],
  "follow_ups": []
}
```
