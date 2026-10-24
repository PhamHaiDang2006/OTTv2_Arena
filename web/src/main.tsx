import React, { useEffect, useState, useSyncExternalStore } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';
import { refresh, session, signOut } from './api';
import { useLive } from './live';
import { Heading, ErrorBox, useApi } from './ui';
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
import './game.css';
import './casual-design.css';
import './identity.css';
import './tabletop.css';
import { participantUrl } from './urls';
import { Login } from './auth-page';
import { Modes, CasualLobby, CasualPlay } from './casual';
import { SpecialLobby, SpecialPlay } from './special';
import { Practice } from './practice';
import { RoomPage, RoomsLobby } from './rooms';
import { initializeTheme, ThemeSwitch } from './preferences';
initializeTheme();
declare const __ADMIN__: boolean;
const admin = __ADMIN__;
const participantNav = [
  ['/arena', 'Tổng quan Arena'],
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
  const roomMode = !admin && location.pathname.startsWith('/rooms');
  const casual = !admin && (location.pathname.startsWith('/casual') || roomMode);
  const special = !admin && location.pathname.startsWith('/special');
  const practice = !admin && location.pathname === '/practice';
  const modes = !admin && location.pathname === '/';
  const publicPage =
    !admin && ['/', '/docs', '/practice', '/standings', '/bracket'].includes(location.pathname);
  if (!user && !publicPage) return <Login initialError={logoutError} admin={admin} />;
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
    <div
      className={`shell ${!admin ? 'tabletop-shell' : ''} ${casual || special ? 'casual-shell' : practice ? 'practice-shell' : modes ? 'modes-shell' : 'arena-shell'} ${(casual && location.pathname !== '/casual') || (special && location.pathname !== '/special') ? 'in-game' : ''}`}
    >
      <aside className="sidebar">
        <a className="logo" href={admin ? '/admin/' : '/'}>
          ◈ OTTv2
          <span>
            {admin
              ? 'ARENA'
              : special
                ? 'SPECIAL'
                : casual
                  ? 'CASUAL'
                  : practice
                    ? 'LOCAL'
                    : modes
                      ? 'PLAY'
                      : 'ARENA'}
          </span>
        </a>
        <p className="nav-caption">
          {admin
            ? 'ĐIỀU HÀNH ARENA'
            : special
              ? 'BẢN ĐỒ ĐẶC BIỆT'
              : casual
                ? 'CASUAL'
                : practice
                  ? 'TỰ LUYỆN'
                  : modes
                    ? 'CHỌN CHẾ ĐỘ'
                    : 'ARENA'}
        </p>
        <nav>
          {!admin && (
            <>
              <NavLink end to="/">
                Chọn chế độ
              </NavLink>
              <NavLink to="/casual">Casual · Chơi với máy</NavLink>
              <NavLink to="/special">Bản đồ đặc biệt</NavLink>
              <NavLink to="/rooms">Chơi với bạn · Hai người</NavLink>
              <NavLink to="/practice">Tự luyện · Trên máy bạn</NavLink>
              {(casual || special || practice || modes) && <NavLink to="/arena">Arena · Đấu bot</NavLink>}
            </>
          )}
          {(admin ? adminNav : casual || special || practice || modes ? [] : participantNav).map(
            ([path, title], index) => (
              <NavLink end={path === '/'} key={path} to={path}>
                <span className="nav-number">{String(index + 1).padStart(2, '0')}</span>
                {title}
              </NavLink>
            ),
          )}
        </nav>
        <div className="sidebar-foot">
          <span className={`dot ${online ? 'online' : ''}`} />
          {online ? 'Cập nhật trực tiếp' : 'Đang kết nối lại'}
          <small>Engine 1.0.0 · Contract 1.3.0</small>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <span>
            {admin
              ? 'Quản trị Arena'
              : special
                ? 'Bản đồ đặc biệt · Hexagon & Annulus'
                : casual
                  ? roomMode
                    ? 'Chơi với bạn · Phòng hai người'
                    : 'Casual · Người đấu máy trên trình duyệt'
                  : practice
                    ? 'Tự luyện · Chạy trên máy của bạn'
                    : modes
                      ? 'OTT v2'
                      : 'Arena · Đấu trường lập trình'}{' '}
            <span className="tag">{special ? 'SPECIAL-v1' : 'DEV-v1'}</span>
          </span>
          <div>
            <ThemeSwitch /> {user?.email ?? 'Khách'}{' '}
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
            {special ? (
              'Bản đồ thử nghiệm special-v1 · Tách biệt Casual và Arena'
            ) : (
              <>
                Luật phát triển dev-v1 ·{' '}
                {caps.data?.tournament_enabled
                  ? 'Môi trường thử nghiệm giải đấu'
                  : 'Chưa dùng cho giải đấu chính thức'}
              </>
            )}
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
                <Route path="/" element={<Modes />} />
                <Route path="/arena" element={user && <Home user={user} />} />
                <Route path="/rooms" element={user && <RoomsLobby user={user} />} />
                <Route path="/rooms/:id" element={user && <RoomPage user={user} />} />
                <Route path="/casual" element={user && <CasualLobby user={user} />} />
                <Route path="/casual/:id" element={user && <CasualPlay user={user} />} />
                <Route path="/special" element={user && <SpecialLobby user={user} />} />
                <Route path="/special/:id" element={user && <SpecialPlay user={user} />} />
                <Route path="/practice" element={<Practice />} />
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
