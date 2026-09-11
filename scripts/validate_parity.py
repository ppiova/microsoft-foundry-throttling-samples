"""Maintainer-only cross-runtime check. End-user paths remain independent."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]


def execute(command, cwd):
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout


def main():
    execute(['dotnet', 'build', 'dotnet/FoundryLab', '-c', 'Release'], root)
    python = [sys.executable, '-B', str(root / 'python/lab.py')]
    dotnet = ['dotnet', str(root / 'dotnet/FoundryLab/bin/Release/net10.0/FoundryLab.dll')]
    required = json.loads((root / 'scenarios/manifest.schema.json').read_text())['required']
    with tempfile.TemporaryDirectory(prefix='foundry-parity-') as tmp:
        paths = []
        for command in (python, dotnet):
            for scenario in ('burst', 'retry', 'paced'):
                stdout = execute(command + ['run', '--config', str(root / 'python/config.example.json'),
                    '--scenario', scenario, '--out', tmp], root)
                path = Path(next(line[8:] for line in stdout.splitlines() if line.startswith('RESULTS=')))
                manifest = json.loads((path / 'manifest.json').read_text())
                assert all(key in manifest for key in required)
                assert manifest['ended_at_utc'] and manifest['mode'] == 'LOCAL_HTTP_MOCK'
                paths.append(path)
        # Each comparer consumes all six runs, including the other runtime's output.
        for index, command in enumerate((python, dotnet)):
            execute(command + ['compare'] + list(map(str, paths)) + ['--out', str(Path(tmp) / f'comparison-{index}.md')], root)
        manifests = [json.loads((p / 'manifest.json').read_text()) for p in paths]
        assert len({m['prompt_sha256'] for m in manifests}) == 1
        for path in paths:
            m = json.loads((path / 'manifest.json').read_text())
            s = json.loads((path / 'summary.json').read_text())
            print(m['implementation'], m['scenario'], 'complete=', s['completed_responses'], 'attempts=', s['http_attempts'], '429=', s['http_429'])
    print('Both CLIs produced compatible evidence and accepted cross-runtime comparisons.')


if __name__ == '__main__':
    main()
