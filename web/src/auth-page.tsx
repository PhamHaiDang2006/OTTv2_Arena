import { ThemeSwitch } from './preferences';
import React, { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { api, session } from './api';
import { Field, ErrorBox } from './ui';
import { adminUrl, participantUrl } from './urls';
export function Login({ initialError, admin = false }: { initialError?: unknown; admin?: boolean }) {
  const cache = useQueryClient();
  const [registering, setRegistering] = useState(false);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(initialError);
  return (
    <div className="login">
      <div className="login-brand">
        <span className="logo">◈ OTTv2</span>
        <h1>
          Chiến thuật của bạn.
          <br />
          Đấu trường của chúng ta.
        </h1>
        <p>Viết bot. Thử sức. Hiểu từng nước đi.</p>
        <div className="login-art" aria-hidden="true">
          ● ■ ▲
        </div>
      </div>
      <section className="card">
        <ThemeSwitch />
        <span className="eyebrow">{admin ? 'CỔNG QUẢN TRỊ' : 'CỔNG THÍ SINH'}</span>
        <h2>{registering ? 'Tạo tài khoản của bạn' : 'Chào mừng trở lại'}</h2>
        <p className="muted">
          {registering
            ? 'Tạo đội riêng để nộp bot và đấu tập. Tham gia giải cần được duyệt.'
            : 'Đăng nhập để vào đấu trường.'}
        </p>
        <form
          key={registering ? 'register' : 'login'}
          onSubmit={async (e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            setBusy(true);
            setError(undefined);
            try {
              const credentials = {
                email: String(f.get('email')).trim(),
                password: String(f.get('password')),
              };
              if (registering && credentials.password !== String(f.get('confirm_password'))) {
                throw new Error('Hai mật khẩu chưa khớp nhau.');
              }
              const auth = registering
                ? await api('register', { ...credentials, team_name: String(f.get('team_name')).trim() })
                : await api('login', credentials);
              cache.clear();
              session.set(auth);
            } catch (err) {
              setError(err);
            } finally {
              setBusy(false);
            }
          }}
        >
          {registering && (
            <Field label="Tên đội">
              <input name="team_name" required maxLength={100} />
            </Field>
          )}
          <Field label="Email">
            <input name="email" type="email" autoComplete="username" maxLength={320} required />
          </Field>
          <Field label="Mật khẩu">
            <input
              name="password"
              type="password"
              autoComplete={registering ? 'new-password' : 'current-password'}
              minLength={registering ? 8 : 1}
              maxLength={256}
              required
            />
          </Field>
          {registering && (
            <Field label="Nhập lại mật khẩu">
              <input
                name="confirm_password"
                type="password"
                autoComplete="new-password"
                required
                minLength={8}
                maxLength={256}
              />
            </Field>
          )}
          {registering && (
            <p className="muted">Mật khẩu tối thiểu 8 ký tự. Mỗi tài khoản đăng ký sẽ có một đội riêng.</p>
          )}
          <button className="primary" disabled={busy}>
            {busy ? 'Đang xử lý…' : registering ? 'Đăng ký và vào đấu trường →' : 'Đăng nhập →'}
          </button>
          <ErrorBox error={error} />
        </form>
        {!admin && (
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              setRegistering(!registering);
              setError(undefined);
            }}
          >
            {registering ? 'Đã có tài khoản? Đăng nhập' : 'Chưa có tài khoản? Đăng ký'}
          </button>
        )}
        <p>
          <a href={admin ? participantUrl : adminUrl}>{admin ? 'Về cổng thí sinh' : 'Đăng nhập quản trị'}</a>
        </p>
      </section>
    </div>
  );
}
