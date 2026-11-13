"""Offline integration checks using real ripgrep and mocked curl/Dolphin.

All fixtures are synthetic and removed on completion. No real API calls are made.
"""
import json
import os
from pathlib import Path
import pty
import select
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

BINARY = str(Path(sys.argv.pop(1)).resolve())
MOCK_CURL = r'''
import json, os, sys
from pathlib import Path
config = {}
for line in sys.stdin.read().splitlines():
    key, value = line.split(' = ', 1)
    config.setdefault(key, []).append(json.loads(value))
assert config['url'] == ['https://example.invalid/chat/completions']
assert 'api-key: synthetic-secret' in config['header']
assert 'synthetic-secret' not in ' '.join(sys.argv)
request = json.loads(config['data-binary'][0])
assert request['model'] == 'gpt-6-astra'
mode = os.environ.get('TEST_MODE', '')
Path(os.environ['MOCK_CALLED']).write_text('called')
if mode == 'http':
    print('{"error":"synthetic-secret"}\n401', end=''); sys.exit(0)
if request['messages'][0]['content'] == 'Reply with exactly OK.':
    content = 'OK'
else:
    context = json.loads(request['messages'][1]['content'])
    candidates = context['candidates']
    assert len(candidates) <= int(os.environ.get('EXPECTED_CANDIDATES', '20'))
    assert all(len(c['excerpts'].encode()) <= 3000 for c in candidates)
    results = []
    for c in candidates:
        folder = c['folder']
        date = '2026-10-22' if 'Recent' in folder else '2025-09-14'
        results.append(dict(id=c['id'], customer=Path(folder).name, date=date,
                            date_evidence=date, subject='Vector Search Workshop',
                            relevance=2 if 'Peripheral' in folder else 3))
    if mode == 'bad-id': results[0]['id'] = 99999
    if mode == 'duplicate': results.append(results[0])
    if mode == 'bad-date': results[0]['date'] = '2026-02-30'
    if mode == 'no-evidence': results[0]['date_evidence'] = 'not supplied anywhere'
    if mode == 'wrong-evidence': results[0]['date_evidence'] = 'Vector Search'
    if mode == 'named-date':
        results[0]['date'] = '2026-10-22'; results[0]['date_evidence'] = 'October 22, 2026'
    if mode == 'empty': results = []
    content = json.dumps(dict(results=results))
    if mode == 'malformed': content = 'not JSON'
reply = dict(choices=[dict(finish_reason='length' if mode == 'length' else 'stop', message=dict(content=content))])
print(json.dumps(reply) + '\n200', end='')
'''


