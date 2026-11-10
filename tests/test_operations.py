"""배포 중단이 초록으로 숨지 않는지 검증 (네트워크 없이 실행)."""
import sys
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/audit'))
import check_operations as ops
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/fetch'))
import fetch_gallup_self as fetcher


class OperationsTests(unittest.TestCase):
    def test_build_marker(self):
        self.assertEqual(ops.build_sha('<meta content="abcdef123456 2026-09-03" name="polis-build">'), 'abcdef123456')
        for html in ('<html>200 OK</html>', '<meta name="polis-build" content="bad">'):
            with self.assertRaises(ValueError):
                ops.build_sha(html)

    def test_exact_delivery(self):
        self.assertIsNone(ops.deployment_problem('a' * 12, 'a' * 40, True, 24))
        self.assertIn('불일치', ops.deployment_problem('b' * 12, 'a' * 40, True, 24))

    @patch.object(ops.subprocess, 'run')
    @patch.object(ops, 'git')
    def test_new_commits_do_not_hide_old_undelivered_commits(self, git, run):
        git.side_effect = ['b' * 40, '2026-11-10T00:00:00+00:00\n2026-09-04T00:00:00+00:00']
        problem = ops.deployment_problem('b' * 12, 'a' * 40, False, 24,
                                        datetime(2026, 11, 10, tzinfo=timezone.utc))
        self.assertIn('배포 지연', problem)

    @patch.object(ops.subprocess, 'run')
    @patch.object(ops, 'git')
    def test_allows_deployment_in_progress(self, git, run):
        git.side_effect = ['b' * 40, '2026-11-10T00:00:00+00:00']
        self.assertIsNone(ops.deployment_problem('b' * 12, 'a' * 40, False, 24,
                          datetime(2026, 11, 10, 1, tzinfo=timezone.utc)))

    @patch.object(ops, 'git', side_effect=ops.subprocess.CalledProcessError(128, 'git'))
    def test_unknown_sha_fails(self, git):
        self.assertIn('대조할 수 없습니다', ops.deployment_problem('b' * 12, 'a' * 40, False, 24))

    def test_manual_refresh_is_not_healthy(self):
        rows = [dict(label=s, state=s, last='2026-08-10', next='2026-08-20')
                for s in ('fresh', 'expected_pause', 'manual_refresh', 'overdue', 'fetch_failed')]
        self.assertEqual(len(ops.freshness_problems(rows)), 3)

    def test_latest_date_ignores_record_order(self):
        self.assertEqual(ops.latest_date({'records': [{'date': '2026-11-05'}, {'period_end': '2026-08-10'}]}), '2026-11-05')
        self.assertEqual(ops.latest_date({'records': []}), '')


class GallupIncrementalTests(unittest.TestCase):
    def test_cold_cache_preserves_history_and_replaces_same_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'leaders.json'
            old = [{'seqNo': 1, 'candidate': '가', 'pct': 10},
                   {'seqNo': 2, 'candidate': '나', 'pct': 20}]
            path.write_text(json.dumps({'records': old}))
            identity = lambda r: (r['seqNo'], r['candidate'])
            self.assertEqual(fetcher.merge_records(path, 'records', [], identity), old)
            new = [{'seqNo': 2, 'candidate': '나', 'pct': 21},
                   {'seqNo': 3, 'candidate': '다', 'pct': 30}]
            merged = fetcher.merge_records(path, 'records', new, identity)
            self.assertEqual(merged, [old[0], *new])
            path.write_text(json.dumps({'records': merged}))
            self.assertEqual(fetcher.merge_records(path, 'records', new, identity), merged)

    def test_latest_report_comes_from_official_listing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'leaders.json'
            path.write_text(json.dumps({'records': [{'seqNo': 1644}]}))
            with patch.object(fetcher, 'OUT', path), patch.object(fetcher.urllib.request, 'urlopen') as open_url:
                open_url.return_value.__enter__.return_value.read.return_value = b'<a href="reportContent.asp?seqNo=1666">latest</a>'
                self.assertEqual(fetcher.recent_bounds(), (1666, 1642))
                open_url.return_value.__enter__.return_value.read.return_value = b'blocked'
                with self.assertRaises(RuntimeError):
                    fetcher.recent_bounds()


if __name__ == '__main__':
    unittest.main()
