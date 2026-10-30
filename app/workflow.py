"""Reusable saved-ticket generation; web and CLI share source verification."""
from app import database
from pathlib import Path

from app.baseline import segments_for, verified_sources
from app.evidence_context import with_context
from app.model_gateway import ModelError, generate_draft, load_settings, preview


def ticket_inputs(ticket_id):
    try:
        sources = verified_sources()
        partials = {Path(source['local_file']).name: source for source in sources[5:]}
        verified = [segment for source in sources[:5] for segment in segments_for(source, partials)]
    except ValueError as error:
        raise ModelError('source_changed', 'Source snapshot verification failed; generation has been stopped.') from error
    trusted = {segment['segment_id']: segment for segment in verified}
    record = database.read_ticket(ticket_id)
    if record is None or not record['runs']:
        raise ModelError('ticket_missing', 'The ticket or its retrieval record was not found.')
    if not record['ticket']['synthetic']:
        raise ModelError('scope', 'Model generation is limited to synthetic tickets in this demo.')
    citations = record['runs'][0]['result']['citations'][:3]
    current = {entry['segment_id']: entry for entry in database.current_segments()}
    clean_citations = []
    for citation in citations:
        identifier = citation.get('segment_id')
        source = trusted.get(identifier)
        stored = current.get(identifier)
        if (source is None or stored != source or
                any(citation.get(name) != value for name, value in source.items())):
            raise ModelError('source_changed', 'Saved evidence differs from the verified source; generation has been stopped.')
        # Preserve retrieval metadata, but take source content and links from the verified file.
        clean_citations.append({**source, **{key: citation[key] for key in
            ('score', 'matched_terms', 'included_by', 'selection_reason') if key in citation}})
    return record['ticket']['question'], with_context(clean_citations, verified)


def preview_ticket(ticket_id, profile='openai_luna', language='en'):
    question, citations = ticket_inputs(ticket_id)
    return preview(question, citations, load_settings(profile=profile, output_language=language))


def generate_ticket(ticket_id, profile='openai_luna', language='en'):
    question, citations = ticket_inputs(ticket_id)
    generation = generate_draft(question, citations,
        load_settings(profile=profile, output_language=language),
        database.reserve_model_call, database.finish_model_call)
    if not generation['model_called']:
        return generation
    generation['retrieval_method'] = database.read_ticket(ticket_id)['runs'][0]['method']
    saved = database.save_generated_run(ticket_id, question, generation)
    return saved
