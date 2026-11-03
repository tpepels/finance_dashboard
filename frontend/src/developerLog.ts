/** Safe, structured API view: export only explicitly selected fields. */
export type DiagnosticEvent = {
  at: string; level: 'info' | 'warning' | 'error'; scope: string; event: string;
  action?: string; job_id?: string; source_id?: string;
  stage?: string; status?: string; reason?: string;
  completed?: number; total?: number; failed?: number; http_status?: number;
};
export type DiagnosticJob = {
  id?: string; action?: string; status?: string;
  created_at?: string; finished_at?: string;
  completed?: number; total?: number;
  parts?: Record<string,{
    status?: string; reason?: string; failed?: number; missing?: number;
    downloaded?: number; sources?: number; http_status?: number;
    funds?: {id?: string; status?: string; stored?: number; errors?: number;
      http_status?: number; reason?: string}[];
  }>;
};
export type DiagnosticReport = {
  schema_version: number; generated_at: string;
  coverage: { registered: number; with_data: number; needs_attention: number };
  issues: { family: string; id: string; state: string;
    latest_source_date: string | null; last_failure_code: string | null }[];
  jobs: DiagnosticJob[];
  events: DiagnosticEvent[];
  retention: string;
};
const value = (v: unknown): string => v == null ? '—' : String(v);
const field = (key: string, v: unknown): string => v == null ? '' : ' ' + key + '=' + String(v);
export function eventLine(e: DiagnosticEvent): string {
  return [e.at, e.level.toUpperCase(), e.scope + '.' + e.event,
    field('source',e.source_id),field('stage',e.stage),field('action',e.action),
    field('status',e.status),field('reason',e.reason),
    field('failed',e.failed),field('done',e.completed),
    field('total',e.total),field('http',e.http_status)].join(' ').replace(/\s+/g,' ').trim();
}
export function formatDeveloperLog(report: DiagnosticReport): string {
  const lines: string[] = [
    'GLOBAL CAPITAL MONITOR — DEVELOPER DIAGNOSTICS',
    'Generated (UTC): ' + report.generated_at,
    'Coverage: ' + report.coverage.with_data + '/' + report.coverage.registered
      + ' sources stored, ' + report.coverage.needs_attention + ' attention items',
    'Retention: ' + report.retention,
    '',
    'SOURCE ISSUES (' + report.issues.length + ')',
  ];
  if (!report.issues.length) lines.push('None reported');
  for (const row of report.issues) lines.push(
    row.family + ' / ' + row.id + ' / ' + row.state
    + ' / last=' + value(row.latest_source_date)
    + ' / error=' + value(row.last_failure_code));
  lines.push('', 'RECENT DATA JOBS (' + report.jobs.length + ')');
  if (!report.jobs.length) lines.push('None recorded');
  for (const job of report.jobs) {
    lines.push('Job ' + value(job.action) + ' / ' + value(job.status)
      + ' / started=' + value(job.created_at)
      + ' / finished=' + value(job.finished_at));
    for (const [key, part] of Object.entries(job.parts ?? {})) {
      lines.push('  ' + key + ' / ' + value(part.status)
        + field('reason',part.reason) + field('failed',part.failed)
        + field('missing',part.missing) + field('downloaded',part.downloaded)
        + field('http',part.http_status));
      for (const fund of part.funds ?? []) {
        lines.push('    fund=' + value(fund.id) + ' status=' + value(fund.status)
          + field('filings',fund.stored) + field('errors',fund.errors)
          + field('reason',fund.reason) + field('http',fund.http_status));
      }
    }
  }
  lines.push('', 'EVENT LOG (' + report.events.length + ')');
  if (!report.events.length) lines.push('No events collected yet; run a sync to generate them');
  for (const item of report.events) lines.push(eventLine(item));
  lines.push('', 'Structured source diagnostics only; no HTTP payloads, headers or secrets are recorded.');
  return lines.join('\n') + '\n';
}
