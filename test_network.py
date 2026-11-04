"""Collector network failure regressions without live HTTP or credentials."""
import json
import ssl
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import collect


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.used_reader = patch.object(collect, 'USED_READER', False)
        self.used_reader.start()
        self.addCleanup(self.used_reader.stop)

    @staticmethod
    def expired_certificate():
        return urllib.error.URLError(
            ssl.SSLCertVerificationError(10, 'certificate has expired'))

    @staticmethod
    def reader_error(status, headers=None):
        return urllib.error.HTTPError(
            'https://r.jina.ai/'+collect.SOURCE, status,
            'reader request failed', headers, None)

    @staticmethod
    def response():
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'<html>public event content</html>'
        return response

    def test_expired_origin_and_reader_422_recover_without_weakening_tls(self):
        with patch.object(collect.urllib.request, 'urlopen', side_effect=[
                self.expired_certificate(), self.reader_error(422),
                self.response()]) as request, patch.object(collect.time, 'sleep') as sleep:
            result = collect.download(collect.SOURCE)
        self.assertEqual(result, b'<html>public event content</html>')
        self.assertTrue(collect.USED_READER)
        self.assertEqual(request.call_count, 3)
        sleep.assert_called_once_with(2)
        for args, kwargs in request.call_args_list:
            self.assertNotIn('context', kwargs)
            self.assertNotIn('cookie', {key.lower(): value for key, value in args[0].header_items()})
        self.assertEqual(request.call_args.args[0].full_url,
                         'https://r.jina.ai/'+collect.SOURCE)

    def test_reader_connection_failure_is_retried(self):
        with patch.object(collect.urllib.request, 'urlopen', side_effect=[
                self.expired_certificate(), urllib.error.URLError('connection reset'),
                self.response()]), patch.object(collect.time, 'sleep') as sleep:
            self.assertEqual(collect.download(collect.SOURCE),
                             b'<html>public event content</html>')
        sleep.assert_called_once_with(2)

    def test_invalid_retry_after_does_not_break_recovery(self):
        with patch.object(collect.urllib.request, 'urlopen', side_effect=[
                self.expired_certificate(),
                self.reader_error(429, {'Retry-After': 'unknown'}),
                self.response()]), patch.object(collect.time, 'sleep') as sleep:
            collect.download(collect.SOURCE)
        sleep.assert_called_once_with(2)

    def test_permanent_reader_error_fails_without_retry(self):
        with patch.object(collect.urllib.request, 'urlopen', side_effect=[
                self.expired_certificate(), self.reader_error(404)]) as request, \
                patch.object(collect.time, 'sleep') as sleep:
            with self.assertRaises(urllib.error.HTTPError):
                collect.download(collect.SOURCE)
        self.assertEqual(request.call_count, 2)
        sleep.assert_not_called()

    def test_exhausted_retries_preserve_last_successful_snapshot(self):
        previous = json.dumps({'updatedAt': 1793754892929, 'records': [{'id': 'kept'}]})+'\n'
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'calendar.json'
            output.write_text(previous)
            with patch.object(collect.urllib.request, 'urlopen', side_effect=[
                    self.expired_certificate(), self.reader_error(422),
                    self.reader_error(503), self.reader_error(422)]) as request, \
                    patch.object(collect.time, 'sleep') as sleep:
                with self.assertRaises(urllib.error.HTTPError):
                    collect.collect(output)
            self.assertEqual(output.read_text(), previous)
            self.assertFalse(output.with_suffix('.tmp').exists())
            self.assertEqual(request.call_count, 4)
            self.assertEqual([call.args[0] for call in sleep.call_args_list], [2, 4])


if __name__ == '__main__':
    unittest.main()
