"""Check an English synthetic ticket and free model-input preview; no model calls."""
import json
import httpx


def main():
    with httpx.Client(base_url='http://127.0.0.1:8767', timeout=15) as client:
        health = client.get('/health')
        health.raise_for_status()
        assert not health.json()['model_calls_enabled']
        page = client.get('/')
        page.raise_for_status()
        assert 'Find evidence, review a reply' in page.text
        assert "localStorage.getItem('supportdesk-ui-language')||'en'" in page.text
        response = client.post('/tickets', json={
            'question': 'Can I put my secret key in frontend environment variables?',
            'synthetic': True, 'retrieval': 'keyword'})
        response.raise_for_status()
        ticket = response.json()
        assert len(ticket['citations']) == 3
        assert any('A secret key bypasses RLS only when' in c['context']['text'] for c in ticket['citations'])
        plan = client.get('/tickets/' + ticket['ticket_id'] + '/model-input?language=en')
        plan.raise_for_status()
        data = plan.json()
        assert not data['model_called']
        assert 'Prepare a support reply draft in English' in data['request_body']['instructions']
        print(json.dumps({'ticket_id': ticket['ticket_id'], 'english_ui_default': True,
                          'english_prompt': True, 'token_condition_found': True,
                          'model_called': False}))


if __name__ == '__main__':
    main()
