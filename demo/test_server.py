import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import http.client
import threading
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('demo_server', Path(__file__).with_name('server.py'))
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class ConsoleBoundaryTests(unittest.TestCase):
    def test_malformed_reports_are_skipped_without_breaking_the_list(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = {'schema_version':1,'mode':'LOCAL_HTTP_MOCK','implementation':'python',
                        'target':{'provider':'azure_openai'},'scenario':'burst',
                        'started_at_utc':'2026-09-10T00:00:00Z','request_count':6,
                        'output_limit':128,'concurrency':3}
            cases = [([], {}, {}), (manifest, [], {}), (manifest, {}, []),
                     ({**manifest, 'request_count':0}, {}, {}), (manifest, {}, {})]
            for index, (data, summary, attempt) in enumerate(cases):
                folder = root / 'python' / 'runs' / str(index)
                folder.mkdir(parents=True)
                (folder/'manifest.json').write_text(json.dumps(data))
                (folder/'summary.json').write_text(json.dumps(summary))
                (folder/'attempts.jsonl').write_text(json.dumps(attempt))
            with patch.object(server, 'ROOT', root):
                result = server.runs()
            self.assertEqual(result['skipped'], 4)
            self.assertEqual(len(result['runs']), 1)

    def test_cannot_request_live_or_inject_cli_arguments(self):
        for data in ({'runtime':'python','target':'aoai','scenario':'burst','live':True},
                     {'runtime':'python','target':'aoai; exit','scenario':'burst'},
                     {'runtime':'bash','target':'aoai','scenario':'burst'}):
            with self.assertRaises(ValueError):
                server.command(data)
        for runtime in ('python', 'dotnet'):
            args = server.command({'runtime':runtime,'target':'mai','scenario':'retry'})
            self.assertNotIn('--live', args)
            self.assertIn(str(server.ROOT / runtime / 'config.example.json'), args)
            self.assertNotIn('config.local.json', ' '.join(args))

    def test_evidence_projection_excludes_private_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            manifest = {'schema_version':1,'mode':'LIVE_AZURE','implementation':'python',
                        'target':{'provider':'azure_openai','endpoint':'PRIVATE_ENDPOINT','deployment':'PRIVATE_DEPLOYMENT'},
                        'scenario':'burst','started_at_utc':'2026-09-10T00:00:00Z','request_count':1,
                        'output_limit':128,'concurrency':1,'prompt':'PRIVATE_PROMPT'}
            (folder/'manifest.json').write_text(json.dumps(manifest))
            (folder/'summary.json').write_text('{}')
            (folder/'attempts.jsonl').write_text(json.dumps({'job':1,'status':200,'headers':{'Authorization':'PRIVATE_TOKEN'},'content':'PRIVATE_RESPONSE'}))
            result = json.dumps(server.project_run(folder))
            self.assertNotIn('PRIVATE_', result)
            self.assertNotIn(temp.replace('\\','\\\\'), result)
            first = server.project_run(folder)
            manifest['output_limit'] = 2048
            (folder/'manifest.json').write_text(json.dumps(manifest))
            self.assertNotEqual(first['signature'], server.project_run(folder)['signature'])

    def test_http_rejects_other_origins_and_source_file_paths(self):
        httpd = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            client = http.client.HTTPConnection('127.0.0.1', httpd.server_port)
            client.request('GET', '/api/runs', headers={'Host':'attacker.example'})
            response = client.getresponse()
            self.assertEqual(response.status, 403)
            response.read()
            client.request('GET', '/python/config.local.json')
            response = client.getresponse()
            self.assertEqual(response.status, 404)
            response.read()
            client.request('POST', '/api/run', '{}', headers={'Content-Type':'application/json','Origin':'https://attacker.example'})
            response = client.getresponse()
            self.assertEqual(response.status, 403)
            response.read()
            client.close()
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