class Integration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='session-search-test-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'Notes with spaces'
        self.root.mkdir()
        self.bin = self.base / 'bin'
        self.bin.mkdir()
        curl = self.bin / 'curl'
        curl.write_text('#!' + sys.executable + '\n' + MOCK_CURL)
        curl.chmod(0o755)
        dolphin = self.bin / 'dolphin'
        dolphin.write_text('#!' + sys.executable + '\nimport json, os, sys\nfrom pathlib import Path\nPath(os.environ["MOCK_OPENED"]).write_text(json.dumps(sys.argv[1:]))\n')
        dolphin.chmod(0o755)
        self.env = os.environ.copy()
        for key in ('LLM_API_KEY', 'LLM_BASE_URL', 'LLM_MODEL', 'SEARCH_ROOT'):
            self.env.pop(key, None)
        self.env.update(PATH=str(self.bin) + os.pathsep + os.environ['PATH'],
                        MOCK_CALLED=str(self.base / 'called'), MOCK_OPENED=str(self.base / 'opened'))
        self.config = self.base / 'settings.env'
        self.config.write_text('export LLM_API_KEY="synthetic-secret" # comment\n'
                               'LLM_BASE_URL=https://example.invalid/chat/completions\n'
                               'LLM_MODEL=gpt-6-astra\nSEARCH_ROOT="' + str(self.root) + '"\n')
        self.note('Old', 'Customer: Old\nDelivered: 2025-09-14\nSubject: Vector Search Workshop\n')
        self.note('Recent', 'Customer: Recent\nDelivered: 2026-10-22\nSubject: Vector Search Workshop\n')
        self.note('Peripheral', 'Delivered: 2026-10-22\nVector Search was a brief part of another workshop.\n')

    def note(self, folder, content, name='notes.txt'):
        p = self.root / folder
        p.mkdir(exist_ok=True)
        (p / name).write_text(content)
        return p

    def run_app(self, *args, mode='', success=True):
        env = dict(self.env, TEST_MODE=mode)
        result = subprocess.run([BINARY, '--env', str(self.config), '--no-open', *args],
                                env=env, cwd=self.base, text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        self.assertNotIn('synthetic-secret', result.stdout + result.stderr)
        return result

    def test_ranking_and_folder_deduplication(self):
        self.note('Recent', 'Vector Search Workshop\nDelivered: 2026-10-22\n', 'duplicate.txt')
        result = self.run_app('vector search')
        self.assertIn('1. Recent | 2026-10-22', result.stdout)
        self.assertIn('2. Old | 2025-09-14', result.stdout)
        self.assertIn('3. Peripheral', result.stdout)
        self.assertEqual(result.stdout.count(str(self.root / 'Recent')), 1)
        self.assertNotIn('Open result', result.stdout)

    def test_no_matches_skip_api(self):
        result = self.run_app('absent-topic')
        self.assertIn('No local matches', result.stdout)
        self.assertFalse((self.base / 'called').exists())

    def test_empty_verified_results(self):
        self.assertIn('No relevant sessions', self.run_app('Vector Search', mode='empty').stdout)

    def test_local_only_needs_no_credentials(self):
        self.config.write_text('SEARCH_ROOT="' + str(self.root) + '"\n')
        result = self.run_app('--local-only', 'Vector Search')
        self.assertIn('unverified', result.stderr)
        self.assertIn('Unknown', result.stdout)
        self.assertFalse((self.base / 'called').exists())

    def test_invalid_model_output_fails_closed(self):
        for mode in ('bad-id', 'duplicate', 'malformed', 'length'):
            with self.subTest(mode=mode):
                result = self.run_app('Vector Search', mode=mode, success=False)
                self.assertNotIn('1. ', result.stdout)

    def test_unsupported_dates_are_unknown(self):
        for mode in ('bad-date', 'no-evidence', 'wrong-evidence'):
            with self.subTest(mode=mode):
                result = self.run_app('--candidates', '1', 'Vector Search', mode=mode)
                self.assertIn('| Unknown |', result.stdout)

    def test_named_date(self):
        self.note('Recent', 'Vector Search\nDelivered October 22, 2026\n')
        result = self.run_app('--root', str(self.root / 'Recent'), 'Vector Search', mode='named-date')
        self.assertIn('| 2026-10-22 |', result.stdout)

    def test_candidate_and_excerpt_limits(self):
        self.env['EXPECTED_CANDIDATES'] = '1'
        self.note('Large', ('Vector Search ' + 'x' * 500 + '\n') * 80)
        result = self.run_app('--candidates', '1', '--limit', '1', 'Vector Search')
        self.assertIn('top 1 matching folders', result.stderr)
        self.assertEqual(result.stdout.count('\n   '), 1)

    def test_http_error_hides_response_and_credentials(self):
        result = self.run_app('Vector Search', mode='http', success=False)
        self.assertIn('HTTP 401', result.stderr)

    def test_connection_check_sends_no_notes(self):
        self.assertIn('connection successful', self.run_app('--check-connection').stdout)

    def test_root_override_and_symlink_exclusion(self):
        outside = self.base / 'outside'
        outside.mkdir()
        (outside / 'notes.txt').write_text('Vector Search private outside root')
        (self.root / 'link').symlink_to(outside, target_is_directory=True)
        result = self.run_app('--root', str(self.root / 'Old'), 'Vector Search')
        self.assertIn('1. Old', result.stdout)
        self.assertNotIn('Recent', result.stdout)
        self.assertNotIn('outside', self.run_app('--local-only', 'private outside root').stdout)

    def test_literal_queries_and_paths_are_not_shell_commands(self):
        folder = self.note("Customer $(touch PWNED); 'quoted'", '$(touch PWNED)\n')
        result = self.run_app('--local-only', '--root', str(folder), '--', '$(touch PWNED)')
        self.assertIn(str(folder), result.stdout)
        self.assertFalse((self.base / 'PWNED').exists())

    def test_environment_overrides_dotenv(self):
        self.env['SEARCH_ROOT'] = str(self.root / 'Old')
        self.assertNotIn('Recent', self.run_app('Vector Search').stdout)

    def test_invalid_cli_and_missing_configuration(self):
        for args in ((), ('--limit', '0', 'topic'), ('--candidates', '41', 'topic'), ('--context', 'bad', 'topic'), ('--bogus',)):
            with self.subTest(args=args):
                self.run_app(*args, success=False)
        self.env['LLM_API_KEY'] = ''
        self.assertIn('Missing LLM_API_KEY', self.run_app('Vector Search', success=False).stderr)

    def test_no_cache_or_note_changes(self):
        before = {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.run_app('Vector Search')
        after = {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(set(p.name for p in self.base.iterdir()), {'Notes with spaces', 'bin', 'settings.env', 'called'})

    def test_noninteractive_input_never_prompts(self):
        result = subprocess.run([BINARY, '--env', str(self.config), 'Vector Search'],
                                env=self.env, cwd=self.base, text=True, input='', capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('Open result', result.stdout)
        self.assertFalse((self.base / 'opened').exists())

    def test_utf8_excerpt_boundaries(self):
        self.note('Unicode', 'Vector Search ' + 'é' * 900 + '\nDelivered: 2025-09-14\n')
        self.run_app('--root', str(self.root / 'Unicode'), 'Vector Search')

    def test_search_output_limit_is_explicit(self):
        for index in range(16):
            self.note('Volume', ('Vector Search ' + 'x' * 100000 + '\n') * 12, str(index) + '.txt')
        result = self.run_app('--local-only', 'Vector Search')
        self.assertIn('Search output limit reached', result.stderr)
        self.assertIn('1. ', result.stdout)

    def interact(self, answer):
        master, slave = pty.openpty()
        self.addCleanup(os.close, master)
        p = subprocess.Popen([BINARY, '--env', str(self.config), 'Vector Search'],
                             env=self.env, cwd=self.base, stdin=slave, stdout=slave, stderr=slave)
        os.close(slave)
        self.addCleanup(lambda: p.kill() if p.poll() is None else None)
        output = b''
        deadline = time.monotonic() + 10
        while b'Open result [1], or q to quit:' not in output and time.monotonic() < deadline:
            if select.select([master], [], [], .1)[0]:
                try: output += os.read(master, 8192)
                except OSError: break
        self.assertIn(b'Open result [1], or q to quit:', output)
        os.write(master, answer)
        self.assertEqual(p.wait(timeout=5), 0)
        opened = self.base / 'opened'
        if answer != b'q\n':
            deadline = time.monotonic() + 3
            while not opened.exists() and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue(opened.exists())
            return json.loads(opened.read_text())
        self.assertFalse(opened.exists())

    def test_dolphin_default_is_first_result(self):
        self.assertEqual(self.interact(b'\n'), ['--', str(self.root / 'Recent')])

    def test_dolphin_selection_and_invalid_input(self):
        self.assertEqual(self.interact(b'999\n2\n'), ['--', str(self.root / 'Old')])

    def test_dolphin_quit(self):
        self.interact(b'q\n')


if __name__ == '__main__':
    unittest.main()
