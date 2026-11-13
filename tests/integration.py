"""Offline integration checks using real ripgrep and mocked curl/Dolphin.

All fixtures are synthetic and removed on completion. No real API calls are made.
"""
import datetime
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
import datetime, json, os, sys
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
    assert context['as_of_date'] == datetime.date.today().isoformat()
    candidates = context['candidates']
    assert len(candidates) <= int(os.environ.get('EXPECTED_CANDIDATES', '20'))
    assert all(len(c['excerpts'].encode()) <= 3000 for c in candidates)
    results = []
    for c in candidates:
        folder = c['folder']
        date = '2026-10-22' if Path(folder).name in ('Recent', 'Related') else '2025-09-14'
        results.append(dict(id=c['id'], customer=Path(folder).name, date=date,
                            date_evidence=date, subject='Vector Search Workshop',
                            relevance=2 if 'Related' in folder else 3))
    for result in results:
        result.update(json.loads(os.environ.get('TEST_RESULTS', '{}')).get(result['customer'], {}))
    if mode == 'reverse': results.reverse()
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
        self.env.update(TZ='UTC', PATH=str(self.bin) + os.pathsep + os.environ['PATH'],
                        HOME=str(self.base / 'home'), XDG_CONFIG_HOME=str(self.base / 'xdg'),
                        MOCK_CALLED=str(self.base / 'called'), MOCK_OPENED=str(self.base / 'opened'))
        self.config = self.base / 'settings.env'
        self.config.write_text('export LLM_API_KEY="synthetic-secret" # comment\n'
                               'LLM_BASE_URL=https://example.invalid/chat/completions\n'
                               'LLM_MODEL=gpt-6-astra\nSEARCH_ROOT="' + str(self.root) + '"\n')
        self.config.chmod(0o600)
        self.note('Old', 'Customer: Old\nDelivered: 2025-09-14\nSubject: Vector Search Workshop\n')
        self.note('Recent', 'Customer: Recent\nDelivered: 2026-10-22\nSubject: Vector Search Workshop\n')
        self.note('Related', 'Delivered: 2026-10-22\nSubstantially related Vector Search session materials.\n')

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
        self.assertIn('2. Related | 2026-10-22', result.stdout)
        self.assertIn('3. Old | 2025-09-14', result.stdout)
        self.assertEqual(result.stdout.count(str(self.root / 'Recent')), 1)
        self.assertNotIn('Open result', result.stdout)

    def ranking_fixture(self, sessions):
        for folder in self.root.iterdir():
            shutil.rmtree(folder)
        overrides = {}
        for name, date, relevance, hits in sessions:
            self.note(name, 'Customer: ' + name + '\nDelivered: ' + date + '\n' +
                      ''.join('Vector Search exercise ' + str(i) + '\n' for i in range(hits)))
            overrides[name] = dict(date=date, date_evidence='' if date == 'Unknown' else date,
                                   relevance=relevance)
        self.env['TEST_RESULTS'] = json.dumps(overrides)

    def ranked_customers(self, query='Vector Search', **kwargs):
        result = self.run_app(query, **kwargs)
        return [line.split('. ', 1)[1].split(' | ', 1)[0] for line in result.stdout.splitlines() if ' | ' in line]

    def coverage_fixture(self, claimed_text, reference_text, claimed_name='Claimed', filename='notes.txt', reference_rating=2):
        self.ranking_fixture([])
        self.note(claimed_name, 'Delivered: 2025-01-01\n' + claimed_text, filename)
        self.note('Reference', 'Delivered: 2025-01-01\n' + reference_text)
        self.env['TEST_RESULTS'] = json.dumps({
            claimed_name: dict(date='2025-01-01', date_evidence='2025-01-01', relevance=3),
            'Reference': dict(date='2025-01-01', date_evidence='2025-01-01', relevance=reference_rating)})

    def test_sparse_three_term_match_caps_direct_rating(self):
        self.coverage_fixture('alpha\n', 'alpha beta gamma\n')
        self.assertEqual(self.ranked_customers('alpha beta gamma'), ['Reference', 'Claimed'])

    def test_direct_coverage_rounds_up_for_odd_term_counts(self):
        for text, expected in (('alpha beta\n', ['Reference', 'Claimed']),
                               ('alpha beta gamma\n', ['Claimed', 'Reference'])):
            with self.subTest(text=text):
                self.coverage_fixture(text, 'alpha beta gamma delta epsilon\n')
                self.assertEqual(self.ranked_customers('alpha beta gamma delta epsilon'), expected)

    def test_half_or_full_coverage_preserves_direct_rating(self):
        for query, text in (('alpha beta gamma', 'alpha beta\n'),
                            ('alpha beta gamma delta', 'alpha beta\n'),
                            ('alpha beta gamma', 'alpha beta gamma\n')):
            with self.subTest(query=query, text=text):
                self.coverage_fixture(text, query + '\n' + query + '\n')
                self.assertEqual(self.ranked_customers(query), ['Claimed', 'Reference'])

    def test_duplicate_case_insensitive_query_terms_count_once(self):
        self.coverage_fixture('ALPHA BeTa\n', 'alpha beta gamma\n')
        self.assertEqual(self.ranked_customers('ALPHA alpha BETA beta gamma'), ['Claimed', 'Reference'])

    def test_single_term_present_in_excerpt_preserves_direct_rating(self):
        self.coverage_fixture('alpha\n', 'alpha exercise one\nalpha exercise two\n')
        self.assertEqual(self.ranked_customers('alpha'), ['Claimed', 'Reference'])

    def test_folder_names_do_not_justify_direct_rating(self):
        name = 'Claimed beta gamma'
        self.coverage_fixture('alpha one\nalpha two\nalpha three\nalpha four\n',
                              'alpha\nbeta\ngamma\n', claimed_name=name, reference_rating=3)
        self.assertEqual(self.ranked_customers('alpha beta gamma'), ['Reference', name])

    def test_filename_prefixes_do_not_justify_direct_rating(self):
        self.coverage_fixture('alpha\n', 'alpha beta gamma\n', filename='beta gamma.txt')
        self.assertEqual(self.ranked_customers('alpha beta gamma'), ['Reference', 'Claimed'])

    def test_lines_omitted_from_submitted_excerpt_do_not_count(self):
        self.coverage_fixture('alpha ' + 'x' * 1050 + '\nalpha ' + 'y' * 1050 + '\n' +
                              'beta gamma ' + 'z' * 1100 + '\n', 'alpha beta gamma\n')
        self.assertEqual(self.ranked_customers('alpha beta gamma'), ['Reference', 'Claimed'])

    def test_cap_preserves_peripheral_rating_and_does_not_drop_results(self):
        self.coverage_fixture('alpha\n', 'alpha beta gamma\n')
        overrides = json.loads(self.env['TEST_RESULTS'])
        overrides['Claimed']['relevance'] = 1
        self.env['TEST_RESULTS'] = json.dumps(overrides)
        self.assertEqual(self.ranked_customers('alpha beta gamma'), ['Reference', 'Claimed'])

    def test_capped_newer_session_still_qualifies_for_recency_ranking(self):
        self.coverage_fixture('alpha\nDelivered: 2025-02-01\n', 'alpha beta gamma\n', reference_rating=3)
        overrides = json.loads(self.env['TEST_RESULTS'])
        overrides['Claimed'].update(date='2025-02-01', date_evidence='2025-02-01')
        self.env['TEST_RESULTS'] = json.dumps(overrides)
        self.assertEqual(self.ranked_customers('alpha beta gamma'), ['Claimed', 'Reference'])

    def test_newer_substantial_session_beats_older_direct_session(self):
        self.ranking_fixture([('Direct', '2025-01-01', 3, 1), ('Substantial', '2025-02-01', 2, 1)])
        self.assertEqual(self.ranked_customers(), ['Substantial', 'Direct'])

    def test_peripheral_group_follows_all_on_topic_results(self):
        self.ranking_fixture([('Dated', '2025-01-01', 2, 1), ('Undated', 'Unknown', 3, 1),
                              ('PeripheralNew', '2025-03-01', 1, 1), ('PeripheralOld', '2025-02-01', 1, 1),
                              ('PeripheralUnknown', 'Unknown', 1, 1)])
        self.assertEqual(self.ranked_customers(), ['Dated', 'Undated', 'PeripheralNew', 'PeripheralOld', 'PeripheralUnknown'])

    def test_equal_dates_use_relevance_score_and_candidate_order(self):
        self.ranking_fixture([('DirectHigh', '2025-01-01', 3, 3), ('DirectLowZ', '2025-01-01', 3, 1),
                              ('DirectLowA', '2025-01-01', 3, 1), ('RelatedHigh', '2025-01-01', 2, 5)])
        expected = ['DirectHigh', 'DirectLowZ', 'DirectLowA', 'RelatedHigh']
        for mode in ('', 'reverse', 'reverse'):
            self.assertEqual(self.ranked_customers(mode=mode), expected)

    def test_future_delivery_is_excluded_today_is_accepted(self):
        today = datetime.datetime.now(datetime.timezone.utc).date()
        tomorrow = today + datetime.timedelta(days=1)
        self.ranking_fixture([('Future', tomorrow.isoformat(), 3, 1), ('Today', today.isoformat(), 2, 1),
                              ('Past', '2025-01-01', 3, 1)])
        self.assertEqual(self.ranked_customers(), ['Today', 'Past'])

    def test_all_future_sessions_produce_no_verified_results(self):
        future = datetime.datetime.now(datetime.timezone.utc).date() + datetime.timedelta(days=1)
        self.ranking_fixture([('FutureOnly', future.isoformat(), 3, 1)])
        self.assertIn('No relevant sessions', self.run_app('Vector Search').stdout)

    def test_future_cutoff_uses_system_timezone(self):
        for tz, offset in (('UTC-14', 14), ('UTC+12', -12)):
            with self.subTest(tz=tz):
                self.env['TZ'] = tz
                today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=offset))).date()
                self.ranking_fixture([('LocalToday', today.isoformat(), 3, 1),
                                      ('LocalTomorrow', (today + datetime.timedelta(days=1)).isoformat(), 3, 1)])
                self.assertEqual(self.ranked_customers(), ['LocalToday'])

    def test_invalid_and_unsupported_future_dates_remain_unknown(self):
        self.ranking_fixture([('Invalid', '2025-02-30', 3, 1), ('Unsupported', '9999-01-01', 3, 1),
                              ('Dated', '2025-01-01', 2, 1)])
        overrides = json.loads(self.env['TEST_RESULTS'])
        overrides['Unsupported']['date_evidence'] = 'never appeared in the notes'
        self.env['TEST_RESULTS'] = json.dumps(overrides)
        result = self.run_app('Vector Search')
        self.assertIn('1. Dated', result.stdout)
        self.assertIn('Invalid | Unknown |', result.stdout)
        self.assertIn('Unsupported | Unknown |', result.stdout)

    def test_result_limit_is_applied_after_new_ranking(self):
        self.ranking_fixture([('DirectOld', '2025-01-01', 3, 1), ('RelatedNew', '2025-02-01', 2, 1)])
        result = self.run_app('--limit', '1', 'Vector Search')
        self.assertIn('1. RelatedNew', result.stdout)
        self.assertNotIn('DirectOld', result.stdout)

    def test_no_matches_skip_api(self):
        result = self.run_app('absent-topic')
        self.assertIn('No local matches', result.stdout)
        self.assertFalse((self.base / 'called').exists())

    def test_model_notice_is_stderr_only_and_stdout_is_unchanged(self):
        result = self.run_app('--root', str(self.root / 'Recent'), 'Vector Search')
        self.assertEqual(result.stdout, '1. Recent | 2026-10-22 | Vector Search Workshop\n   ' +
                         str(self.root / 'Recent') + '\n\n')
        self.assertEqual(result.stderr, 'Model-generated results: check customer, date, and subject in the folder before relying on them.\n')

    def test_model_notice_absent_without_verified_results(self):
        for args, mode in ((('--local-only', 'Vector Search'), ''), (('absent-topic',), ''),
                           (('Vector Search',), 'empty'), (('--check-connection',), '')):
            with self.subTest(args=args, mode=mode):
                result = self.run_app(*args, mode=mode)
                self.assertNotIn('Model-generated results', result.stdout + result.stderr)

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

    def default_config(self, base):
        target = base / 'bfind' / '.env'
        target.parent.mkdir(parents=True)
        target.write_text(self.config.read_text())
        target.chmod(0o600)
        return target

    def run_default(self, *args, success=True):
        result = subprocess.run([BINARY, '--no-open', *args], env=self.env, cwd=self.base,
                                text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        self.assertNotIn('synthetic-secret', result.stdout + result.stderr)
        self.assertNotIn('attacker.invalid', result.stdout + result.stderr)
        return result

    def test_cwd_config_cannot_redirect_environment_key(self):
        (self.base / '.env').write_text('LLM_BASE_URL=https://attacker.invalid/steal\n'
                                       'SEARCH_ROOT=/untrusted/unrelated\n')
        self.env.update(LLM_API_KEY='synthetic-secret', LLM_MODEL='gpt-6-astra')
        result = self.run_default('--root', str(self.root), 'Vector Search', success=False)
        self.assertIn('Missing LLM_BASE_URL', result.stderr)
        self.assertFalse((self.base / 'called').exists())

    def test_xdg_default_ignores_hostile_cwd_config(self):
        self.default_config(Path(self.env['XDG_CONFIG_HOME']))
        (self.base / '.env').write_text('LLM_BASE_URL=https://attacker.invalid/steal\n'
                                       'SEARCH_ROOT=/untrusted/unrelated\n')
        self.env['LLM_API_KEY'] = 'synthetic-secret'
        self.assertIn('1. Recent', self.run_default('Vector Search').stdout)

    def test_home_config_fallback(self):
        self.env.pop('XDG_CONFIG_HOME')
        self.default_config(Path(self.env['HOME']) / '.config')
        self.assertIn('1. Recent', self.run_default('Vector Search').stdout)

    def test_relative_or_empty_xdg_is_ignored(self):
        self.default_config(Path(self.env['HOME']) / '.config')
        for value in ('relative-config', ''):
            with self.subTest(value=value):
                self.env['XDG_CONFIG_HOME'] = value
                self.assertIn('1. Recent', self.run_default('Vector Search').stdout)

    def test_absolute_xdg_does_not_require_home(self):
        self.default_config(Path(self.env['XDG_CONFIG_HOME']))
        self.env.pop('HOME')
        self.assertIn('1. Recent', self.run_default('Vector Search').stdout)

    def test_missing_home_fails_clearly_but_explicit_env_works(self):
        self.env.pop('XDG_CONFIG_HOME')
        self.env.pop('HOME')
        self.assertIn('Cannot resolve default configuration', self.run_default('--check-connection', success=False).stderr)
        self.assertIn('connection successful', self.run_app('--check-connection').stdout)

    def test_relative_home_is_rejected(self):
        self.env.pop('XDG_CONFIG_HOME')
        self.env['HOME'] = 'relative-home'
        self.assertIn('Cannot resolve default configuration', self.run_default('--check-connection', success=False).stderr)

    def test_missing_default_allows_environment_only(self):
        self.env.update(LLM_API_KEY='synthetic-secret', LLM_MODEL='gpt-6-astra',
                        LLM_BASE_URL='https://example.invalid/chat/completions', SEARCH_ROOT=str(self.root))
        self.assertIn('1. Recent', self.run_default('Vector Search').stdout)

    def test_missing_default_allows_local_only(self):
        result = self.run_default('--root', str(self.root), '--local-only', 'Vector Search')
        self.assertIn('unverified', result.stderr)
        self.assertFalse((self.base / 'called').exists())

    def test_config_permission_warning(self):
        for mode in (0o644, 0o640, 0o601, 0o600):
            with self.subTest(mode=oct(mode)):
                self.config.chmod(mode)
                result = self.run_app('--check-connection')
                self.assertEqual('Warning: configuration file' in result.stderr, mode != 0o600)
                self.assertNotIn('example.invalid', result.stderr)
        target = self.default_config(Path(self.env['XDG_CONFIG_HOME']))
        target.chmod(0o644)
        self.assertIn('Warning: configuration file', self.run_default('--check-connection').stderr)

    @unittest.skipUnless(os.geteuid() == 0, 'Changing synthetic file ownership requires root')
    def test_config_ownership_warning(self):
        os.chown(self.config, 1, -1)
        self.assertIn('Warning: configuration file', self.run_app('--check-connection').stderr)

    def test_config_checks_symlink_target(self):
        link = self.base / 'linked.env'
        link.symlink_to(self.config)
        result = self.run_default('--env', str(link), '--check-connection')
        self.assertNotIn('Warning:', result.stderr)

    def test_nonregular_config_rejected_without_blocking(self):
        pipe = self.base / 'config.fifo'
        os.mkfifo(pipe)
        result = self.run_default('--env', str(pipe), '--check-connection', success=False)
        self.assertIn('regular file', result.stderr)

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
        self.assertEqual(self.interact(b'999\n2\n'), ['--', str(self.root / 'Related')])

    def test_dolphin_quit(self):
        self.interact(b'q\n')


if __name__ == '__main__':
    unittest.main()
