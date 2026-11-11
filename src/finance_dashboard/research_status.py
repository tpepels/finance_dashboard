"""Read-only research navigation derived from the canonical acceptance snapshot."""
from __future__ import annotations

from collections import Counter

from .engine.acceptance import analysis_phase2, grouped
from .engine.runner import list_analyses


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
                'owner_input_required': owner and not accepted,
                'series_ids': list(role.get('series_ids') or []),
                'limitations': grouped(role.get('limitations') or []),
            })
        for role in definition.get('descoped_roles', []):
            if any(r['role'] == role['role'] for r in roles):
                continue
            roles.append({'role': role['role'], 'state': 'descoped', 'accepted': False,
                          'description': role.get('reason') or role['role'].replace('_', ' '),
                          'owner_input_required': False, 'series_ids': [], 'limitations': []})
        questions.append({**row, 'phase2': analysis_phase2(snapshot, aid),
                          'role_dispositions': roles})
    return {'evaluated_at': snapshot.evaluated_at.isoformat(),
            'counts': dict(Counter(row['state'] for row in questions)), 'questions': questions}
