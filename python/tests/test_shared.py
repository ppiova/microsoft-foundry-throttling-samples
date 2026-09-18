import contextlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters import response_info
from credentials import RenewableToken, AuthenticationError
from lab import retry_delay, main


class SharedContracts(unittest.TestCase):
    def test_shared_protocol_fixtures(self):
        cases = json.loads((Path(__file__).resolve().parents[2] / 'scenarios/protocol-cases.json').read_text())
        for case in cases['responses']:
            result = response_info(case['provider'], case['status'], case['body'])
            self.assertEqual(result['outcome'], case['outcome'])
            self.assertNotIn('never export', json.dumps(result))
        with patch('lab.time.time', return_value=0), patch('lab.random.random', return_value=.5):
            for case in cases['retries']:
                self.assertEqual(retry_delay(case['headers'], case['attempt']), case['expected'])

    def test_renewal_is_cached_atomic_and_secret_safe(self):
        now = [0]
        class Fake:
            calls = 0
            def get_token(self, scope):
                self.calls += 1
                return SimpleNamespace(token='secret-' + str(self.calls), expires_on=now[0] + 3600)
            def close(self): pass
        fake = Fake()
        provider = RenewableToken(fake, 'scope', lambda: now[0])
        threads = [threading.Thread(target=provider) for _ in range(20)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(fake.calls, 1)
        now[0] = 3500
        self.assertEqual(provider(), 'secret-2')
        with patch.object(fake, 'get_token', side_effect=RuntimeError('secret-error')):
            now[0] = 7000
            with self.assertRaises(AuthenticationError) as error: provider()
            self.assertNotIn('secret', str(error.exception))

    def test_all_scenarios_emit_versioned_evidence(self):
        config = str(Path(__file__).resolve().parents[1] / 'config.example.json')
        for target, scenario, extra in [
            ('aoai', 'preflight', []), ('aoai', 'baseline', []), ('aoai', 'burst', []),
            ('aoai', 'retry', []), ('aoai', 'paced', []),
            ('aoai', 'guarded', ['--client-token-budget', '512', '--mock-axis', 'tpm']),
            ('claude', 'guarded', ['--client-output-budget', '256', '--mock-axis', 'otpm']),
            ('mai', 'preflight', []), ('image', 'paced', []),
            ('aoai', 'retry', ['--mock-axis', 'capacity'])]:
            with self.subTest(target=target, scenario=scenario), tempfile.TemporaryDirectory() as tmp:
                argv = ['lab.py', 'run', '--config', config, '--target', target, '--scenario', scenario,
                        '--requests', '3', '--mock-window', '.1', '--client-rpm', '1200', '--out', tmp] + extra
                with patch('sys.argv', argv), contextlib.redirect_stdout(io.StringIO()): main()
                path = next(Path(tmp).iterdir())
                manifest = json.loads((path / 'manifest.json').read_text())
                jobs = json.loads((path / 'jobs.json').read_text())
                attempts = [json.loads(line) for line in (path / 'attempts.jsonl').read_text().splitlines()]
                summary = json.loads((path / 'summary.json').read_text())
                self.assertEqual(manifest['schema_version'], 1)
                self.assertEqual(manifest['implementation'], 'python')
                self.assertTrue(manifest['ended_at_utc'])
                self.assertEqual(summary['http_attempts'], len(attempts))
                self.assertEqual(sum(j['attempts'] for j in jobs), len(attempts))
                self.assertLessEqual(len(attempts), manifest['attempt_budget'])

    def test_nonfinite_rate_rejected_before_network(self):
        config = str(Path(__file__).resolve().parents[1] / 'config.example.json')
        for value in ('nan', 'inf'):
            with patch('sys.argv', ['lab.py','run','--config',config,'--client-rpm',value]), patch('lab.start_mock') as mock:
                with self.assertRaises(ValueError): main()
                mock.assert_not_called()
