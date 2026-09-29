import { Injectable } from '@nestjs/common';

@Injectable()
export class UserRepository {
  async findByEmail(email: string) {
    return { id: 'u1', email, passwordHash: '$argon2id$...' };
  }
}
