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
if mode == 'curl-timeout': sys.exit(28)
if mode == 'http':
    print('{"error":"synthetic-secret"}\n401', end=''); sys.exit(0)
if request['messages'][0]['content'] == 'Reply with exactly OK.':
    assert request['max_completion_tokens'] == 2048
    content = 'OK'
else:
    assert request['max_completion_tokens'] == 16384
    context = json.loads(request['messages'][1]['content'])
    assert context['as_of_date'] == datetime.date.today().isoformat()
    candidates = context['candidates']
    assert len(candidates) <= int(os.environ.get('EXPECTED_CANDIDATES', '40'))
    if 'EXPECTED_EXACT_CANDIDATES' in os.environ:
        assert len(candidates) == int(os.environ['EXPECTED_EXACT_CANDIDATES'])
    assert all(len(c['excerpts'].encode()) <= 3000 for c in candidates)
    for c in candidates:
        for text in json.loads(os.environ.get('EXPECTED_EXCERPT_TEXT', '{}')).get(Path(c['folder']).name, []):
            assert text in c['excerpts']
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
    if mode == 'bad-relevance': results[0]['relevance'] = 4
    if mode in ('null-fields', 'missing-fields', 'wrong-fields'):
        for field in ('customer', 'subject', 'date', 'date_evidence'):
            if mode == 'missing-fields': results[0].pop(field)
            else: results[0][field] = None if mode == 'null-fields' else ['not a string']
    if mode == 'nonobject': results.append(None)
    if mode == 'oversized': results[0]['customer'] = 'x' * 201
    if mode == 'all-oversized':
        for result in results: result['subject'] = 'x' * 301
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
if mode == 'missing-envelope': reply = {}
if mode == 'null-content': reply['choices'][0]['message']['content'] = None
if mode == 'filtered': reply['choices'][0]['finish_reason'] = 'content_filter'
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

    def run_app(self, *args, mode='', success=True, timeout=15):
        env = dict(self.env, TEST_MODE=mode)
        result = subprocess.run([BINARY, '--env', str(self.config), '--no-open', *args],
                                env=env, cwd=self.base, text=True, capture_output=True, timeout=timeout)
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
        expected = ['DirectHigh', 'DirectLowA', 'DirectLowZ', 'RelatedHigh']
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
        for mode in ('bad-id', 'bad-relevance', 'nonobject', 'duplicate', 'malformed', 'length'):
            with self.subTest(mode=mode):
                result = self.run_app('Vector Search', mode=mode, success=False)
                self.assertNotIn('1. ', result.stdout)

    def test_optional_model_text_fields_are_tolerated(self):
        for mode in ('null-fields', 'missing-fields', 'wrong-fields'):
            with self.subTest(mode=mode):
                result = self.run_app('Vector Search', mode=mode)
                self.assertIn('Unknown | Unknown | Unknown', result.stdout)
                self.assertEqual(result.stdout.count('\n   '), 3)

    def test_oversized_fields_skip_only_the_item(self):
        result = self.run_app('Vector Search', mode='oversized')
        self.assertIn('Skipped 1 model result(s)', result.stderr)
        self.assertEqual(result.stdout.count('\n   '), 2)
        self.assertNotIn('x' * 201, result.stdout + result.stderr)
        result = self.run_app('Vector Search', mode='all-oversized', success=False)
        self.assertIn('Skipped 3 model result(s)', result.stderr)
        self.assertIn('invalid session data', result.stderr)

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

    def test_stopwords_do_not_retrieve_unrelated_notes(self):
        self.note('Noise', 'the unrelated workshop\n')
        target = self.note('Quasars', 'quasars workshop\n')
        result = self.run_app('--local-only', 'the quasars')
        self.assertIn(str(target), result.stdout)
        self.assertEqual(result.stdout.count('\n   '), 1)

    def test_all_stopword_query_still_searches(self):
        self.note('Stopwords', 'the and\n')
        self.assertIn('Stopwords', self.run_app('--local-only', 'the and').stdout)

    def test_rare_term_beats_common_term_in_shortlist(self):
        self.ranking_fixture([])
        self.note('Rare', 'rare\n')
        for i in range(8): self.note('Common' + str(i), 'common\n')
        result = self.run_app('--local-only', '--candidates', '1', 'common rare')
        self.assertIn(str(self.root / 'Rare'), result.stdout)
        self.assertNotIn(str(self.root / 'Common'), result.stdout)

    def test_default_shortlist_contains_forty_candidates(self):
        self.ranking_fixture([])
        for i in range(41): self.note('Session' + str(i), 'Vector Search\nDelivered: 2025-09-14\n')
        self.env['EXPECTED_EXACT_CANDIDATES'] = '40'
        result = self.run_app('Vector Search')
        self.assertIn('top 40 matching folders', result.stderr)

    def test_filtered_terms_are_used_by_coverage_cap(self):
        self.coverage_fixture('alpha\n', 'alpha exercise one\nalpha exercise two\n')
        self.assertEqual(self.ranked_customers('the and alpha'), ['Claimed', 'Reference'])

    def session_tree(self):
        self.ranking_fixture([])
        session = self.root / 'Acme' / '2025-09-14'
        for subdir, marker in (('notes', 'Notebook material'), ('slides', 'Slide text material')):
            folder = session / subdir
            folder.mkdir(parents=True)
            (folder / 'notes.txt').write_text('Vector Search\nDelivered: 2025-09-14\n' + marker + '\n')
        (session / 'overview.md').write_text('Vector Search overview\nDelivered: 2025-09-14\n')
        return session

    def test_customer_date_documents_group_into_one_session(self):
        session = self.session_tree()
        self.env['EXPECTED_EXACT_CANDIDATES'] = '1'
        self.env['EXPECTED_EXCERPT_TEXT'] = json.dumps({session.name: ['Notebook material', 'Slide text material',
                                                                    'notes/notes.txt', 'slides/notes.txt']})
        result = self.run_app('Vector Search')
        self.assertEqual(result.stdout.count('\n   '), 1)
        self.assertIn(str(session), result.stdout)

    def test_separate_session_dates_stay_separate(self):
        first = self.session_tree()
        second = first.parent / '2025-09-15'
        second.mkdir()
        (second / 'notes.txt').write_text('Vector Search\nDelivered: 2025-09-15\n')
        self.env['EXPECTED_EXACT_CANDIDATES'] = '2'
        result = self.run_app('Vector Search')
        self.assertEqual(result.stdout.count('\n   '), 2)
        self.assertIn(str(first), result.stdout)
        self.assertIn(str(second), result.stdout)

    def test_narrow_root_preserves_session_boundary_and_containment(self):
        session = self.session_tree()
        for root, expected in ((session.parent, session), (session, session), (session / 'notes', session / 'notes')):
            with self.subTest(root=root):
                result = self.run_app('--local-only', '--root', str(root), 'Vector Search')
                self.assertEqual(result.stdout.count('\n   '), 1)
                self.assertIn('\n   ' + str(expected) + '\n', result.stdout)

    def test_ignore_rules_do_not_hide_ordinary_notes(self):
        (self.root / '.ignore').write_text('Ignored/\n')
        (self.root / '.gitignore').write_text('GitIgnored/\n')
        (self.root / '.git').mkdir()
        first = self.note('Ignored', 'visibilityprobe\n')
        second = self.note('GitIgnored', 'visibilityprobe\n')
        result = self.run_app('--local-only', 'visibilityprobe')
        self.assertEqual(result.stdout.count('\n   '), 2)
        self.assertIn(str(first), result.stdout)
        self.assertIn(str(second), result.stdout)

    def test_hidden_and_binary_notes_remain_excluded(self):
        self.note('.private', 'visibilityprobe\n')
        (self.root / '.env').write_text('visibilityprobe\n')
        (self.root / 'binary.dat').write_bytes(b'\x00visibilityprobe\n')
        visible = self.note('Visible', 'visibilityprobe\n', 'notes.md')
        result = self.run_app('--local-only', 'visibilityprobe')
        self.assertEqual(result.stdout.count('\n   '), 1)
        self.assertIn(str(visible), result.stdout)
        self.assertNotIn('.private', result.stdout)

    def test_http_error_hides_response_and_credentials(self):
        result = self.run_app('Vector Search', mode='http', success=False)
        self.assertIn('HTTP 401', result.stderr)

    def test_connection_check_sends_no_notes(self):
        self.assertIn('connection successful', self.run_app('--check-connection').stdout)

    def test_truncation_has_specific_error(self):
        for args in (('Vector Search',), ('--check-connection',)):
            result = self.run_app(*args, mode='length', success=False)
            self.assertIn('truncated', result.stderr)
            self.assertNotIn('try fewer candidates', result.stderr)

    def test_curl_timeout_remains_an_error(self):
        result = self.run_app('Vector Search', mode='curl-timeout', success=False)
        self.assertIn('Grove request timed out', result.stderr)
        self.assertNotIn('1. ', result.stdout)

    def test_invalid_and_incomplete_completions_have_distinct_errors(self):
        for mode in ('missing-envelope', 'null-content'):
            self.assertIn('invalid completion response', self.run_app('Vector Search', mode=mode, success=False).stderr)
        self.assertIn('incomplete completion', self.run_app('Vector Search', mode='filtered', success=False).stderr)

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

    def test_output_limited_retrieval_is_repeatable(self):
        self.ranking_fixture([])
        for i in range(16):
            self.note('Volume' + str(i), ('Vector Search ' + 'x' * 100000 + '\n') * 12)
        outputs = []
        for _ in range(2):
            result = self.run_app('--local-only', '--limit', '30', 'Vector Search')
            self.assertIn('Search output limit reached', result.stderr)
            outputs.append(result.stdout)
        self.assertEqual(outputs[0], outputs[1])

    def mock_rg(self, paths, delay=0):
        events = [dict(type='match', data=dict(path=dict(text=str(path)), line_number=1,
                  lines=dict(text='Vector Search\nDelivered: 2026-10-22\n'))) for path in paths]
        script = self.bin / 'rg'
        script.write_text('#!' + sys.executable + '\nimport json, time\n' +
                          'events = ' + repr(events) + '\n' +
                          'for event in events: print(json.dumps(event), flush=True)\n' +
                          'time.sleep(' + str(delay) + ')\n')
        script.chmod(0o755)

    def test_search_timeout_retains_partial_records(self):
        self.mock_rg([self.root / 'Recent' / 'notes.txt'], delay=60)
        started = time.monotonic()
        result = self.run_app('--local-only', 'Vector Search', timeout=35)
        self.assertIn(str(self.root / 'Recent'), result.stdout)
        self.assertIn('Search timed out; using partial results', result.stderr)
        self.assertLess(time.monotonic() - started, 34)

    def test_inaccessible_paths_are_counted_once_and_other_files_survive(self):
        blocked = self.root / 'blocked'
        blocked.write_text('not a directory')
        bad = blocked / 'notes.txt'
        self.mock_rg([bad, bad, self.root / 'Recent' / 'notes.txt'])
        result = self.run_app('--local-only', 'Vector Search')
        self.assertIn('Skipped 1 inaccessible file path(s)', result.stderr)
        self.assertIn(str(self.root / 'Recent'), result.stdout)
        self.assertNotIn(str(bad), result.stdout + result.stderr)

    def test_empty_partial_search_does_not_claim_complete_coverage(self):
        self.mock_rg([self.root / 'removed.txt'])
        result = self.run_app('--local-only', 'Vector Search')
        self.assertIn('partial search results; coverage is incomplete', result.stdout)
        self.assertNotIn('Model-generated', result.stderr)

    def test_empty_verification_of_partial_search_is_labeled(self):
        self.mock_rg([self.root / 'removed.txt', self.root / 'Recent' / 'notes.txt'])
        result = self.run_app('Vector Search', mode='empty')
        self.assertIn('partial candidate excerpts; coverage is incomplete', result.stdout)

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
