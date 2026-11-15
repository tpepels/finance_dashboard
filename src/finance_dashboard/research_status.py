"""Read-only research navigation derived from the canonical acceptance snapshot."""
from __future__ import annotations

from collections import Counter

from .engine.acceptance import analysis_phase2, grouped
from .engine.runner import list_analyses



def evidence_next_step(analysis_id: str, research_state: str,
                       roles: list[dict], open_gates: list[str]) -> dict:
    """Describe what remains without mistaking supplemental work for a core failure.

    Action eligibility is derived solely from the accepted corpus and the
    current scientific evaluation. A missing source does not imply that the
    owner must upload a file, and a registered source is not accepted evidence.
    """
    required = [role for role in roles
                if not role.get('supplemental') and role.get('state') != 'descoped']
    supplemental = [role for role in roles if role.get('supplemental')]
    pending = [role for role in required if not role.get('accepted')]
    owner = [role for role in pending if role.get('owner_input_required')]
    source_absent = [role for role in pending
                     if role.get('series_ids') and
                     not role.get('sources_with_observations')]
    source_review = [role for role in pending
                     if role.get('series_ids') and
                     role.get('sources_with_observations')]
    unmapped = [role for role in pending
                if not role.get('series_ids') and
                not role.get('owner_input_required')]
    counts = {
        'required': len(required),
        'required_accepted': sum(role.get('accepted') is True for role in required),
        'supplemental': len(supplemental),
        'supplemental_accepted': sum(role.get('accepted') is True
                                     for role in supplemental),
        'descoped': sum(role.get('state') == 'descoped' for role in roles),
    }
    def result(kind, message, link=None):
        return {'kind': kind, 'message': message, 'link': link,
                'role_count': len(pending), 'role_ids': [role['role'] for role in pending],
                'counts': counts}
    if research_state == 'not_checked':
        return result('assessment_pending',
                      'The scientific assessment has not finished. No action is requested.')
    if owner:
        link = '#portfolio' if analysis_id.startswith('P') else None
        return result('owner_information',
                      'Your own information is needed for part of this analysis. '
                      'The other source checks continue independently.', link)
    if research_state == 'accepted':
        if any(not role.get('accepted') for role in supplemental):
            return result('accepted_with_extensions',
                          'The original research method is accepted. Some additional '
                          'research comparisons still lack verified source evidence.')
        return result('ready',
                      'The original research method passed its scientific checks. '
                      'No action is needed.')
    if unmapped:
        return result('original_research',
                      'A required original source or compatible economic definition '
                      'has not been verified. The finding remains qualified or withheld.')
    if source_absent:
        return result('publisher_data',
                      'Required publisher observations are missing. Check Data & diagnostics '
                      'for automatic collection progress and any genuine manual-file request.',
                      '#research-sources')
    if source_review or open_gates:
        return result('scientific_review',
                      'Source observations require further scientific verification. '
                      'The research assessment will update after accepted evidence changes.')
    if research_state in ('conditional', 'deferred', 'incomplete'):
        return result('qualified',
                      'This analysis retains documented evidence and method limitations.')
    return result('assessment_pending',
                  'Scientific assessment is pending. No action is requested.')



def research_next_actions(snapshot, document: dict) -> dict:
    """Bounded research-readiness summary for the on-demand diagnostic ZIP.

    A submitted source is not an accepted original. Owner action is named
    only for an explicitly missing user-supplied input. The per-question
    entries are derived from the same acceptance snapshot as the UI.
    """
    if snapshot is None:
        return {'status': 'assessment_unavailable', 'evaluated_at': None,
                'counts': {}, 'next_action_counts': {}, 'questions': [],
                'note': 'A complete scientific assessment was not yet available.'}
    from collections import Counter
    report = research_status(snapshot, document)
    questions = []
    for row in report['questions']:
        step = row['next_step']
        questions.append({
            'id': row['analysis_id'],
            'state': row['phase2']['state'],
            'next_step': step,
            'open_gates': row['phase2']['open_gates'],
            'limitations_count': len(row['phase2']['limitations']),
        })
    return {
        'status': 'ready',
        'evaluated_at': report['evaluated_at'],
        'question_count': len(questions),
        'counts': report['counts'],
        'next_action_counts': dict(Counter(q['next_step']['kind'] for q in questions)),
        'questions': questions,
        'note': ('A methodological role may remain unaccepted despite source data '
                 'having been downloaded. Owner inputs are requested only when '
                 'the canonical owner-supplied role is missing.'),
    }

def research_status(snapshot, document: dict) -> dict:
    """Describe current scope; never compute, accept or promote an input here."""
    definitions = {r['id']: r for r in document['analyses']}
    questions = []
    for row in list_analyses(snapshot, document):
        aid = row['analysis_id']
        definition = definitions[aid]
        acceptance = snapshot.analyses.get(aid, {})
        originals = {r['role']: r for r in (definition.get('comparison_contract') or {}).get(
            'original_requirements', [])}
        roles = []
        for role in acceptance.get('requirements', []):
            declared = originals.get(role['role'], {})
            owner = role.get('state') == 'user_input'
            accepted = role.get('accepted') is True
            roles.append({
                'role': role['role'], 'state': role.get('state', 'not_checked'),
                'description': declared.get('description') or role.get('description') or role['role'].replace('_', ' '),
                'accepted': accepted,
                'supplemental': declared.get('requirement_class') == 'supplemental',
                'owner_input_required': owner and not accepted,
                'series_ids': list(role.get('series_ids') or []),
                'sources_with_observations': role.get('sources_with_observations') or 0,
                'blocking_checks': list(role.get('blocking_checks') or []),
                'limitations': grouped(role.get('limitations') or []),
            })
        for role in definition.get('descoped_roles', []):
            if any(r['role'] == role['role'] for r in roles):
                continue
            roles.append({'role': role['role'], 'state': 'descoped', 'accepted': False,
                          'supplemental': False,
                          'description': role.get('reason') or role['role'].replace('_', ' '),
                          'owner_input_required': False, 'series_ids': [],
                          'sources_with_observations': 0,
                          'blocking_checks': [], 'limitations': []})
        phase2 = analysis_phase2(snapshot, aid)
        questions.append({**row, 'phase2': phase2,
                          'role_dispositions': roles,
                          'next_step': evidence_next_step(
                              aid, phase2['state'], roles, phase2['open_gates'])})
    # The same evaluated response powers both the question catalogue and
    # its follow-up network. Partial test/research subsets retain their
    # established behavior without fabricating edges to missing questions.
    from .question_graph import load_question_links, question_graph
    approved = load_question_links()
    linked_ids = {id for edge in approved['links']
                  for id in (edge['parent'], edge['child'])}
    graph = question_graph(document, questions, approved) if set(definitions) == linked_ids else None
    return {'evaluated_at': snapshot.evaluated_at.isoformat(),
            'counts': dict(Counter(row['state'] for row in questions)),
            'questions': questions, 'question_graph': graph}
