import { useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import Markdown from 'react-markdown';
import type { AdminTeamPatch, RoundCreate } from '../../contracts/generated/types';
import { Badge, date, Field, Heading, Load, MutationForm, Pager, Reason, Table, text, useApi } from './ui';
import { BuildLog, TournamentSelect, scrimmagePause } from './participant';
import { SourceCode } from './source-code';
export function Teams() {
  const [page, setPage] = useState(1),
    [selected, setSelected] = useState(''),
    [importErrors, setImportErrors] = useState<string[]>([]);
  const query = useApi('adminListTeams', { query: { page } });
  return (
    <>
      <Heading title="Quản lý đội" description="Duyệt đội, xếp hạt giống và chuẩn bị danh sách thi đấu." />
      <Load query={query}>
        {(data) => (
          <>
            <Table
              rows={data.items}
              columns={[
                {
                  title: 'Đội',
                  render: (r) => (
                    <>
                      <strong>{r.name}</strong>
                      <small>{r.id}</small>
                    </>
                  ),
                },
                { title: 'Trạng thái', render: (r) => <Badge value={r.status} /> },
                { title: 'Khóa', render: (r) => (r.is_locked ? 'Có' : 'Không') },
                { title: 'Hạt giống', render: (r) => r.seed ?? 'Chưa đặt' },
                {
                  title: 'Thao tác',
                  render: (r) => <button onClick={() => setSelected(r.id)}>Cập nhật</button>,
                },
              ]}
            />
            <Pager page={page} total={data.total} setPage={setPage} />
            {selected && (
              <section className="card" key={selected}>
                <h2>Cập nhật đội {data.items.find((t) => t.id === selected)?.name}</h2>
                <MutationForm
                  title="Lưu thay đổi đội"
                  op="adminUpdateTeam"
                  path={{ id: selected }}
                  confirm
                  body={(f) => {
                    const result: AdminTeamPatch = { reason: text(f, 'reason') };
                    if (text(f, 'name')) result.name = text(f, 'name');
                    if (text(f, 'status')) result.status = text(f, 'status') as AdminTeamPatch['status'];
                    if (text(f, 'locked')) result.is_locked = text(f, 'locked') === 'true';
                    if (text(f, 'seed')) result.seed = Number(text(f, 'seed'));
                    return result;
                  }}
                >
                  <Field label="Tên mới (để trống nếu giữ nguyên)">
                    <input name="name" />
                  </Field>
                  <Field label="Trạng thái">
                    <select name="status">
                      <option value="">Giữ nguyên</option>
                      <option value="approved">Duyệt</option>
                      <option value="pending">Chờ duyệt</option>
                      <option value="disqualified">Loại đội</option>
                    </select>
                  </Field>
                  <Field label="Khóa đội">
                    <select name="locked">
                      <option value="">Giữ nguyên</option>
                      <option value="true">Khóa</option>
                      <option value="false">Mở khóa</option>
                    </select>
                  </Field>
                  <Field label="Hạt giống mới">
                    <input name="seed" type="number" min="1" />
                  </Field>
                  <Reason />
                </MutationForm>
              </section>
            )}
          </>
        )}
      </Load>
      <div className="two-col">
        <section className="card">
          <h2>Tạo đội</h2>
          <MutationForm
            title="Tạo đội"
            op="adminCreateTeam"
            confirm
            body={(f) => ({
              name: text(f, 'name'),
              slug: text(f, 'slug'),
              captain_email: text(f, 'email'),
              seed: text(f, 'seed') ? Number(text(f, 'seed')) : null,
            })}
          >
            <Field label="Tên đội">
              <input name="name" required />
            </Field>
            <Field label="Slug">
              <input name="slug" required pattern="[a-z0-9-]+" />
            </Field>
            <Field label="Email đội trưởng">
              <input name="email" type="email" required />
            </Field>
            <Field label="Hạt giống">
              <input name="seed" type="number" min="1" />
            </Field>
          </MutationForm>
        </section>
        <section className="card">
          <h2>Nhập đội từ CSV</h2>
          <p>Kiểm tra toàn bộ tệp trước khi nhập. Nếu có lỗi, không đội nào được tạo.</p>
          <MutationForm
            title="Nhập CSV"
            op="adminImportTeams"
            confirm
            body={(f) => ({ csv: text(f, 'csv') })}
            onSuccess={(r) => setImportErrors(r.errors.map((e) => `Dòng ${e.row}: ${e.message}`))}
          >
            <Field label="Nội dung CSV">
              <textarea name="csv" required rows={8} placeholder="name,slug,captain_email,seed" />
            </Field>
          </MutationForm>
          {importErrors.length > 0 && (
            <div role="alert" className="error">
              <strong>Chưa nhập đội vì CSV có lỗi:</strong>
              {importErrors.map((e, i) => (
                <p key={i}>{e}</p>
              ))}
            </div>
          )}
        </section>
      </div>
    </>
  );
}
export function DrawPage() {
  const [id, setId] = useState('');
  const draw = useApi('adminGetDraw', { path: { id } }, !!id),
    caps = useApi('capabilities');
  const teams = useApi('adminListTeams', { query: { page_size: 100 } });
  return (
    <>
      <Heading
        title="Giải đấu & bốc thăm"
        description="Tạo giải, bốc thăm các bảng rồi chốt trước khi tạo vòng đấu."
      />
      <section className="card">
        <h2>Tạo giải mới</h2>
        <MutationForm
          op="adminCreateTournament"
          title="Tạo giải"
          confirm
          disabled={!caps.data?.tournament_enabled}
          body={(f) => ({ name: text(f, 'name'), engine_version: text(f, 'engine'), ruleset_id: 'dev-v1' })}
          onSuccess={(t) => setId(t.id)}
        >
          <Field label="Tên giải">
            <input name="name" required />
          </Field>
          <Field label="Phiên bản engine">
            <input name="engine" defaultValue="1.0.0" required />
          </Field>
        </MutationForm>
        {!caps.data?.tournament_enabled && <p>Máy chủ chưa bật giải đấu cho luật phát triển dev-v1.</p>}
      </section>
      <TournamentSelect admin value={id} onChange={setId} />
      {id && (
        <section className="card">
          <h2>Kết quả bốc thăm</h2>
          <Load query={draw}>
            {(data) => (
              <>
                <p>
                  Seed: {data.draw_seed} · {data.locked ? 'Đã chốt' : 'Chưa chốt'}
                </p>
                <div className="two-col">
                  {data.groups.map((group) => (
                    <article key={group.id}>
                      <h3>Bảng {group.label}</h3>
                      {group.team_ids.map((team) => (
                        <p key={team}>{teams.data?.items.find((t) => t.id === team)?.name ?? team}</p>
                      ))}
                    </article>
                  ))}
                </div>
              </>
            )}
          </Load>
          <MutationForm
            op="adminDraw"
            path={{ id }}
            title="Bốc thăm / bốc lại"
            confirm
            disabled={draw.data?.locked}
            body={(f) => ({ reason: text(f, 'reason') })}
          >
            <Reason />
          </MutationForm>
          <MutationForm
            op="adminLockDraw"
            path={{ id }}
            title="Chốt bốc thăm"
            confirm
            disabled={!draw.data || draw.data.locked}
            body={(f) => ({ reason: text(f, 'reason') })}
          >
            <Reason />
          </MutationForm>
        </section>
      )}
    </>
  );
}
export function Rounds() {
  const [id, setId] = useState(''),
    [page, setPage] = useState(1),
    [selected, setSelected] = useState('');
  const query = useApi('adminListRounds', { path: { id }, query: { page } }, !!id, 10000);
  const snapshot = useApi('adminGetSnapshot', { path: { id: selected } }, !!selected);
  return (
    <>
      <Heading
        title="Điều hành vòng đấu"
        description="Đóng băng bot trước khi chạy. Mọi thay đổi đều được ghi vào nhật ký."
      />
      <TournamentSelect
        admin
        value={id}
        onChange={(v) => {
          setId(v);
          setPage(1);
          setSelected('');
        }}
      />
      {id && (
        <>
          <section className="card">
            <h2>Tạo vòng</h2>
            <MutationForm
              op="adminCreateRound"
              path={{ id }}
              title="Tạo vòng đấu"
              confirm
              body={(f) => ({
                stage: text(f, 'stage') as RoundCreate['stage'],
                freeze_at: text(f, 'freeze') ? new Date(text(f, 'freeze')).toISOString() : null,
              })}
            >
              <Field label="Giai đoạn">
                <select name="stage">
                  {['group', 'quarterfinal', 'semifinal', 'third_place', 'final'].map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </Field>
              <Field label="Thời gian đóng băng (giờ máy của bạn)">
                <input name="freeze" type="datetime-local" />
              </Field>
            </MutationForm>
          </section>
          <Load query={query}>
            {(data) => (
              <>
                <Table
                  rows={data.items}
                  columns={[
                    {
                      title: 'Vòng',
                      render: (r) => (
                        <>
                          <strong>{r.stage}</strong>
                          <small>{r.id}</small>
                        </>
                      ),
                    },
                    { title: 'Trạng thái', render: (r) => <Badge value={r.status} /> },
                    { title: 'Tiến độ', render: (r) => `${r.matches_finished}/${r.matches_total}` },
                    { title: 'Đóng băng', render: (r) => date(r.freeze_at) },
                    {
                      title: 'Điều hành',
                      render: (r) => (
                        <details>
                          <summary>Thao tác</summary>
                          <MutationForm
                            op="adminUpdateRound"
                            path={{ id: r.id }}
                            title="Đặt giờ đóng băng"
                            confirm
                            disabled={r.status !== 'draft'}
                            body={(f) => ({
                              freeze_at: text(f, 'freeze') ? new Date(text(f, 'freeze')).toISOString() : null,
                              reason: text(f, 'reason'),
                            })}
                          >
                            <Field label="Thời gian">
                              <input name="freeze" type="datetime-local" />
                            </Field>
                            <Reason />
                          </MutationForm>
                          <MutationForm
                            op="adminFreezeRound"
                            path={{ id: r.id }}
                            title="Đóng băng ngay"
                            confirm
                            disabled={r.status !== 'draft'}
                            body={(f) => ({ reason: text(f, 'reason') })}
                          >
                            <Reason />
                          </MutationForm>
                          <MutationForm
                            op="adminRunRound"
                            path={{ id: r.id }}
                            title="Chạy vòng"
                            confirm
                            disabled={r.status !== 'frozen'}
                            body={(f) => ({ reason: text(f, 'reason') })}
                          >
                            <Reason />
                          </MutationForm>
                          {r.snapshot_id && (
                            <button onClick={() => setSelected(r.id)}>Xem snapshot bot</button>
                          )}
                        </details>
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
              <h2>Snapshot bất biến</h2>
              <Load query={snapshot}>
                {(data) => (
                  <Table
                    rows={data.bots}
                    columns={[
                      { title: 'Đội', render: (r) => r.team_id },
                      { title: 'Bản nộp', render: (r) => r.submission_id },
                    ]}
                  />
                )}
              </Load>
            </section>
          )}
        </>
      )}
    </>
  );
}
export function AdminMatches() {
  const [page, setPage] = useState(1),
    [round, setRound] = useState(''),
    [status, setStatus] = useState('');
  const query = useApi(
    'adminListMatches',
    { query: { page, round_id: round || undefined, status: status || undefined } },
    true,
    10000,
  );
  return (
    <>
      <Heading
        title="Quản lý trận đấu"
        description="Giữ nguyên lịch sử attempt. Backend kiểm tra các khóa vòng sau trước khi thay đổi."
      />
      <div className="filters">
        <Field label="ID vòng">
          <input
            value={round}
            onChange={(e) => {
              setRound(e.target.value);
              setPage(1);
            }}
          />
        </Field>
        <Field label="Trạng thái">
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
            }}
          >
            <option value="">Tất cả</option>
            {['queued', 'running', 'finished', 'blocked'].map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </Field>
      </div>
      <Load query={query}>
        {(data) => (
          <>
            {data.items.map((match) => (
              <section className="card" key={match.id}>
                <h2>
                  <Link to={`/matches/${match.id}`}>
                    {match.team_a.name} {match.score_a} : {match.score_b} {match.team_b.name}
                  </Link>
                </h2>
                <Badge value={match.status} />
                <Table
                  rows={match.games}
                  columns={[
                    {
                      title: 'Ván / attempt',
                      render: (g) =>
                        `${g.game_index} / ${g.attempt} · ${g.is_current ? 'Hiện hành' : 'Lịch sử'}`,
                    },
                    { title: 'Trạng thái', render: (g) => <Badge value={g.status} /> },
                    { title: 'Nhật ký', render: (g) => <Link to={`/games/${g.id}`}>Replay & stderr</Link> },
                    {
                      title: 'Chạy lại',
                      render: (g) => (
                        <MutationForm
                          op="adminRerunGame"
                          path={{ id: g.id }}
                          title="Tạo attempt mới"
                          confirm
                          disabled={!g.is_current || g.status === 'running' || g.status === 'queued'}
                          body={(f) => ({ reason: text(f, 'reason') })}
                        >
                          <Reason />
                        </MutationForm>
                      ),
                    },
                  ]}
                />
                <details>
                  <summary>Sửa kết quả trận</summary>
                  <MutationForm
                    op="adminOverrideMatch"
                    path={{ id: match.id }}
                    title="Sửa kết quả"
                    confirm
                    body={(f) => ({
                      winner_team_id: text(f, 'winner') || null,
                      score_a: Number(text(f, 'a')),
                      score_b: Number(text(f, 'b')),
                      reason: text(f, 'reason'),
                    })}
                  >
                    <Field label="Đội thắng">
                      <select name="winner">
                        <option value="">Hòa</option>
                        <option value={match.team_a.id}>{match.team_a.name}</option>
                        <option value={match.team_b.id}>{match.team_b.name}</option>
                      </select>
                    </Field>
                    <Field label={`Điểm ${match.team_a.name}`}>
                      <input name="a" required min="0" type="number" defaultValue={match.score_a} />
                    </Field>
                    <Field label={`Điểm ${match.team_b.name}`}>
                      <input name="b" required min="0" type="number" defaultValue={match.score_b} />
                    </Field>
                    <Reason />
                  </MutationForm>
                </details>
              </section>
            ))}
            {!data.items.length && <p>Chưa có trận đấu.</p>}
            <Pager page={page} total={data.total} setPage={setPage} />
          </>
        )}
      </Load>
    </>
  );
}
export function QueuePage() {
  const query = useApi('adminQueue', {}, true, 5000);
  return (
    <>
      <Heading title="Hàng đợi & worker" description="Tự cập nhật mỗi 5 giây khi trang hoạt động." />
      <Load query={query}>
        {(data) => (
          <>
            <section className="card">
              <h2>Nhận trận đánh tập mới</h2>
              <p role="status">
                {data.scrimmage_admission.paused_reason
                  ? `Đang tạm dừng: ${scrimmagePause[data.scrimmage_admission.paused_reason]} Trận đã nhận vẫn chạy trên worker đánh tập.`
                  : 'Đang nhận. Worker giải chỉ lấy việc ở match:tournament.'}
              </p>
            </section>
            <div className="queue-grid">
              {data.queues.map((queue) => (
                <section className="card" key={queue.name}>
                  <h2>{queue.name}</h2>
                  <p>{queue.paused ? 'Đang tạm dừng' : 'Đang nhận việc'}</p>
                  <div className="stats">
                    <div>
                      <span>Chờ</span>
                      <strong>{queue.queued}</strong>
                    </div>
                    <div>
                      <span>Chạy</span>
                      <strong>{queue.running}</strong>
                    </div>
                    <div>
                      <span>Lỗi</span>
                      <strong>{queue.failed}</strong>
                    </div>
                  </div>
                  <MutationForm
                    op="adminControlQueue"
                    title={queue.paused ? 'Tiếp tục hàng đợi' : 'Tạm dừng hàng đợi'}
                    confirm
                    body={(f) => ({ name: queue.name, paused: !queue.paused, reason: text(f, 'reason') })}
                  >
                    <Reason />
                  </MutationForm>
                </section>
              ))}
            </div>
            <section className="card">
              <h2>Worker</h2>
              <Table
                rows={data.workers}
                columns={[
                  { title: 'ID', render: (r) => r.id },
                  { title: 'Loại', render: (r) => r.kind },
                  { title: 'Trạng thái', render: (r) => r.status },
                  { title: 'Heartbeat cuối', render: (r) => date(r.last_seen_at) },
                  { title: 'Job', render: (r) => r.job_id ?? 'Không có' },
                ]}
              />
            </section>
          </>
        )}
      </Load>
    </>
  );
}
function SourcePane({ id, admin }: { id: string; admin: boolean }) {
  const [path, setPath] = useState('');
  const tree = useApi(admin ? 'adminGetSource' : 'getOwnSource', { path: { id } });
  const file = useApi(
    admin ? 'adminGetSourceFile' : 'getOwnSourceFile',
    { path: { id }, query: { path } },
    !!path,
  );
  return (
    <section className="card source">
      <h3>Bản nộp {id.slice(0, 8)}</h3>
      <Load query={tree}>
        {(data) => (
          <Field label="Tệp nguồn">
            <select value={path} onChange={(e) => setPath(e.target.value)}>
              <option value="">Chọn tệp</option>
              {data.files.map((f) => (
                <option key={f.path}>{f.path}</option>
              ))}
            </select>
          </Field>
        )}
      </Load>
      {path && (
        <Load query={file}>
          {(data) => (
            <>
              <SourceCode path={data.path} content={data.content} />
              {data.truncated && <p>Nội dung đã được cắt bớt.</p>}
            </>
          )}
        </Load>
      )}
    </section>
  );
}
export function SourcePage({ admin = false }: { admin?: boolean }) {
  const { id = '' } = useParams();
  const [search] = useSearchParams(),
    [compare, setCompare] = useState(search.get('compare') || '');
  const submission = useApi(admin ? 'adminGetSubmission' : 'getSubmission', { path: { id } });
  const other = useApi('adminGetSubmission', { path: { id: compare } }, admin && !!compare);
  return (
    <>
      <Heading
        title="Kiểm tra mã nguồn"
        description="Tệp nguồn hiển thị dạng văn bản, không thực thi trong trình duyệt."
      />
      <Load query={submission}>
        {(s) => (
          <>
            <p>
              {s.language} · <Badge value={s.status} />
            </p>
            {admin && (
              <Field label="ID bản nộp để so sánh">
                <input value={compare} onChange={(e) => setCompare(e.target.value)} />
              </Field>
            )}
            <div className={compare && admin ? 'two-col' : ''}>
              <SourcePane key={id} id={id} admin={admin} />
              {admin && compare && (
                <Load query={other}>{() => <SourcePane key={compare} id={compare} admin />}</Load>
              )}
            </div>
            <section className="card">
              <h2>Nhật ký build</h2>
              <BuildLog id={id} admin={admin} />
            </section>
          </>
        )}
      </Load>
    </>
  );
}
export function SimilarityPage() {
  const [page, setPage] = useState(1);
  const query = useApi('adminSimilarity', { query: { page } });
  return (
    <>
      <Heading
        title="Kiểm tra trùng lặp"
        description="Điểm tương đồng hỗ trợ review, không tự kết luận vi phạm."
      />
      <Load query={query}>
        {(data) => (
          <>
            <Table
              rows={data.items}
              columns={[
                {
                  title: 'Cặp bản nộp',
                  render: (r) => (
                    <>
                      {r.submission_a.slice(0, 8)} / {r.submission_b.slice(0, 8)}
                    </>
                  ),
                },
                { title: 'Điểm', render: (r) => r.score },
                { title: 'Kiểm tra lúc', render: (r) => date(r.checked_at) },
                {
                  title: 'Xem nguồn',
                  render: (r) => (
                    <Link to={`/submissions/${r.submission_a}?compare=${r.submission_b}`}>
                      So sánh hai bên
                    </Link>
                  ),
                },
              ]}
            />
            <Pager page={page} total={data.total} setPage={setPage} />
          </>
        )}
      </Load>
    </>
  );
}
export function AuditPage() {
  const [page, setPage] = useState(1),
    [actor, setActor] = useState(''),
    [action, setAction] = useState('');
  const query = useApi('adminAuditLog', {
    query: { page, actor_user_id: actor || undefined, action: action || undefined },
  });
  return (
    <>
      <Heading title="Nhật ký kiểm toán" description="Lịch sử chỉ đọc của các thao tác quản trị." />
      <div className="filters">
        <Field label="ID người thực hiện">
          <input
            value={actor}
            onChange={(e) => {
              setActor(e.target.value);
              setPage(1);
            }}
          />
        </Field>
        <Field label="Thao tác">
          <input
            value={action}
            onChange={(e) => {
              setAction(e.target.value);
              setPage(1);
            }}
          />
        </Field>
      </div>
      <Load query={query}>
        {(data) => (
          <>
            <Table
              rows={data.items}
              columns={[
                { title: 'Thời điểm', render: (r) => date(r.created_at) },
                { title: 'Người thực hiện', render: (r) => r.actor_user_id ?? 'Hệ thống' },
                { title: 'Thao tác', render: (r) => r.action },
                { title: 'Đối tượng', render: (r) => `${r.target_type} ${r.target_id ?? ''}` },
                {
                  title: 'Chi tiết',
                  render: (r) => (
                    <details>
                      <summary>Mở</summary>
                      <pre>{JSON.stringify(r.payload, null, 2)}</pre>
                    </details>
                  ),
                },
              ]}
            />
            <Pager page={page} total={data.total} setPage={setPage} />
          </>
        )}
      </Load>
    </>
  );
}
export function AnnouncementsPage() {
  const [page, setPage] = useState(1),
    [body, setBody] = useState(''),
    [title, setTitle] = useState('');
  const query = useApi('adminAnnouncements', { query: { page } });
  return (
    <>
      <Heading title="Thông báo" description="Soạn bản nháp, xem trước rồi công bố." />
      <div className="two-col">
        <section className="card">
          <h2>Soạn thông báo</h2>
          <MutationForm
            op="adminCreateAnnouncement"
            title="Lưu bản nháp"
            confirm
            body={() => ({ title, body })}
          >
            <Field label="Tiêu đề">
              <input required value={title} onChange={(e) => setTitle(e.target.value)} />
            </Field>
            <Field label="Nội dung Markdown">
              <textarea required rows={8} value={body} onChange={(e) => setBody(e.target.value)} />
            </Field>
          </MutationForm>
        </section>
        <section className="card">
          <h2>Xem trước: {title}</h2>
          <Markdown>{body}</Markdown>
        </section>
      </div>
      <Load query={query}>
        {(data) => (
          <>
            {data.items.map((item) => (
              <section className="card" key={item.id}>
                <h2>{item.title}</h2>
                <small>{item.published_at ? `Đã công bố ${date(item.published_at)}` : 'Bản nháp'}</small>
                <Markdown>{item.body}</Markdown>
                <details>
                  <summary>Chỉnh sửa</summary>
                  <MutationForm
                    op="adminUpdateAnnouncement"
                    path={{ id: item.id }}
                    title="Lưu thông báo"
                    confirm
                    body={(f) => ({ title: text(f, 'title'), body: text(f, 'body') })}
                  >
                    <Field label="Tiêu đề">
                      <input name="title" defaultValue={item.title} required />
                    </Field>
                    <Field label="Nội dung">
                      <textarea name="body" defaultValue={item.body} rows={6} required />
                    </Field>
                  </MutationForm>
                </details>
                <MutationForm
                  op="adminPublishAnnouncement"
                  path={{ id: item.id }}
                  title="Công bố"
                  confirm
                  disabled={!!item.published_at}
                  body={(f) => ({ reason: text(f, 'reason') })}
                >
                  <Reason />
                </MutationForm>
              </section>
            ))}
            <Pager page={page} total={data.total} setPage={setPage} />
          </>
        )}
      </Load>
    </>
  );
}
