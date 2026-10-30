"""Attach bounded, traceable section context without changing retrieval identities."""
from collections import defaultdict


def with_context(citations, segments, max_chars=4000):
    """Keep ranked excerpts intact; add only verified neighbouring source segments.

    Do not cross a section, snapshot, parent document or partial-file boundary.
    A long section is expanded around the hit without truncating prose/code.
    """
    if max_chars < 1:
        raise ValueError('Context limit must be positive')
    groups = defaultdict(list)
    for segment in segments:
        key = tuple(segment.get(field) for field in
                    ('document_id', 'source_id', 'sha256', 'local_file'))
        groups[key].append(segment)
    by_id = {}
    for group in groups.values():
        group.sort(key=lambda s: (s['line_start'], s['line_end']))
        block = []
        for segment in group:
            if block and segment['section'] != block[-1]['section']:
                block = []
            block.append(segment)
            by_id[segment['segment_id']] = (block, len(block) - 1)
    output = []
    for citation in citations:
        location = by_id.get(citation['segment_id'])
        if location is None:
            raise ValueError('Citation is outside the verified source segments')
        block, index = location
        source = block[index]
        if any(citation.get(field) != source.get(field) for field in
               ('text', 'source_id', 'sha256', 'document_id', 'local_file', 'section', 'line_start', 'line_end')):
            raise ValueError('Citation differs from its verified source segment')
        left = right = index
        used = len(source['text'])
        # Alternate before/after; never skip a nearby paragraph to fit a distant one.
        before_open = after_open = True
        while before_open or after_open:
            if before_open:
                if left > 0 and used + 2 + len(block[left - 1]['text']) <= max_chars:
                    left -= 1
                    used += 2 + len(block[left]['text'])
                else:
                    before_open = False
            if after_open:
                if right + 1 < len(block) and used + 2 + len(block[right + 1]['text']) <= max_chars:
                    right += 1
                    used += 2 + len(block[right]['text'])
                else:
                    after_open = False
        chosen = block[left:right + 1]
        context = {'text': '\n\n'.join(s['text'] for s in chosen),
                   'line_start': chosen[0]['line_start'], 'line_end': chosen[-1]['line_end'],
                   'segments': [{field: s[field] for field in
                                 ('segment_id', 'source_id', 'sha256', 'local_file', 'line_start', 'line_end')}
                                for s in chosen],
                   'policy': 'same-section-neighbours-v1'}
        output.append({**citation, 'context': context})
    return output
