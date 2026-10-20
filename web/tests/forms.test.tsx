import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, expect, it, vi } from 'vitest';
import { MutationForm, Reason, text } from '../src/ui';
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it('requires confirmation and reason before queue mutation, surfaces 409', async () => {
  const mock = vi
    .fn()
    .mockResolvedValue(
      new Response(
        JSON.stringify({ error: { code: 'CONFLICT', message: 'Locked', details: {} }, request_id: 'test' }),
        { status: 409 },
      ),
    );
  vi.stubGlobal('fetch', mock);
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MutationForm
        op="adminControlQueue"
        title="Tạm dừng"
        confirm
        body={(f) => ({ name: 'build', paused: true, reason: text(f, 'reason') })}
      >
        <Reason />
      </MutationForm>
    </QueryClientProvider>,
  );
  fireEvent.change(screen.getByLabelText('Lý do'), { target: { value: 'Bảo trì' } });
  fireEvent.click(screen.getByText('Tạm dừng'));
  expect(mock).not.toHaveBeenCalled();
  expect(screen.getByRole('dialog')).toBeTruthy();
  fireEvent.click(screen.getByText('Xác nhận thực hiện'));
  await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('Trạng thái đã thay đổi'));
  expect(mock).toHaveBeenCalledTimes(1);
});
it('does not report CSV validation errors as a successful import', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({ created: [], errors: [{ row: 2, code: 'DUPLICATE', message: 'Trùng slug' }] }),
          { status: 201 },
        ),
      ),
  );
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MutationForm op="adminImportTeams" title="Nhập" body={() => ({ csv: 'bad' })} />
    </QueryClientProvider>,
  );
  fireEvent.click(screen.getByText('Nhập'));
  await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('Trùng slug'));
  expect(screen.queryByRole('status')).toBeNull();
});
