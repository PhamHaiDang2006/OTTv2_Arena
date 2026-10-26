import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { EditProfile, PublicProfile } from '../src/profile';
import fixture from '../../contracts/examples/http/myProfile.response.json';
import type { User } from '../../contracts/generated/types';

const user: User = {
  id: fixture.user_id,
  email: 'secret@example.test',
  role: 'member',
  team_id: null,
  is_active: true,
};
const clients: QueryClient[] = [];
afterEach(() => {
  cleanup();
  clients.splice(0).forEach((c) => c.clear());
  vi.unstubAllGlobals();
});
function open(edit: boolean) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  clients.push(client);
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[edit ? '/profile' : `/players/${user.id}`]}>
        <Routes>
          <Route path="/profile" element={<EditProfile user={user} />} />
          <Route path="/players/:id" element={<PublicProfile user={null} />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
it('saves chosen cosmetics and text without sending statistics or private account fields', async () => {
  let sent: unknown;
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_url: string, init: RequestInit) => {
      if (init.method === 'PUT') sent = JSON.parse(init.body as string);
      return new Response(JSON.stringify({ ...fixture, ...((sent as object) ?? {}) }));
    }),
  );
  open(true);
  const input = await screen.findByLabelText('Tên hiển thị');
  fireEvent.change(input, { target: { value: 'Mèo chiến thuật' } });
  fireEvent.change(screen.getByLabelText(/Giới thiệu ngắn/), { target: { value: 'Hẹn trên bàn Hexagon' } });
  fireEvent.click(screen.getByRole('button', { name: 'Chọn Mèo' }));
  fireEvent.change(screen.getByLabelText('Khung avatar'), { target: { value: 'double' } });
  fireEvent.change(screen.getByLabelText('Màu hồ sơ'), { target: { value: 'ocean' } });
  fireEvent.click(screen.getByRole('button', { name: 'Lưu hồ sơ' }));
  expect(await screen.findByText('Đã lưu hồ sơ.')).toBeTruthy();
  expect(sent).toEqual({
    display_name: 'Mèo chiến thuật',
    bio: 'Hẹn trên bàn Hexagon',
    avatar: 'cat',
    frame: 'double',
    color: 'ocean',
  });
});
it('public profile renders safe text and zero-game stats without login or email', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify({ ...fixture, bio: '<img src=x onerror=alert(1)>' }))),
  );
  open(false);
  expect(await screen.findByText('<img src=x onerror=alert(1)>')).toBeTruthy();
  expect(screen.queryByText(user.email)).toBeNull();
  expect(screen.queryByRole('button', { name: 'Lưu hồ sơ' })).toBeNull();
  expect(screen.getByText('—')).toBeTruthy();
  expect(document.querySelector('img[src="x"]')).toBeNull();
});
it('keeps the draft when saving fails', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_url: string, init: RequestInit) =>
      init.method === 'PUT'
        ? new Response(
            JSON.stringify({
              error: { code: 'SERVICE_UNAVAILABLE', message: 'Thử lại sau', details: {} },
              request_id: fixture.user_id,
            }),
            { status: 503 },
          )
        : new Response(JSON.stringify(fixture)),
    ),
  );
  open(true);
  fireEvent.change(await screen.findByLabelText('Tên hiển thị'), { target: { value: 'Giữ bản nháp' } });
  fireEvent.click(screen.getByRole('button', { name: 'Lưu hồ sơ' }));
  await waitFor(() => expect(screen.getByText(/Thử lại sau/)).toBeTruthy());
  expect((screen.getByLabelText('Tên hiển thị') as HTMLInputElement).value).toBe('Giữ bản nháp');
  expect(screen.queryByText('Đã lưu hồ sơ.')).toBeNull();
});
