"""Real local HTTP semantics for MP4 seeking; bytes are a software fixture."""
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import unittest

from scripts.serve_preview import PreviewHandler


class QuietHandler(PreviewHandler):
    def log_message(self, *args):
        pass


class VideoRanges(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = TemporaryDirectory(prefix='supportdesk-range-test-')
        cls.payload = bytes(range(100))
        (Path(cls.directory.name) / 'fixture.mp4').write_bytes(cls.payload)
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=cls.directory.name))
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}/fixture.mp4'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.directory.cleanup()

    def get(self, value=None, method='GET'):
        return urlopen(Request(self.url, headers={'Range': value} if value else {}, method=method), timeout=3)

    def test_full_video_advertises_seek_support(self):
        with self.get() as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers['Accept-Ranges'], 'bytes')
            self.assertEqual(response.read(), self.payload)

    def test_bounded_range_returns_only_requested_bytes(self):
        with self.get('bytes=10-29') as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.headers['Content-Range'], 'bytes 10-29/100')
            self.assertEqual(response.headers['Content-Length'], '20')
            self.assertEqual(response.read(), self.payload[10:30])

    def test_open_ended_range_reaches_end(self):
        with self.get('bytes=80-') as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.read(), self.payload[80:])

    def test_suffix_range_returns_tail(self):
        with self.get('bytes=-12') as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.headers['Content-Range'], 'bytes 88-99/100')
            self.assertEqual(response.read(), self.payload[-12:])

    def test_unsatisfiable_and_multiple_ranges_fail_clearly(self):
        for value in ['bytes=100-', 'bytes=-0', 'bytes=70-20', 'bytes=1-2,5-6']:
            with self.subTest(value=value), self.assertRaises(HTTPError) as caught:
                self.get(value)
            self.assertEqual(caught.exception.code, 416)
            self.assertEqual(caught.exception.headers['Content-Range'], 'bytes */100')
            self.assertEqual(caught.exception.read(), b'')

    def test_range_head_has_headers_without_body(self):
        with self.get('bytes=10-19', method='HEAD') as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.headers['Content-Length'], '10')
            self.assertEqual(response.read(), b'')
