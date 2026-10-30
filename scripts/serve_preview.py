"""Read-only, loopback-only preview with file-backed logs; works with pythonw."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import os
import re
import sys
from urllib.parse import urlsplit

class PreviewHandler(SimpleHTTPRequestHandler):
    """Single byte-range support lets browser MP4 players seek reliably."""

    def end_headers(self):
        if urlsplit(self.path).path.lower().endswith('.mp4'):
            self.send_header('Accept-Ranges', 'bytes')
        super().end_headers()

    def send_head(self):
        self.range_remaining = None
        path = Path(self.translate_path(self.path))
        requested = self.headers.get('Range')
        if not requested or path.suffix.lower() != '.mp4' or not path.is_file():
            return super().send_head()
        size = path.stat().st_size
        match = re.fullmatch(r'bytes=(\d*)-(\d*)', requested.strip())
        valid = bool(match and any(match.groups()))
        start, end = 0, size - 1
        if valid:
            first, last = match.groups()
            if first:
                start = int(first)
                end = min(int(last), size - 1) if last else size - 1
            else:
                suffix = int(last)
                start = max(0, size - suffix)
                valid = suffix > 0
            valid = valid and 0 <= start <= end < size
        if not valid:
            self.send_response(416)
            self.send_header('Content-Range', f'bytes */{size}')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return None
        stream = path.open('rb')
        stream.seek(start)
        self.range_remaining = end - start + 1
        self.send_response(206)
        self.send_header('Content-Type', self.guess_type(str(path)))
        self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.send_header('Content-Length', str(self.range_remaining))
        self.send_header('Last-Modified', self.date_time_string(path.stat().st_mtime))
        self.end_headers()
        return stream

    def copyfile(self, source, outputfile):
        if self.range_remaining is None:
            return super().copyfile(source, outputfile)
        remaining = self.range_remaining
        while remaining:
            data = source.read(min(remaining, 64 * 1024))
            if not data:
                break
            outputfile.write(data)
            remaining -= len(data)


def main():
    output = Path(__file__).resolve().parents[1] / 'outputs'
    if not (output / 'stage0.html').is_file():
        raise SystemExit('Missing stage0.html')
    with (output / 'preview.log').open('a', encoding='utf-8', buffering=1) as log:
        sys.stdout = sys.stderr = log
        try:
            with ThreadingHTTPServer(('127.0.0.1', 8768), partial(PreviewHandler, directory=str(output))) as server:
                (output / 'preview.pid').write_text(str(os.getpid()), encoding='ascii')
                print(f'Preview started; pid={os.getpid()}; http://127.0.0.1:8768/stage0.html')
                server.serve_forever()
        except Exception:
            import traceback
            traceback.print_exc()
            raise


if __name__ == '__main__':
    main()
