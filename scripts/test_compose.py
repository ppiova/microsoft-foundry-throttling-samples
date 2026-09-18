"""Exercise both engines through an already running local Compose service."""
import json
import subprocess
import urllib.error
import urllib.request

origin = 'http://127.0.0.1:8765'


def request(path, payload=None, headers=None):
    req = urllib.request.Request(origin + path,
        data=json.dumps(payload).encode() if payload else None,
        headers=headers or {})
    with urllib.request.urlopen(req, timeout=190) as response:
        return response.read()


assert b'id="slide-14"' in request('/slides')
for path in ('/presenter', '/speaker-notes.json'):
    try:
        request(path)
        raise AssertionError(f'Unexpected public route: {path}')
    except urllib.error.HTTPError as error:
        assert error.code == 404
try:
    request('/api/run', {'runtime': 'python', 'target': 'aoai', 'scenario': 'retry'},
            {'Content-Type': 'application/json', 'Origin': 'https://untrusted.example'})
    raise AssertionError('Cross-origin simulation accepted')
except urllib.error.HTTPError as error:
    assert error.code == 403

created = set()
for runtime in ('python', 'dotnet'):
    before = {run['id'] for run in json.loads(request('/api/runs'))['runs']}
    result = json.loads(request('/api/run',
        {'runtime': runtime, 'target': 'aoai', 'scenario': 'retry'},
        {'Content-Type': 'application/json', 'Origin': origin}))
    added = [run for run in result['runs'] if run['id'] not in before]
    assert len(added) == 1 and added[0]['runtime'] == runtime
    assert added[0]['mode'] == 'LOCAL_HTTP_MOCK'
    assert added[0]['summary']['completed_responses'] == 6
    created.add(added[0]['id'])
    print(f'{runtime}: six requests completed through the container UI API')

subprocess.run(['docker', 'compose', 'up', '-d', '--force-recreate', '--wait'], check=True)
after = {run['id'] for run in json.loads(request('/api/runs'))['runs']}
assert created <= after
print('Evidence persisted across container recreation; origin and private-route checks passed.')
