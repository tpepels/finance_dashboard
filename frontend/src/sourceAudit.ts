/** Stable and credential-free local source coverage CSV for evidence review. */
export interface SourceAuditRow {
  family: string;
  id: string;
  name: string;
  provider: string;
  frequency: string;
  state: string;
  collection_enabled: boolean;
  stored_periods: number;
  stored_versions?: number;
  additional_revisions?: number;
  unobserved_internal_periods?: number | null;
  oldest_source_date: string | null;
  latest_source_date: string | null;
  published_release?: string | null;
  published_through?: string | null;
  complete_for_pinned_release?: boolean;
  last_attempt_state: string;
  last_failure_code: string | null;
  last_success_utc?: string | null;
}
const COLUMNS: [keyof SourceAuditRow, string][] = [
  ['family', 'family'], ['id', 'canonical_id'], ['name', 'name'],
  ['provider', 'provider'], ['frequency', 'frequency'],
  ['state', 'state'], ['collection_enabled', 'collection_enabled'],
  ['stored_periods', 'distinct_source_periods'],
  ['stored_versions', 'stored_versions'],
  ['additional_revisions', 'additional_revisions'],
  ['unobserved_internal_periods', 'internal_calendar_gaps'],
  ['oldest_source_date', 'first_source_period'],
  ['latest_source_date', 'last_source_period'],
  ['published_release', 'pinned_release'],
  ['published_through', 'pinned_release_through'],
  ['complete_for_pinned_release', 'pinned_release_complete'],
  ['last_attempt_state', 'last_attempt_state'],
  ['last_failure_code', 'last_failure_code'],
  ['last_success_utc', 'last_success_utc'],
];
function cell(value: unknown): string {
  if (value == null) return '';
  const str = String(value);
  // Defend spreadsheet users from formula injection by untrusted source names.
  const safe = /^[\s]*[=+\-@]/.test(str) ? "'" + str : str;
  return '"' + safe.replace(/"/g, '""') + '"';
}
export function sourceAuditCsv(items: SourceAuditRow[], releaseId: string): string {
  return [
    [cell('app_release'), ...COLUMNS.map(([, name]) => cell(name))].join(','),
    ...items.map(item => [cell(releaseId), ...COLUMNS.map(([key]) => cell(item[key]))].join(',')),
  ].join('\r\n') + '\r\n';
}
