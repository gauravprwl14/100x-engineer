import { Injectable } from '@nestjs/common';

@Injectable()
export class SessionStore {
  async createSession(userId: string) { return { id: 's1', userId }; }
}
