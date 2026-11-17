"""Bounded outbound relay. A provider dispatch is never automatically replayed."""
import base64
import json

import httpx

from .config import validate_local


def bounded(client, method, url, limit=500_000, **kwargs):
    with client.stream(method, url, **kwargs) as response:
        response.raise_for_status()
        data = bytearray()
        for chunk in response.iter_bytes():
            data.extend(chunk)
            if len(data) > limit:
                raise ValueError('Provider response exceeds the supported size.')
        return json.loads(data)


def dispatch(client, local, key, request):
    local = validate_local(local)
    auth = {'Authorization': 'Bearer ' + key} if key else {}
    operation = request['operation']
    if operation == 'models':
        return bounded(client, 'GET', local + '/models', headers=auth)
    body = dict(request.get('payload', {}))
    if operation == 'completion':
        body['stream'] = False
        return bounded(client, 'POST', local + '/chat/completions', json=body, headers=auth)
    if operation not in ('image_generation', 'image_edit'):
        raise ValueError('Unsupported relay operation.')
    references = body.pop('references', [])
    body = {k: v for k, v in body.items() if k in ('model', 'prompt', 'n', 'size', 'response_format')}
    body.update(n=1, size='1024x1024', response_format='b64_json')
    if len(body.get('prompt', '')) > 24000 or len(references) > 4:
        raise ValueError('Image request exceeds supported limits.')
    if operation == 'image_generation':
        return bounded(client, 'POST', local + '/images/generations', limit=16_000_000, json=body, headers=auth)
    if not references:
        raise ValueError('An image reference is required.')
    files = []
    for index, reference in enumerate(references):
        if not reference.startswith(('data:image/png;base64,', 'data:image/jpeg;base64,', 'data:image/webp;base64,')) or len(reference) > 7_000_000:
            raise ValueError('Unsupported image reference.')
        mime, encoded = reference.split(';base64,', 1)
        files.append(('image[]', (f'reference-{index}', base64.b64decode(encoded, validate=True), mime[5:])))
    return bounded(client, 'POST', local + '/images/edits', limit=16_000_000, data={k: str(v) for k, v in body.items()}, files=files, headers=auth)


def relay_once(client, store):
    token = store.credential('bridge-token')
    base = store.data['vespera_url'].rstrip('/') + '/api/provider-bridges'
    headers = {'Authorization': 'Bearer ' + token}
    response = client.get(base + '/poll', headers=headers)
    response.raise_for_status()
    item = response.json()
    if not item.get('id'):
        return False
    try:
        result = dispatch(client, store.data['local_url'], store.credential('proxy-key'), item['request'])
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        result = {'error': 'local_provider_failed'}
    # A lost receipt is left uncertain. Neither dispatch nor receipt is retried.
    client.post(base + '/requests/' + item['id'], headers=headers, json={'result': result}).raise_for_status()
    return True
