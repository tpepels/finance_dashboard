/** Deployed artifact identity supplied by the backend; never infer from the browser cache. */
export interface ReleaseInfo {
  version: string;
  build: string;
  release_id: string;
  activated_at: string | null;
}

/** Safe identifier for downloaded report filenames. */
export function releaseFilenameId(release: ReleaseInfo | undefined): string {
  const id = release?.release_id;
  return id && /^[A-Za-z0-9][A-Za-z0-9.+_-]{0,100}$/.test(id) ? id : 'unknown-build';
}
