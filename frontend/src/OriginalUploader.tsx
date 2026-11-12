import { useEffect, useRef, useState } from 'react';

type StoredFile = { filename: string; bytes: number; kind: string };
type Result = { filename: string; status: string; error_code?: string; edition?: string; table?: string };
type ImportJob = {
  id: string; status: string; completed: number; total: number;
  error_code?: string | null; results: Result[];
};
type Inventory = { active: boolean; readme_available?: boolean; files: StoredFile[]; jobs: ImportJob[] };

const READ_ME = 'ReadMe_ICIO_small.xlsx';
const initial: Inventory = { active: false, files: [], jobs: [] };
const size = (bytes: number) => bytes < 1024 * 1024
  ? (bytes / 1024).toFixed(0) + ' KB'
  : (bytes / (1024 * 1024)).toFixed(1) + ' MB';

function uploadedSuccessfully(job: ImportJob[], filename: string) {
  for (const entry of job) {
    const found = entry.results.find(result => result.filename === filename);
    if (found) return found.status !== 'failed';
  }
  return false;
}

/** Originals are uploaded as bounded streams, then passed through the canonical server importer. */
export default function OriginalUploader() {
  const [inventory, setInventory] = useState<Inventory>(initial);
  const [activity, setActivity] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const queuedJob = useRef<string | null>(null);
  const acceptStatus = (next: Inventory) => {
    setInventory(next);
    const latest = next.jobs[0];
    if (!next.active && latest && queuedJob.current === latest.id &&
        ['complete', 'partial', 'failed'].includes(latest.status)) {
      queuedJob.current = null;
      window.dispatchEvent(new Event('gcm-data-updated'));
    }
  };

  const refresh = async () => {
    const response = await fetch('/api/originals', { cache: 'no-store' });
    if (!response.ok) throw new Error('Could not read original import status (' + response.status + ')');
    const data = await response.json() as Inventory;
    acceptStatus(data);
    return data;
  };
  useEffect(() => {
    let active = true;
    const poll = () => {
      void fetch('/api/originals', { cache: 'no-store' })
        .then(res => { if (!res.ok) throw new Error('Original upload status unavailable'); return res.json() as Promise<Inventory>; })
.then(next => { if (active) acceptStatus(next); })
        .catch(() => { if (active) setError('Cannot read original import status.'); });
    };
    poll();
    const interval = window.setInterval(poll, inventory.active ? 3000 : 30000);
    return () => { active = false; window.clearInterval(interval); };
  }, [inventory.active]);

  const send = (file: File, index: number, total: number) => new Promise<void>((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open('POST', '/api/originals/upload?filename=' + encodeURIComponent(file.name));
    request.setRequestHeader('Content-Type', 'application/octet-stream');
    request.setRequestHeader('X-GCM-Action', 'dashboard');
    request.upload.onprogress = progress => {
      if (progress.lengthComputable) {
        setActivity('Uploading ' + index + '/' + total + ': ' + file.name +
          ' (' + Math.round(progress.loaded * 100 / progress.total) + '%)');
      }
    };
    request.onerror = () => reject(new Error('Network error uploading ' + file.name));
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) resolve();
      else {
        let detail = 'Upload rejected (' + request.status + ')';
        try { detail = JSON.parse(request.responseText).detail || detail; } catch { /* optional */ }
        reject(new Error(file.name + ': ' + detail));
      }
    };
    request.send(file);
  });

  const importFiles = async (data: Inventory, selected: string[]) => {
    const staged = data.files.filter(file => file.kind !== 'readme' &&
      !uploadedSuccessfully(data.jobs, file.filename));
    const filenames = [...new Set([...selected.filter(name => name !== READ_ME),
      ...staged.map(item => item.filename)])];
    if (!filenames.length) {
      setActivity('All selected originals are already registered.');
      return;
    }
    const hasReadme = data.readme_available || data.files.some(file => file.filename === READ_ME);
    const ready = hasReadme ? filenames : filenames.filter(name => !data.files.some(
      file => file.filename === name && file.kind === 'verified_regular'));
    if (!ready.length) {
      setActivity('Regular archive stored. Upload ' + READ_ME + ' to validate the matrices.');
      return;
    }
    if (data.active) {
      setActivity('Another original import is running. Files are staged for the next import.');
      return;
    }
    const response = await fetch('/api/originals/import', {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-GCM-Action': 'dashboard' },
      body: JSON.stringify({ filenames: ready }),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({})) as { detail?: string };
      throw new Error(body.detail ?? 'Import could not start (' + response.status + ')');
    }
    const queued = await response.json() as { id: string };
    queuedJob.current = queued.id;
    setActivity('Importing ' + ready.length + ' archive(s); progress appears below.' +
      (ready.length < filenames.length ? ' Regular archives wait for the matching ReadMe.' : ''));
    await refresh();
  };

  const chooseFiles = async (fileList: FileList | null) => {
    const chosen = [...(fileList ?? [])];
    if (!chosen.length) return;
    setBusy(true); setError(''); setActivity('Uploading original files…');
    const succeeded: string[] = [];
    try {
      const ordered = chosen.sort((a, b) => (a.name === READ_ME ? -1 : b.name === READ_ME ? 1 : 0));
      for (let index = 0; index < ordered.length; index++) {
        await send(ordered[index], index + 1, ordered.length);
        if (ordered[index].name !== READ_ME) succeeded.push(ordered[index].name);
      }
      const current = await refresh();
      await importFiles(current, succeeded);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Original upload failed');
      await refresh().catch(() => undefined);
    } finally {
      setBusy(false);
    }
  };
  const latest = inventory.jobs[0];
  return <section className="original-uploader" aria-labelledby="original-uploader-heading">
    <header>
      <h3 id="original-uploader-heading">Import original research files</h3>
      <p>Upload official OECD ICIO ZIP archives and the matching ReadMe workbook. Files are
        verified and registered in the existing research store; already stored evidence is preserved.</p>
    </header>
    <label className="original-file-picker">
      <span>{busy ? 'Uploading…' : 'Choose research files to upload'}</span>
      <input type="file" accept=".zip,.xlsx" multiple disabled={busy}
        aria-label="Upload original research ZIP files and ReadMe workbook"
        onChange={event => {
          void chooseFiles(event.currentTarget.files);
          event.currentTarget.value = '';
        }}/>
    </label>
    {activity && <p role="status" className="original-import-activity">{activity}</p>}
    {error && <p role="alert" className="original-import-error">{error}</p>}
    {latest && <div className="original-import-job" role="status">
      <strong>Import: {latest.status}</strong>
      <span>{latest.completed} of {latest.total} archives processed</span>
      <progress max={latest.total} value={latest.completed}/>
      {latest.results.length > 0 && <ul>{latest.results.map(result =>
        <li key={result.filename}>
          <strong>{result.filename}</strong>: {result.status.replaceAll('_', ' ')}
          {result.error_code && <small> · {result.error_code}</small>}
        </li>)}</ul>}
    </div>}
    {inventory.files.some(file => file.kind !== 'readme' &&
      !uploadedSuccessfully(inventory.jobs, file.filename)) && !inventory.active &&
      <button type="button" className="original-resume-import" disabled={busy}
        onClick={() => { void importFiles(inventory, []).catch(reason =>
          setError(reason instanceof Error ? reason.message : 'Import could not start')); }}>
        Import pending uploaded archives
      </button>}
    {inventory.files.length > 0 && <details className="original-staged-files">
      <summary>Uploaded originals ({inventory.files.length})</summary>
      <ul>{inventory.files.map(file => <li key={file.filename}>
        <span>{file.filename}</span><small>{size(file.bytes)}</small>
      </li>)}</ul>
    </details>}
    <p className="original-import-note">2025 regular matrices receive the full pinned original
      accounting audit. Extended and 2018/2021 editions are preserved and indexed, but remain
      unverified for economic comparability until their edition-specific dimensions are validated.</p>
  </section>;
}
