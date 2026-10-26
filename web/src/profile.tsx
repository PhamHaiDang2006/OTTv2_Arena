import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { Profile, ProfileEdit, User } from '../../contracts/generated/types';
import { api } from './api';
import { ErrorBox, Heading } from './ui';
import { PieceIcon } from './casual-presentation';
import './profile.css';

const avatars = { hammer: 'Búa', paper: 'Bao', scissors: 'Kéo', fox: 'Cáo', owl: 'Cú', cat: 'Mèo' };
const frames = { none: 'Đơn giản', bronze: 'Đồng', laurel: 'Nguyệt quế', double: 'Viền đôi' };
const colors = { amber: 'Hổ phách', jade: 'Ngọc', ocean: 'Biển', violet: 'Tím', rose: 'Hồng' };
const mapNames = { standard: 'Casual 9×9', hexagon: 'Hexagon', circular: 'Annulus' };
const defaults: ProfileEdit = { display_name: '', bio: '', avatar: 'hammer', frame: 'none', color: 'amber' };

export function Avatar({ profile }: { profile: Pick<ProfileEdit, 'avatar' | 'frame' | 'color'> }) {
  const piece = { hammer: 'B', paper: 'P', scissors: 'K' }[profile.avatar as 'hammer'];
  return (
    <span
      className={`profile-avatar frame-${profile.frame} profile-${profile.color}`}
      role="img"
      aria-label={`Avatar ${avatars[profile.avatar]}, khung ${frames[profile.frame]}`}
    >
      {piece ? (
        <PieceIcon piece={piece} />
      ) : (
        <svg viewBox="0 0 64 64" aria-hidden="true" fill="none">
          <path
            d={
              profile.avatar === 'owl'
                ? 'M12 10 24 17Q32 13 40 17L52 10V38Q50 55 32 58Q14 55 12 38Z'
                : profile.avatar === 'fox'
                  ? 'M8 7 25 19H39L56 7 51 40 32 57 13 40Z'
                  : 'M10 8 26 19H38L54 8V39Q52 55 32 55Q12 55 10 39Z'
            }
            fill="currentColor"
            opacity=".85"
          />
          <path d="M15 28Q22 20 29 30L32 45 35 30Q42 20 49 28L45 41 32 51 19 41Z" fill="var(--avatar-face)" />
          <circle cx="23" cy="32" r={profile.avatar === 'owl' ? 5 : 3} fill="currentColor" />
          <circle cx="41" cy="32" r={profile.avatar === 'owl' ? 5 : 3} fill="currentColor" />
          <path d="m28 43 4 5 4-5Z" fill="currentColor" />
        </svg>
      )}
    </span>
  );
}

function useProfile(id: string) {
  return useQuery({
    queryKey: ['public-profile', id],
    queryFn: () => api('publicProfile', undefined, { path: { user_id: id } }),
    enabled: !!id,
    retry: false,
  });
}

export function PlayerIdentity({ id }: { id: string }) {
  const query = useProfile(id);
  return (
    <Link className="player-identity" to={`/players/${id}`}>
      <Avatar profile={query.data ?? defaults} />
      <span>{query.data?.display_name ?? 'Người chơi'}</span>
    </Link>
  );
}

export function ProfileCard({ profile }: { profile: ProfileEdit }) {
  return (
    <div className={`profile-card profile-${profile.color}`}>
      <div className="profile-banner">
        <span>OTT v2 · PLAYER</span>
      </div>
      <div className="profile-card-body">
        <Avatar profile={profile} />
        <h2>{profile.display_name || 'Tên của bạn'}</h2>
        <p className="profile-bio">{profile.bio || 'Một bàn cờ, một phong cách riêng.'}</p>
      </div>
    </div>
  );
}

