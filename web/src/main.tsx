import React, { useEffect, useState, useSyncExternalStore } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';
import { api, refresh, session, signOut } from './api';
import { useLive } from './live';
import { Field, Heading, ErrorBox, useApi } from './ui';
import { Docs, GamePage, Home, MatchDetail, Scrimmage, Standings, Submissions, Upload } from './participant';
import {
  AdminMatches,
  AnnouncementsPage,
  AuditPage,
  DrawPage,
  QueuePage,
  Rounds,
  SimilarityPage,
  SourcePage,
  Teams,
} from './admin';
import './style.css';
import { adminUrl, participantUrl } from './urls';
declare const __ADMIN__: boolean;
const admin = __ADMIN__;
const participantNav = [
  ['/', 'Tổng quan'],
  ['/submit', 'Nộp bot'],
  ['/submissions', 'Bản nộp'],
  ['/scrimmage', 'Đánh tập'],
  ['/standings', 'Bảng xếp hạng'],
  ['/bracket', 'Nhánh đấu'],
  ['/docs', 'Tài liệu'],
];
const adminNav = [
  ['/teams', 'Đội thi đấu'],
  ['/draw', 'Bốc thăm'],
  ['/rounds', 'Vòng đấu'],
  ['/matches', 'Trận đấu'],
  ['/queue', 'Hàng đợi'],
  ['/announcements', 'Thông báo'],
  ['/submissions', 'Mã nguồn'],
  ['/similarity', 'Trùng lặp'],
  ['/audit-log', 'Kiểm toán'],
];
function Login({ initialError }: { initialError?: unknown }) {
  const cache = useQueryClient();
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
        <span className="eyebrow">{admin ? 'CỔNG QUẢN TRỊ' : 'CỔNG THÍ SINH'}</span>
        <h2>Chào mừng trở lại</h2>
        <p className="muted">Đăng nhập bằng tài khoản do ban tổ chức cấp.</p>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            setBusy(true);
            setError(undefined);
            try {
              const auth = await api('login', {
                email: String(f.get('email')),
                password: String(f.get('password')),
              });
              cache.clear();
              session.set(auth);
            } catch (err) {
              setError(err);
            } finally {
              setBusy(false);
            }
          }}
        >
          <Field label="Email">
            <input name="email" type="email" autoComplete="username" required />
          </Field>
          <Field label="Mật khẩu">
            <input name="password" type="password" autoComplete="current-password" required />
          </Field>
          <button className="primary" disabled={busy}>
            {busy ? 'Đang đăng nhập…' : 'Đăng nhập →'}
          </button>
          <ErrorBox error={error} />
        </form>
        <p>
          <a href={admin ? participantUrl : adminUrl}>{admin ? 'Về cổng thí sinh' : 'Đăng nhập quản trị'}</a>
        </p>
      </section>
    </div>
  );
}
function App() {
  const user = useSyncExternalStore(session.subscribe, session.user);
  const [booting, setBooting] = useState(true),
    [logoutError, setLogoutError] = useState<unknown>();
  const cache = useQueryClient(),
    location = useLocation(),
    online = useLive(user);
  const caps = useApi('capabilities');
  useEffect(() => {
    void refresh()
      .catch(() => {})
      .finally(() => setBooting(false));
  }, []);
  if (booting)
    return (
      <p className="boot" role="status">
        Đang khôi phục phiên đăng nhập…
      </p>
    );
  const publicPage = !admin && ['/docs', '/standings', '/bracket'].includes(location.pathname);
  if (!user && !publicPage) return <Login initialError={logoutError} />;
  if (admin && user?.role !== 'admin')
    return (
      <main className="card">
        <h1>Không có quyền quản trị</h1>
        <p>Tài khoản hiện tại không có vai trò admin.</p>
        <a href={participantUrl}>Về cổng thí sinh</a>
        <button onClick={() => void signOut().catch(setLogoutError)}>Đổi tài khoản</button>
        <ErrorBox error={logoutError} />
      </main>
    );
  return (
    <div className="shell">
      <aside className="sidebar">
        <a className="logo" href={admin ? '/admin/' : '/'}>
          ◈ OTTv2<span>ARENA</span>
        </a>
        <p className="nav-caption">{admin ? 'ĐIỀU HÀNH GIẢI' : 'KHÔNG GIAN THI ĐẤU'}</p>
        <nav>
          {(admin ? adminNav : participantNav).map(([path, title], index) => (
            <NavLink end={path === '/'} key={path} to={path}>
              <span className="nav-number">{String(index + 1).padStart(2, '0')}</span>
              {title}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <span className={`dot ${online ? 'online' : ''}`} />
          {online ? 'Cập nhật trực tiếp' : 'Đang kết nối lại'}
          <small>Engine 1.0.0 · Contract 1.0.0</small>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <span>
            {admin ? 'Trung tâm quản trị' : 'Cổng thí sinh'} <span className="tag">DEV-v1</span>
          </span>
          <div>
            {user?.email ?? 'Khách'}{' '}
            {user ? (
              <button
                onClick={async () => {
                  try {
                    await signOut();
                  } catch (e) {
                    setLogoutError(e);
                  } finally {
                    cache.clear();
                  }
                }}
              >
                Đăng xuất
              </button>
            ) : (
              <NavLink to="/login">Đăng nhập</NavLink>
            )}
          </div>
        </header>
        <main>
          <div className="development">
            Luật phát triển dev-v1 ·{' '}
            {caps.data?.tournament_enabled
              ? 'Môi trường thử nghiệm giải đấu'
              : 'Chưa dùng cho giải đấu chính thức'}
          </div>
          <ErrorBox error={logoutError} />
          <Routes>
            {admin ? (
              <>
                <Route path="/" element={<Navigate replace to="/teams" />} />
                <Route path="/teams" element={<Teams />} />
                <Route path="/draw" element={<DrawPage />} />
                <Route path="/rounds" element={<Rounds />} />
                <Route path="/matches" element={<AdminMatches />} />
                <Route path="/queue" element={<QueuePage />} />
                <Route path="/announcements" element={<AnnouncementsPage />} />
                <Route path="/similarity" element={<SimilarityPage />} />
                <Route path="/audit-log" element={<AuditPage />} />
              </>
            ) : (
              <>
                <Route path="/" element={user && <Home user={user} />} />
                <Route path="/submit" element={<Upload />} />
                <Route path="/scrimmage" element={<Scrimmage />} />
                <Route path="/standings" element={<Standings />} />
                <Route path="/bracket" element={<Standings bracket />} />
                <Route path="/docs" element={<Docs />} />
              </>
            )}
            <Route path="/login" element={<Navigate to="/" replace />} />
            <Route path="/submissions" element={user && <Submissions user={user} admin={admin} />} />
            <Route path="/submissions/:id" element={<SourcePage admin={admin} />} />
            <Route path="/matches/:id" element={<MatchDetail />} />
            <Route path="/games/:id" element={<GamePage admin={admin} />} />
            <Route
              path="*"
              element={
                <Heading
                  title="Không tìm thấy trang"
                  description="Chọn một mục trong thanh điều hướng để tiếp tục."
                />
              }
            />
          </Routes>
        </main>
        <footer>OTTv2 Arena · Búa / Bao / Kéo · 9 × 9</footer>
      </div>
    </div>
  );
}
const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: 10000 }, mutations: { retry: false } },
});
let cachedUser: string | undefined;
session.subscribe(() => {
  const next = session.user()?.id;
  if (cachedUser !== next) {
    queryClient.clear();
    cachedUser = next;
  }
});
createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename={admin ? '/admin' : '/'}>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
