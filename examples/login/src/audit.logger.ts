import { Injectable } from '@nestjs/common';

// A real collaborator the sequence diagram never mentions.
@Injectable()
export class AuditLogger {
  async record(event: string) { /* ... */ }
}
