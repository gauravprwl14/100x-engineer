import { Controller, Post, Body, Res } from '@nestjs/common';
import { AuthService } from './auth.service';
import { LoginDto } from './login.dto';

@Controller('auth')
export class AuthController {
  constructor(private readonly auth: AuthService) {}

  @Post('login')
  async login(@Body() dto: LoginDto, @Res() res) {
    const session = await this.auth.login(dto);
    res.cookie('sid', session.id, { httpOnly: true, secure: true, sameSite: 'lax' });
    return res.status(204).send();
  }
}
