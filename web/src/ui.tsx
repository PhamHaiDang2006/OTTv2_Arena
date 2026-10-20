import { useState, type ReactNode, type FormEvent } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useReactTable, getCoreRowModel, flexRender, type ColumnDef } from '@tanstack/react-table';
import type { Operations } from '../../contracts/generated/operations';
import type { RequestOptions } from '../../contracts/client';
import { api, errorText, type Op } from './api';
type ReadOp = { [K in Op]: Operations[K]['request'] extends undefined ? K : never }[Op];
export function useApi<K extends ReadOp>(op: K, options: RequestOptions = {}, enabled = true, poll = 0) {
  return useQuery({
    queryKey: [op, options.path, options.query],
    queryFn: ({ signal }) =>
      api(op, undefined as K extends 'createSubmission' ? FormData : Operations[K]['request'], {
        ...options,
        signal,
      }),
    enabled,
    retry: false,
    refetchInterval: poll || false,
    refetchIntervalInBackground: false,
  });
}
export function ErrorBox({ error }: { error: unknown }) {
  return error ? (
    <p className="error" role="alert">
      {errorText(error)}
    </p>
  ) : null;
}
export function Load<T>({
  query,
  children,
}: {
  query: { isPending: boolean; error: unknown; data: T | undefined; refetch: () => unknown };
  children: (data: T) => ReactNode;
}) {
  if (query.isPending)
    return (
      <p role="status" className="muted">
        Đang tải dữ liệu…
      </p>
    );
  if (query.error)
    return (
      <>
        <ErrorBox error={query.error} />
        <button onClick={() => query.refetch()}>Tải lại</button>
      </>
    );
  return query.data === undefined ? null : <>{children(query.data)}</>;
}
export function Table<T>({
  rows,
  columns,
}: {
  rows: T[];
  columns: { title: string; render: (row: T) => ReactNode }[];
}) {
  const defs: ColumnDef<T>[] = columns.map((col, i) => ({
    id: String(i),
    header: col.title,
    cell: (ctx) => col.render(ctx.row.original),
  }));
  const table = useReactTable({ data: rows, columns: defs, getCoreRowModel: getCoreRowModel() });
  if (!rows.length) return <p className="empty">Chưa có dữ liệu.</p>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          {table.getHeaderGroups().map((group) => (
            <tr key={group.id}>
              {group.headers.map((header) => (
                <th key={header.id}>{flexRender(header.column.columnDef.header, header.getContext())}</th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr key={row.id}>
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
export function Pager({
  page,
  total,
  setPage,
}: {
  page: number;
  total: number;
  setPage: (n: number) => void;
}) {
  return (
    <div className="pager">
      <button disabled={page <= 1} onClick={() => setPage(page - 1)}>
        ← Trước
      </button>
      <span>
        Trang {page} · {total} mục
      </span>
      <button disabled={page * 20 >= total} onClick={() => setPage(page + 1)}>
        Sau →
      </button>
    </div>
  );
}
const labels: Record<string, string> = {
  queued: 'Đang chờ',
  building: 'Đang build',
  ready: 'Sẵn sàng',
  failed: 'Lỗi',
  running: 'Đang chạy',
  finished: 'Hoàn tất',
  blocked: 'Bị chặn',
  infra_error: 'Lỗi hạ tầng',
  pending: 'Chờ duyệt',
  approved: 'Đã duyệt',
  disqualified: 'Bị loại',
  draft: 'Bản nháp',
  frozen: 'Đã đóng băng',
  drawn: 'Đã bốc thăm',
};
export function Badge({ value }: { value: string }) {
  return <span className={`badge ${value}`}>{labels[value] ?? value}</span>;
}
export function Heading({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children?: ReactNode;
}) {
  return (
    <header className="page-head">
      <div>
        <p className="eyebrow">OTT v2 / ARENA</p>
        <h1>{title}</h1>
        {description && <p className="muted">{description}</p>}
      </div>
      {children}
    </header>
  );
}
export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}
export function MutationForm<K extends Op>({
  title,
  op,
  path,
  children,
  body,
  confirm = false,
  disabled = false,
  onSuccess,
  fetchImpl,
}: {
  title: string;
  op: K;
  path?: Record<string, string>;
  children?: ReactNode;
  body: (form: FormData) => K extends 'createSubmission' ? FormData : Operations[K]['request'];
  confirm?: boolean;
  disabled?: boolean;
  onSuccess?: (value: Operations[K]['response']) => void;
  fetchImpl?: typeof fetch;
}) {
  const cache = useQueryClient();
  const [candidate, setCandidate] = useState<ReturnType<typeof body> | null>(null);
  const mutation = useMutation({
    mutationFn: async (value: ReturnType<typeof body>) => {
      const result = await api(op, value, { path, fetchImpl });
      if (
        result &&
        typeof result === 'object' &&
        'errors' in result &&
        Array.isArray(result.errors) &&
        result.errors.length
      ) {
        throw new Error(
          `Chưa nhập đội: ${result.errors.map((e) => `dòng ${e.row}: ${e.message}`).join('; ')}`,
        );
      }
      return result;
    },
    retry: false,
    onSuccess: (value) => {
      onSuccess?.(value);
    },
    onSettled: () => {
      setCandidate(null);
      void cache.invalidateQueries();
    },
  });
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const value = body(new FormData(event.currentTarget));
    if (confirm) setCandidate(value);
    else mutation.mutate(value);
  };
  return (
    <form className="action-form" onSubmit={submit}>
      {children}
      <button className="primary" disabled={disabled || mutation.isPending || candidate !== null}>
        {mutation.isPending ? 'Đang gửi…' : title}
      </button>
      <ErrorBox error={mutation.error} />
      {mutation.isSuccess && (
        <p role="status" className="success">
          Yêu cầu đã được tiếp nhận. Danh sách đã được cập nhật.
        </p>
      )}
      {candidate !== null && (
        <div className="modal-backdrop">
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-label={`Xác nhận ${title}`}
            onKeyDown={(event) => {
              if (event.key === 'Escape' && !mutation.isPending) setCandidate(null);
              if (event.key === 'Tab') {
                const buttons = [
                  ...event.currentTarget.querySelectorAll<HTMLButtonElement>('button:not(:disabled)'),
                ];
                const index = buttons.indexOf(document.activeElement as HTMLButtonElement);
                if (buttons.length) {
                  event.preventDefault();
                  buttons[(index + (event.shiftKey ? -1 : 1) + buttons.length) % buttons.length].focus();
                }
              }
            }}
          >
            <h2>Xác nhận: {title}</h2>
            <p>Thao tác sẽ thay đổi dữ liệu trên máy chủ.</p>
            <dl>
              {Object.entries(candidate ?? {}).map(([key, value]) => (
                <div key={key}>
                  <dt>{confirmationLabels[key] ?? key}</dt>
                  <dd>
                    {value === null
                      ? 'Không đặt'
                      : typeof value === 'boolean'
                        ? value
                          ? 'Có'
                          : 'Không'
                        : String(value)}
                  </dd>
                </div>
              ))}
            </dl>
            <button type="button" autoFocus disabled={mutation.isPending} onClick={() => setCandidate(null)}>
              Hủy
            </button>{' '}
            <button
              className="primary"
              type="button"
              disabled={mutation.isPending}
              onClick={() => mutation.mutate(candidate)}
            >
              Xác nhận thực hiện
            </button>
          </section>
        </div>
      )}
    </form>
  );
}
const confirmationLabels: Record<string, string> = {
  name: 'Tên',
  reason: 'Lý do',
  paused: 'Tạm dừng',
  is_locked: 'Khóa đội',
  seed: 'Hạt giống',
  slug: 'Slug đội',
  captain_email: 'Email đội trưởng',
  status: 'Trạng thái',
  csv: 'CSV sẽ nhập',
  engine_version: 'Engine',
  ruleset_id: 'Luật',
  stage: 'Giai đoạn',
  freeze_at: 'Đóng băng lúc (UTC)',
  winner_team_id: 'ID đội thắng',
  score_a: 'Điểm đội A',
  score_b: 'Điểm đội B',
  title: 'Tiêu đề',
  body: 'Nội dung',
};
export function Reason() {
  return (
    <Field label="Lý do">
      <input
        name="reason"
        required
        minLength={1}
        maxLength={2000}
        placeholder="Giải thích để lưu vào nhật ký kiểm toán"
      />
    </Field>
  );
}
export const text = (form: FormData, key: string) => String(form.get(key) ?? '').trim();
export const date = (value: string | null) => (value ? new Date(value).toLocaleString('vi-VN') : 'Chưa đặt');
