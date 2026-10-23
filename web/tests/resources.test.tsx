import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { Scrimmage } from '../src/participant';
import { QueuePage } from '../src/admin';
import { Practice } from '../src/practice';
import quota from '../../contracts/examples/http/scrimmageQuota.response.json';
import paused from '../../contracts/examples/scrimmage-paused.json';
import opponents from '../../contracts/examples/http/listOpponents.response.json';
import scrimmages from '../../contracts/examples/http/listScrimmages.response.json';
import queue from '../../contracts/examples/http/adminQueue.response.json';
import replay from '../../contracts/examples/replay-goal.json';
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
function scrimmagePage(quotaBody: unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) =>
      json(url.includes('/quota') ? quotaBody : url.includes('/opponents') ? opponents : scrimmages),
    ),
  );
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <Scrimmage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
const startButton = () => screen.getByRole('button', { name: 'Bắt đầu đánh tập' }) as HTMLButtonElement;
it('allows a scrimmage while the server accepts and the team has a free slot', async () => {
  scrimmagePage(quota);
  await screen.findByText(/trận chờ hoặc đang chạy/);
  await waitFor(() => expect(startButton().disabled).toBe(false));
});
it('explains a tournament pause and keeps the start button disabled', async () => {
  scrimmagePage(paused);
  expect((await screen.findByRole('status')).textContent).toContain('Giải đấu đang chạy');
  expect(screen.getByRole('status').textContent).toContain('Các trận đã tạo vẫn chạy tiếp');
  expect(startButton().disabled).toBe(true);
});
it('disables the start button when the team already uses every slot', async () => {
  scrimmagePage({ ...quota, active: 2, active_limit: 2 });
  await screen.findByText(/Hãy chờ một trận kết thúc/);
  expect(startButton().disabled).toBe(true);
});
it('shows the scrimmage admission state to admins', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () =>
      json({ ...queue, scrimmage_admission: { accepting: false, paused_reason: 'scrimmage_backlog' } }),
    ),
  );
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <QueuePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  expect((await screen.findByText(/Đang tạm dừng/)).textContent).toContain('Hàng đợi đánh tập đang đầy');
});
it('opens a local replay file without contacting the server', async () => {
  const fetch = vi.fn();
  vi.stubGlobal('fetch', fetch);
  render(
    <MemoryRouter>
      <Practice />
    </MemoryRouter>,
  );
  expect(screen.getByText(/practice duong\/dan\/bot-cua-ban --vs greedy/)).toBeTruthy();
  const input = screen.getByLabelText('Chọn file replay');
  fireEvent.change(input, { target: { files: [new File([JSON.stringify(replay)], 'replay-1.json')] } });
  await screen.findByRole('img');
  expect(screen.getByText('replay-1.json')).toBeTruthy();
  fireEvent.change(input, { target: { files: [new File(['{oops'], 'broken.json')] } });
  expect((await screen.findByRole('alert')).textContent).toContain('không phải JSON');
  expect(fetch).not.toHaveBeenCalled();
});
