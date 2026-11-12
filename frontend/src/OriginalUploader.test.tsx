// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import OriginalUploader from './OriginalUploader';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('original research file upload', () => {
  it('uploads selected archives and automatically queues import through the existing API', async () => {
    const sent: string[] = [];
    const queue: string[][] = [];
    const originals = { active: false, files: [] as { filename: string; bytes: number; kind: string }[],
      jobs: [] as unknown[] };
    class XMLHttpRequestMock {
      status = 201;
      responseText = '{}';
      upload = { onprogress: null as ((e: { lengthComputable: boolean; loaded: number; total: number }) => void) | null };
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      open(_method: string, url: string) { sent.push(url); }
      setRequestHeader(_key: string, _value: string) { /* same-origin action */ }
      send(file: File) {
        originals.files.push({ filename: file.name, bytes: file.size, kind: 'edition_archive' });
        Promise.resolve().then(() => this.onload?.());
      }
    }
    vi.stubGlobal('XMLHttpRequest', XMLHttpRequestMock);
    vi.stubGlobal('fetch', vi.fn(async (path: string, options?: RequestInit) => {
      if (path === '/api/originals/import') {
        const body = JSON.parse(String(options?.body)) as { filenames: string[] };
        queue.push(body.filenames);
        return { ok: true, json: async () => ({ id: 'job', status: 'queued' }) };
      }
      return { ok: true, json: async () => originals };
    }));
    const user = userEvent.setup();
    render(<OriginalUploader/>);
    const file = new File(['archive-content'], 'ICIO2021econA.zip', { type: 'application/zip' });
    await user.upload(screen.getByLabelText('Upload original research ZIP files and ReadMe workbook'), file);
    await waitFor(() => expect(queue).toEqual([['ICIO2021econA.zip']]));
    expect(sent[0]).toContain('filename=ICIO2021econA.zip');
    expect(screen.getByText(/Importing 1 archive/)).toBeTruthy();
  });

  it('reassesses already stored archives from the browser without re-upload', async () => {
    const requested: string[] = [];
    const originals = { active: false, files: [], jobs: [] as unknown[] };
    vi.stubGlobal('fetch', vi.fn(async (url: string, options?: RequestInit) => {
      if (url === '/api/originals/reassess') {
        requested.push(String(options?.headers && (options.headers as Record<string, string>)['X-GCM-Action']));
        return { ok: true, json: async () => ({ id: 'recheck', status: 'queued' }) };
      }
      return { ok: true, json: async () => originals };
    }));
    const user = userEvent.setup();
    render(<OriginalUploader/>);
    await user.click(screen.getByRole('button', { name: 'Reassess previously imported OECD originals' }));
    await waitFor(() => expect(requested).toEqual(['dashboard']));
    expect(screen.getByText(/Reassessing previously registered original archives/)).toBeTruthy();
  });

  it('retains a staged regular archive until its required ReadMe is supplied', async () => {
    const original = { active: false, files: [{
      filename: '1995-2000_SML.zip', bytes: 999, kind: 'verified_regular',
    }], jobs: [] };
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => original })));
    render(<OriginalUploader/>);
    expect(await screen.findByText('Uploaded originals (1)')).toBeTruthy();
    expect(screen.queryByText(/verified publisher regular original/)).toBeNull();
  });
});
