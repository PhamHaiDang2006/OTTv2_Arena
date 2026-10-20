import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import Markdown from 'react-markdown';
import { ReplayViewer } from '@ottv2/replay-viewer';
import type { Language, Match, Replay, User } from '../../contracts/generated/types';
import { api } from './api';
import { validate } from '../shared/schema';
import { uploadFetch } from './upload';
import { Countdown } from './countdown';
import { adminUrl } from './urls';
import { Badge, date, ErrorBox, Field, Heading, Load, MutationForm, Pager, Table, text, useApi } from './ui';
export function Home({ user }: { user: User }) {
  const team = useApi('myTeam', {}, !!user.team_id),
    matches = useApi('listScrimmages', { query: { page_size: 5 } }, !!user.team_id);
  const announcements = useApi('listAnnouncements', { query: { page_size: 5 } });
  return (
    <>
      <Heading
        title="Sẵn sàng cho ván tiếp theo?"
        description="Nộp bot, thử chiến thuật và học từ từng nước đi."
      >
        <Link className="button primary" to="/submit">
          + Nộp bot mới
        </Link>
      </Heading>
      <div className="hero">
        <div>
          <span className="eyebrow">KHÔNG GIAN ĐỘI</span>
          {user.team_id ? (
            <Load query={team}>
              {(data) => (
                <>
                  <h2>{data.name}</h2>
                  <Badge value={data.status} />
                  <p>
                    {data.members.length} thành viên ·{' '}
                    {data.is_locked ? 'Đội đang bị khóa' : 'Đội đang hoạt động'}
                  </p>
                  <div className="stats">
                    {(['scrimmage', 'tournament'] as const).map((scope) => (
                      <div key={scope}>
                        <span>{scope === 'scrimmage' ? 'Bot đánh tập' : 'Bot thi đấu'}</span>
                        <strong>
                          {data.active_bots.find((bot) => bot.scope === scope)?.submission_id.slice(0, 8) ||
                            'Chưa chọn'}
                        </strong>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </Load>
          ) : (
            <p>
              Tài khoản quản trị chưa thuộc đội nào. <a href={adminUrl}>Mở quản trị</a>
            </p>
          )}
        </div>
        <div className="hero-art" aria-hidden="true">
          ●<br />■ ▲
        </div>
      </div>
      <div className="two-col">
        <section className="card">
          <h2>Trận đánh tập gần đây</h2>
          {user.team_id && <Load query={matches}>{(data) => <MatchList matches={data.items} />}</Load>}
          <Link to="/scrimmage">Đến phòng đánh tập →</Link>
        </section>
        <section className="card">
          <h2>Thông báo</h2>
          <Load query={announcements}>
            {(data) =>
              data.items.length ? (
                data.items.map((item) => (
                  <article key={item.id}>
                    <small>{date(item.published_at)}</small>
                    <h3>{item.title}</h3>
                    <Markdown>{item.body}</Markdown>
                  </article>
                ))
              ) : (
                <p>Chưa có thông báo mới.</p>
              )
            }
          </Load>
        </section>
      </div>
      <UpcomingRounds />
      {user.role === 'captain' && (
        <section className="card">
          <h2>Đổi tên đội</h2>
          <MutationForm op="updateMyTeam" title="Lưu tên đội" body={(f) => ({ name: text(f, 'name') })}>
            <Field label="Tên đội">
              <input name="name" required maxLength={120} />
            </Field>
          </MutationForm>
        </section>
      )}
    </>
  );
}
export function Upload() {
  const caps = useApi('capabilities');
  const [file, setFile] = useState<File | null>(null),
    [accepted, setAccepted] = useState<string>(),
    [error, setError] = useState(''),
    [progress, setProgress] = useState<number>();
  const choose = (candidate?: File) => {
    setAccepted(undefined);
    if (
      !candidate ||
      !candidate.name.toLowerCase().endsWith('.zip') ||
      candidate.size > (caps.data?.max_upload_bytes ?? 1048576)
    ) {
      setFile(null);
      setError('Chọn tệp .zip không quá 1 MiB.');
      return;
    }
    setError('');
    setFile(candidate);
  };
  return (
    <>
      <Heading
        title="Nộp bot"
        description="Một chiến thuật mới bắt đầu từ đây. ZIP tối đa 1 MiB, 50 tệp; dung lượng giải nén tối đa 5 MiB."
      />
      <section className="card">
        <Load query={caps}>
          {(data) => (
            <MutationForm
              op="createSubmission"
              title="Tải lên và build"
              fetchImpl={uploadFetch(setProgress)}
              disabled={!file}
              body={(f) => {
                const body = new FormData();
                body.set('file', file!);
                body.set('language', text(f, 'language'));
                return body;
              }}
              onSuccess={(result) => setAccepted(result.id)}
            >
              <div
                className="dropzone"
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  choose(e.dataTransfer.files[0]);
                }}
              >
                <strong>Kéo ZIP vào đây</strong>
                <p>hoặc chọn tệp từ máy tính</p>
                <input
                  aria-label="Tệp bot ZIP"
                  type="file"
                  accept=".zip,application/zip"
                  onChange={(e) => choose(e.target.files?.[0])}
                />
                {file && (
                  <p>
                    {file.name} · {(file.size / 1024).toFixed(1)} KiB
                  </p>
                )}
              </div>
              {error && (
                <p role="alert" className="error">
                  {error}
                </p>
              )}
              {progress !== undefined && (
                <p>
                  <progress aria-label="Tiến trình tải lên" value={progress} max={100} />
                  {progress}% {progress === 100 && !accepted ? '· Đang chờ máy chủ tiếp nhận' : ''}
                </p>
              )}
              <Field label="Ngôn ngữ">
                <select name="language">
                  {data.languages.map((language) => (
                    <option key={language}>{language}</option>
                  ))}
                </select>
              </Field>
            </MutationForm>
          )}
        </Load>
      </section>
      {accepted && (
        <section className="card">
          <h2>Build {accepted.slice(0, 8)}</h2>
          <BuildLog id={accepted} />
          <Link to="/submissions">Mở lịch sử nộp →</Link>
        </section>
      )}
    </>
  );
}
export function BuildLog({ id, admin = false }: { id: string; admin?: boolean }) {
  const query = useApi(admin ? 'adminBuildLog' : 'getBuildLog', { path: { id } }, true, 5000);
  return (
    <Load query={query}>
      {(data) => (
        <>
          <Badge value={data.status} />
          {data.status === 'failed' && (
            <p className="error">
              {data.text
                .split('\n')
                .filter((line) => /error|failed|exception/i.test(line))
                .slice(-3)
                .join('\n') || 'Build thất bại. Xem log bên dưới.'}
            </p>
          )}
          <pre>{data.text || 'Đang chờ nhật ký build…'}</pre>
          {data.truncated && <p>Nhật ký đã được cắt bớt.</p>}
        </>
      )}
    </Load>
  );
}
export function Submissions({ user, admin = false }: { user: User; admin?: boolean }) {
  const [page, setPage] = useState(1),
    [status, setStatus] = useState(''),
    [team, setTeam] = useState(''),
    [language, setLanguage] = useState('');
  const [selected, setSelected] = useState<string>();
  const query = useApi(
    admin ? 'adminListSubmissions' : 'listSubmissions',
    {
      query: {
        page,
        status: status || undefined,
        ...(admin ? { team_id: team || undefined, language: language || undefined } : {}),
      },
    },
    true,
    10000,
  );
  return (
    <>
      <Heading
        title="Lịch sử bản nộp"
        description="Theo dõi build và chọn phiên bản sẵn sàng cho trận tiếp theo."
      />
      <div className="filters">
        <Field label="Trạng thái">
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
            }}
          >
            <option value="">Tất cả</option>
            {['queued', 'building', 'ready', 'failed'].map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </Field>
        {admin && (
          <>
            <Field label="ID đội">
              <input
                value={team}
                onChange={(e) => {
                  setTeam(e.target.value);
                  setPage(1);
                }}
              />
            </Field>
            <Field label="Ngôn ngữ">
              <select
                value={language}
                onChange={(e) => {
                  setLanguage(e.target.value);
                  setPage(1);
                }}
              >
                <option value="">Tất cả</option>
                {['python', 'cpp', 'java', 'node'].map((l) => (
                  <option key={l}>{l}</option>
                ))}
              </select>
            </Field>
          </>
        )}
      </div>
      <Load query={query}>
        {(data) => (
          <>
            <Table
              rows={data.items}
              columns={[
                {
                  title: 'Phiên bản',
                  render: (row) => (
                    <>
                      <code>{row.id.slice(0, 8)}</code>
                      <small>{date(row.submitted_at)}</small>
                    </>
                  ),
                },
                { title: 'Ngôn ngữ', render: (row) => row.language },
                {
                  title: 'Trạng thái',
                  render: (row) => (
                    <>
                      <Badge value={row.status} />
                      {row.build_error && <p>{row.build_error.message}</p>}
                    </>
                  ),
                },
                {
                  title: 'Thao tác',
                  render: (row) => (
                    <div className="row-actions">
                      <button onClick={() => setSelected(row.id)}>Xem build</button>
                      <Link to={`/submissions/${row.id}`}>Mã nguồn</Link>
                      {!admin && user.role === 'captain' && row.status === 'ready' && (
                        <MutationForm
                          op="setActiveBot"
                          title="Chọn bot"
                          body={(f) => ({
                            submission_id: row.id,
                            scope: text(f, 'scope') as 'scrimmage' | 'tournament',
                          })}
                        >
                          <select name="scope" aria-label="Phạm vi bot">
                            <option value="scrimmage">Đánh tập</option>
                            <option value="tournament">Thi đấu</option>
                          </select>
                        </MutationForm>
                      )}
                    </div>
                  ),
                },
              ]}
            />
            <Pager page={page} total={data.total} setPage={setPage} />
          </>
        )}
      </Load>
      {selected && (
        <section className="card">
          <h2>Nhật ký build</h2>
          <BuildLog id={selected} admin={admin} />
        </section>
      )}
    </>
  );
}
export function MatchList({ matches }: { matches: Match[] }) {
  return (
    <Table
      rows={matches}
      columns={[
        {
          title: 'Trận đấu',
          render: (row) => (
            <Link to={`/matches/${row.id}`}>
              {row.team_a.name} <span className="muted">vs</span> {row.team_b.name}
            </Link>
          ),
        },
        { title: 'Tỉ số', render: (row) => `${row.score_a} : ${row.score_b}` },
        { title: 'Trạng thái', render: (row) => <Badge value={row.status} /> },
      ]}
    />
  );
}
export function Scrimmage() {
  const [page, setPage] = useState(1),
    [opponentPage, setOpponentPage] = useState(1);
  const opponents = useApi('listOpponents', { query: { page: opponentPage } }),
    quota = useApi('scrimmageQuota'),
    matches = useApi('listScrimmages', { query: { page } }, true, 10000);
  return (
    <>
      <Heading title="Phòng đánh tập" description="Mỗi trận gồm hai ván đổi màu. Kết quả do máy chủ tính." />
      <div className="two-col">
        <section className="card">
          <h2>Chọn đối thủ</h2>
          <Load query={quota}>
            {(q) => (
              <p>
                Còn{' '}
                <strong>
                  {q.remaining}/{q.limit}
                </strong>{' '}
                trận · Đặt lại {date(q.resets_at)}
              </p>
            )}
          </Load>
          <Load query={opponents}>
            {(data) => (
              <>
                <MutationForm
                  title="Bắt đầu đánh tập"
                  op="createScrimmage"
                  disabled={!data.items.length || !quota.data?.remaining}
                  body={(f) => ({ opponent_team_id: text(f, 'opponent') })}
                >
                  <Field label="Đội đối thủ">
                    <select name="opponent" required>
                      {data.items.map((team) => (
                        <option value={team.id} key={team.id}>
                          {team.name}
                        </option>
                      ))}
                    </select>
                  </Field>
                </MutationForm>
                <Pager page={opponentPage} total={data.total} setPage={setOpponentPage} />
              </>
            )}
          </Load>
        </section>
        <section className="card">
          <h2>Trước khi bắt đầu</h2>
          <p>
            Đội trưởng cần chọn bot đánh tập đã build thành công. Hai bot được chụp lại tại thời điểm tạo
            trận.
          </p>
          <Link to="/submissions">Chọn bot trong lịch sử →</Link>
        </section>
      </div>
      <section className="card">
        <h2>Các trận đã tạo</h2>
        <Load query={matches}>
          {(data) => (
            <>
              <MatchList matches={data.items} />
              <Pager page={page} total={data.total} setPage={setPage} />
            </>
          )}
        </Load>
      </section>
    </>
  );
}
export function MatchDetail() {
  const { id = '' } = useParams();
  const query = useApi('getMatch', { path: { id } }, true, 10000);
  return (
    <>
      <Heading title="Chi tiết trận" />
      <Load query={query}>
        {(match) => (
          <section className="card">
            <h2>
              {match.team_a.name} {match.score_a} : {match.score_b} {match.team_b.name}
            </h2>
            <Badge value={match.status} />
            <Table
              rows={match.games}
              columns={[
                {
                  title: 'Ván / lần chạy',
                  render: (g) =>
                    `${g.game_index} / ${g.attempt}${g.is_current ? ' · Hiện hành' : ' · Lịch sử'}`,
                },
                { title: 'Trạng thái', render: (g) => <Badge value={g.status} /> },
                {
                  title: 'Kết quả',
                  render: (g) => (g.result ? `${g.result.winner} · ${g.result.reason}` : 'Chưa có'),
                },
                {
                  title: 'Replay',
                  render: (g) =>
                    g.replay_available ? <Link to={`/games/${g.id}`}>Xem replay →</Link> : 'Chưa sẵn sàng',
                },
              ]}
            />
          </section>
        )}
      </Load>
    </>
  );
}
export function GamePage({ admin = false }: { admin?: boolean }) {
  const { id = '' } = useParams();
  const game = useApi('getGame', { path: { id } }, true, 10000);
  const logs = useApi('adminGameLogs', { path: { id } }, admin);
  const replay = useQuery({
    queryKey: ['replay', id],
    enabled: !!game.data?.replay_available,
    retry: false,
    queryFn: async ({ signal }) => {
      for (let attempt = 0; attempt < 2; attempt++) {
        const signed = await api('getReplayUrl', undefined, { path: { id }, signal });
        const response = await fetch(signed.url, { signal, credentials: 'omit' });
        if ([401, 403].includes(response.status) && attempt === 0) continue;
        if (!response.ok) throw new Error('Không tải được replay. Hãy tải lại để nhận URL mới.');
        return validate<Replay>('Replay', await response.json());
      }
      throw new Error('URL replay đã hết hạn. Hãy tải lại.');
    },
  });
  return (
    <>
      <Heading title="Phân tích ván đấu" description="Tua từng nước, kiểm tra đồng hồ và debug của bot." />
      <Load query={game}>
        {(g) =>
          g.replay_available ? (
            <section className="card">
              <Load query={replay}>
                {(data) => (
                  <ReplayViewer
                    replay={data}
                    mode={admin ? 'admin' : 'participant'}
                    stderr={admin ? logs.data : undefined}
                    onDownload={() => {
                      const url = URL.createObjectURL(
                        new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }),
                      );
                      const a = document.createElement('a');
                      a.href = url;
                      a.download = `replay-${id}.json`;
                      a.click();
                      setTimeout(() => URL.revokeObjectURL(url), 1000);
                    }}
                  />
                )}
              </Load>
              {admin && <ErrorBox error={logs.error} />}
            </section>
          ) : (
            <section className="card">
              <p>
                Replay chưa sẵn sàng. <Badge value={g.status} />
              </p>
              {admin && (
                <Load query={logs}>
                  {(data) => (
                    <>
                      <h3>stderr Xanh</h3>
                      <pre>{data.BLUE || 'Chưa có log.'}</pre>
                      <h3>stderr Đỏ</h3>
                      <pre>{data.RED || 'Chưa có log.'}</pre>
                    </>
                  )}
                </Load>
              )}
            </section>
          )
        }
      </Load>
      {admin && (logs.data?.blue_truncated || logs.data?.red_truncated) && (
        <p>stderr đã được máy chủ cắt bớt.</p>
      )}
    </>
  );
}
export function TournamentSelect({
  value,
  onChange,
  admin = false,
}: {
  value: string;
  onChange: (id: string) => void;
  admin?: boolean;
}) {
  const [page, setPage] = useState(1);
  const query = useApi(admin ? 'adminListTournaments' : 'listTournaments', { query: { page } });
  return (
    <Load query={query}>
      {(data) => (
        <div className="filters">
          <Field label="Giải đấu">
            <select value={value} onChange={(e) => onChange(e.target.value)}>
              <option value="">Chọn giải đấu</option>
              {data.items.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} · {t.status}
                </option>
              ))}
            </select>
          </Field>
          <Pager page={page} total={data.total} setPage={setPage} />
        </div>
      )}
    </Load>
  );
}
export function Standings({ bracket = false }: { bracket?: boolean }) {
  const [id, setId] = useState(''),
    [page, setPage] = useState(1);
  const standings = useApi('getStandings', { query: { tournament_id: id, page } }, !!id && !bracket);
  const slots = useApi('getBracket', { query: { tournament_id: id, page } }, !!id && bracket);
  return (
    <>
      <Heading
        title={bracket ? 'Nhánh đấu' : 'Bảng xếp hạng'}
        description="Điểm và thứ hạng được cập nhật từ máy chủ."
      />
      <TournamentSelect
        value={id}
        onChange={(v) => {
          setId(v);
          setPage(1);
        }}
      />
      {id &&
        (bracket ? (
          <Load query={slots}>
            {(data) => (
              <>
                <div className="bracket">
                  {['quarterfinal', 'semifinal', 'third_place', 'final'].map((round) => (
                    <section className="card" key={round}>
                      <h2>{round}</h2>
                      {data.items
                        .filter((s) => s.round === round)
                        .map((s) => (
                          <article key={`${s.round}-${s.slot_index}`}>
                            <strong>{s.team?.name ?? 'Chưa xác định'}</strong>
                            <p>{s.source_rule}</p>
                            {s.match_id && <Link to={`/matches/${s.match_id}`}>Xem trận</Link>}
                          </article>
                        ))}
                    </section>
                  ))}
                </div>
                <Pager page={page} total={data.total} setPage={setPage} />
              </>
            )}
          </Load>
        ) : (
          <Load query={standings}>
            {(data) => (
              <>
                <Table
                  rows={data.items}
                  columns={[
                    { title: 'Bảng', render: (r) => r.group_id.slice(0, 8) },
                    { title: 'Hạng', render: (r) => r.rank },
                    { title: 'Đội', render: (r) => r.team.name },
                    { title: 'Trận', render: (r) => r.played },
                    { title: 'T / H / B', render: (r) => `${r.won} / ${r.drawn} / ${r.lost}` },
                    { title: 'Điểm', render: (r) => <strong>{r.points}</strong> },
                    { title: 'Hiệu số', render: (r) => r.game_diff },
                  ]}
                />
                <Pager page={page} total={data.total} setPage={setPage} />
              </>
            )}
          </Load>
        ))}
    </>
  );
}
export function Docs() {
  const query = useApi('getDocs');
  return (
    <>
      <Heading
        title="Tài liệu & bộ khởi động"
        description="Luật dev-v1 đang dùng để phát triển, chưa phải luật giải chính thức."
      />
      <Load query={query}>
        {(data) => (
          <>
            <section className="card">
              <h2>Starter kits</h2>
              {data.starter_kits.map((kit) => (
                <p key={kit.language}>
                  <a href={kit.url}>
                    {kit.language} · engine {kit.engine_version} ↓
                  </a>
                  <small>SHA-256: {kit.sha256}</small>
                </p>
              ))}
            </section>
            <section className="card prose">
              <Markdown>{data.rules_markdown}</Markdown>
              <Markdown>{data.protocol_markdown}</Markdown>
            </section>
          </>
        )}
      </Load>
    </>
  );
}
function UpcomingRounds() {
  const [id, setId] = useState(''),
    [page, setPage] = useState(1);
  const rounds = useApi('listRounds', { path: { id }, query: { page } }, !!id, 10000);
  const matches = useApi(
    'listMatches',
    { query: { tournament_id: id, status: 'queued', page_size: 5 } },
    !!id,
    10000,
  );
  return (
    <section className="card">
      <h2>Lịch thi đấu</h2>
      <TournamentSelect
        value={id}
        onChange={(value) => {
          setId(value);
          setPage(1);
        }}
      />
      {id && (
        <>
          <Load query={rounds}>
            {(data) => (
              <>
                {data.items.map((round) => (
                  <p key={round.id}>
                    {round.stage} · <Badge value={round.status} />{' '}
                    {round.status === 'draft' && round.freeze_at && <Countdown until={round.freeze_at} />}
                  </p>
                ))}
                <Pager page={page} total={data.total} setPage={setPage} />
              </>
            )}
          </Load>
          <Load query={matches}>{(data) => <MatchList matches={data.items} />}</Load>
        </>
      )}
    </section>
  );
}
