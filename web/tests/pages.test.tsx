import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { GamePage, Upload } from '../src/participant';
import game from '../../contracts/examples/http/getGame.response.json';
import replay from '../../contracts/examples/replay.json';
import capabilities from '../../contracts/examples/http/capabilities.response.json';
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it('renews expired replay URL once and never fetches admin stderr for participant', async () => {
  let urls = 0;
  const fetchMock = vi.fn(async (url: string) => {
    if (url.endsWith('/replay'))
      return json({
        url: `https://storage.example.test/replay-${++urls}`,
        expires_at: '2099-01-01T00:00:00Z',
      });
    if (url === 'https://storage.example.test/replay-1') return json({}, 403);
    if (url === 'https://storage.example.test/replay-2') return json(replay);
    return json(game);
  });
  vi.stubGlobal('fetch', fetchMock);
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[`/games/${game.id}`]}>
        <Routes>
          <Route path="/games/:id" element={<GamePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await waitFor(() => expect(screen.getByRole('img')).toBeTruthy());
  expect(urls).toBe(2);
  expect(fetchMock.mock.calls.some(([url]) => url.includes('/admin/'))).toBe(false);
});
it('rejects oversized ZIP before upload and disables submit', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => json(capabilities)),
  );
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <Upload />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  const input = await screen.findByLabelText('Tệp bot ZIP');
  fireEvent.change(input, {
    target: { files: [new File([new Uint8Array(1048577)], 'bot.zip', { type: 'application/zip' })] },
  });
  expect(screen.getByRole('alert').textContent).toContain('không quá 1 MiB');
  expect((screen.getByText('Tải lên và build') as HTMLButtonElement).disabled).toBe(true);
});
