import { Injectable, UnauthorizedException } from '@nestjs/common';
import { UserRepository } from './user.repository';
import { SessionStore } from './session.store';
import { PasswordHasher } from './password.hasher';

@Injectable()
export class AuthService {
  constructor(
    private readonly users: UserRepository,
    private readonly sessions: SessionStore,
    private readonly hasher: PasswordHasher,
  ) {}

  async login(dto: { email: string; password: string }) {
    const user = await this.users.findByEmail(dto.email);
    const ok = await this.hasher.verify(user.passwordHash, dto.password);
    if (!ok) throw new UnauthorizedException();
    return this.sessions.createSession(user.id);
  }
}