function Statistics({ stats }: { stats: Profile['stats'] }) {
  return (
    <section className="card profile-statistics">
      <h2>Thành tích phòng hai người</h2>
      <p>
        Chỉ tính ván đã kết thúc do server ghi nhận, gồm đầu hàng/rời phòng. Không bao gồm Casual đấu máy hay
        Arena đấu bot.
      </p>
      <div className="profile-totals">
        {[
          ['Số ván', stats.played],
          ['Thắng', stats.wins],
          ['Thua', stats.losses],
          ['Tỷ lệ thắng', stats.played ? `${Math.round((stats.wins * 100) / stats.played)}%` : '—'],
        ].map(([label, value]) => (
          <div key={label}>
            <strong>{value}</strong>
            <span>{label}</span>
          </div>
        ))}
      </div>
      {!stats.played && (
        <p>
          Chưa có ván hoàn thành. <Link to="/rooms">Mời bạn vào chơi</Link>
        </p>
      )}
      <table>
        <thead>
          <tr>
            <th>Bản đồ</th>
            <th>Ván</th>
            <th>Thắng</th>
            <th>Thua</th>
          </tr>
        </thead>
        <tbody>
          {stats.by_map.map((row) => (
            <tr key={row.map}>
              <td>{mapNames[row.map]}</td>
              <td>{row.played}</td>
              <td>{row.wins}</td>
              <td>{row.losses}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <small>
        Các vòng chơi lại cũ đã bị ghi đè trước khi có tính năng này không thể khôi phục vào thống kê.
      </small>
    </section>
  );
}

export function PublicProfile({ user }: { user: User | null }) {
  const { id = '' } = useParams();
  const query = useProfile(id);
  return (
    <section className="profile-page">
      <Heading eyebrow="OTT v2 / NGƯỜI CHƠI" title="Hồ sơ người chơi" />
      <ErrorBox error={query.error} />
      {query.isLoading && <p role="status">Đang tải hồ sơ…</p>}
      {query.data && (
        <>
          <ProfileCard profile={query.data} />
          {user?.id === id && (
            <Link className="primary" to="/profile">
              Chỉnh sửa hồ sơ
            </Link>
          )}
          <Statistics stats={query.data.stats} />
        </>
      )}
    </section>
  );
}

export function EditProfile({ user }: { user: User }) {
  const cache = useQueryClient();
  const query = useQuery({
    queryKey: ['my-profile', user.id],
    queryFn: () => api('myProfile', undefined),
    retry: false,
  });
  const [draft, setDraft] = useState<ProfileEdit>();
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(),
    [saved, setSaved] = useState(false);
  useEffect(() => {
    if (query.data && !draft) {
      const { display_name, bio, avatar, frame, color } = query.data;
      setDraft({ display_name, bio, avatar, frame, color });
    }
  }, [query.data, draft]);
  function change<K extends keyof ProfileEdit>(key: K, value: ProfileEdit[K]) {
    setDraft((old) => old && { ...old, [key]: value });
    setSaved(false);
  }
  const url = new URL(`/players/${user.id}`, window.location.origin).href;
  return (
    <section className="profile-page">
      <Heading
        eyebrow="OTT v2 / HỒ SƠ CỦA BẠN"
        title="Dấu ấn trên bàn cờ"
        description="Tên, giới thiệu, avatar và thống kê bên dưới sẽ được hiển thị công khai. Email đăng nhập không được công khai."
      />
      <ErrorBox error={error ?? query.error} />
      {query.isLoading && <p role="status">Đang tải hồ sơ…</p>}
      {draft && (
        <div className="profile-editor">
          <form
            className="card"
            onSubmit={async (e) => {
              e.preventDefault();
              if (busy) return;
              setBusy(true);
              setError(undefined);
              setSaved(false);
              try {
                const next = await api('updateMyProfile', draft);
                cache.setQueryData(['my-profile', user.id], next);
                cache.setQueryData(['public-profile', user.id], next);
                setDraft({
                  display_name: next.display_name,
                  bio: next.bio,
                  avatar: next.avatar,
                  frame: next.frame,
                  color: next.color,
                });
                setSaved(true);
              } catch (e) {
                setError(e);
              } finally {
                setBusy(false);
              }
            }}
          >
            <fieldset disabled={busy}>
              <legend>Thông tin & diện mạo</legend>
              <label>
                Tên hiển thị
                <input
                  value={draft.display_name}
                  maxLength={40}
                  required
                  pattern=".*\S.*"
                  onChange={(e) => change('display_name', e.target.value)}
                />
              </label>
              <label>
                Giới thiệu ngắn
                <textarea
                  rows={3}
                  maxLength={240}
                  value={draft.bio}
                  onChange={(e) => change('bio', e.target.value)}
                />
                <small>{draft.bio.length}/240 ký tự</small>
              </label>
              <fieldset>
                <legend>Chọn avatar</legend>
                <div className="avatar-options">
                  {Object.entries(avatars).map(([id, label]) => (
                    <button
                      type="button"
                      key={id}
                      aria-pressed={draft.avatar === id}
                      aria-label={`Chọn ${label}`}
                      onClick={() => change('avatar', id as ProfileEdit['avatar'])}
                    >
                      <Avatar profile={{ ...draft, avatar: id as ProfileEdit['avatar'] }} />
                      <span>{label}</span>
                    </button>
                  ))}
                </div>
              </fieldset>
              <label>
                Khung avatar
                <select
                  value={draft.frame}
                  onChange={(e) => change('frame', e.target.value as ProfileEdit['frame'])}
                >
                  {Object.entries(frames).map(([id, label]) => (
                    <option key={id} value={id}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Màu hồ sơ
                <select
                  value={draft.color}
                  onChange={(e) => change('color', e.target.value as ProfileEdit['color'])}
                >
                  {Object.entries(colors).map(([id, label]) => (
                    <option key={id} value={id}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <button className="primary" disabled={busy || !draft.display_name.trim()}>
                {busy ? 'Đang lưu…' : 'Lưu hồ sơ'}
              </button>
            </fieldset>
            {saved && <p role="status">Đã lưu hồ sơ.</p>}
          </form>
          <aside>
            <h2>Xem trước</h2>
            <ProfileCard profile={draft} />
            <Link to={`/players/${user.id}`}>Xem hồ sơ công khai →</Link>
            <label>
              Link hồ sơ
              <input readOnly value={url} onFocus={(e) => e.target.select()} />
            </label>
          </aside>
        </div>
      )}
      <p>
        <Link className="primary" to="/achievements">
          Xem 7 thành tích luyện tập →
        </Link>
      </p>
      {query.data && <Statistics stats={query.data.stats} />}
    </section>
  );
}
