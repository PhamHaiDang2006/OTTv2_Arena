import { ThemeSwitch } from './preferences';
import React, { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { api, session } from './api';
import { Field, ErrorBox } from './ui';
import { adminUrl, participantUrl } from './urls';
import { PieceIcon } from './casual-presentation';
export function Login({ initialError, admin = false }: { initialError?: unknown; admin?: boolean }) {
  const cache = useQueryClient();
  const [registering, setRegistering] = useState(false);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(initialError);
  return (
    <main className={`auth-page ${admin ? 'auth-admin' : ''}`}>
      <header className="auth-topbar">
        <a className="auth-logo" href={participantUrl}>
          ◈ OTTv2 <span>PLAY YOUR NEXT MOVE</span>
        </a>
        <ThemeSwitch />
      </header>
      <div className="login auth-layout">
        <div className="login-brand">
          <span className="auth-kicker">BÚA · BAO · KÉO / BÀN CỜ 9 × 9</span>
          <h1>
            Mỗi nước đi,
            <br />
            một khả năng mới.
          </h1>
          <p>Thử một chiến thuật. Viết một đối thủ. Tìm phong cách chơi của riêng bạn.</p>
          <div className="auth-art" aria-hidden="true">
            <div className="auth-grid" />
            {['B', 'P', 'K'].map((piece, i) => (
              <div className={`auth-medallion medallion-${i}`} key={piece}>
                <PieceIcon piece={piece} />
              </div>
            ))}
            <span className="art-coordinate">a1 → i9</span>
          </div>
          <div className="auth-modes">
            <span>
              <i />
              Casual
            </span>
            <span>
              <i />
              Tự luyện
            </span>
            <span>
              <i />
              Arena
            </span>
          </div>
        </div>
        <section
          className="card auth-card"
          aria-label={registering ? 'Đăng ký tài khoản' : 'Đăng nhập tài khoản'}
        >
          <span className="eyebrow">
            {admin ? 'CỔNG QUẢN TRỊ' : registering ? 'BẮT ĐẦU HÀNH TRÌNH' : 'CHÀO MỪNG ĐẾN OTTv2'}
          </span>
          <h2>{registering ? 'Tạo tài khoản của bạn' : 'Chào mừng trở lại'}</h2>
          <p className="muted">
            {registering
              ? 'Tạo đội riêng để nộp bot và đấu tập. Tham gia giải cần được duyệt.'
              : admin
                ? 'Đăng nhập để quản lý đội và điều hành giải đấu.'
                : 'Đăng nhập để tiếp tục ván cờ và khám phá chiến thuật mới.'}
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
                <input
                  name="team_name"
                  placeholder="Tên đội của bạn"
                  autoComplete="organization"
                  required
                  maxLength={100}
                />
              </Field>
            )}
            <Field label="Email">
              <input
                name="email"
                type="email"
                placeholder="ban@example.com"
                autoComplete="username"
                maxLength={320}
                required
              />
            </Field>
            <Field label="Mật khẩu">
              <input
                name="password"
                placeholder={registering ? 'Ít nhất 8 ký tự' : 'Nhập mật khẩu của bạn'}
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
                  placeholder="Nhập lại mật khẩu vừa tạo"
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
              className="auth-switch"
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
          <p className="auth-portal">
            <a href={admin ? participantUrl : adminUrl}>
              {admin ? 'Về cổng thí sinh' : 'Đăng nhập quản trị'}
            </a>
          </p>
        </section>
      </div>
      <footer className="auth-footer">
        <span>OTT v2 · Chiến thuật bắt đầu từ bạn.</span>
        <a href={participantUrl}>← Về trang chọn chế độ</a>
      </footer>
    </main>
  );
}
