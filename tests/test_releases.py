import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import iconlib
import verify_releases


class Response(io.BytesIO):
    status = 200

    def geturl(self):
        return "https://release-assets.githubusercontent.com/example?signature=opaque"


class Opener:
    def __init__(self, data):
        self.data = data

    def open(self, request, timeout):
        return Response(self.data)


class ReleaseTests(unittest.TestCase):
    def test_https_asset_hosts_only(self):
        for url in ("http://github.com/a", "https://evil.example/a",
                    "https://github.com.evil.example/a", "https://user@github.com/a",
                    "https://github.com:444/a", "https://github.com/a#fragment"):
            with self.subTest(url=url), self.assertRaises(iconlib.PackageError):
                verify_releases.require_asset_url(url)
        verify_releases.require_asset_url("https://release-assets.githubusercontent.com/a?signature=opaque")

    def test_redirect_rejects_another_host(self):
        with self.assertRaises(iconlib.PackageError):
            verify_releases.AssetRedirects().redirect_request(None, None, 302, "Found", {}, "https://evil.example/a")

    def test_download_byte_bound(self):
        url = verify_releases.RELEASE_BASE + "example/example.zip"
        self.assertEqual(b"abc", verify_releases.fetch_asset(url, 3, Opener(b"abc")))
        with self.assertRaises(iconlib.PackageError):
            verify_releases.fetch_asset(url, 3, Opener(b"abcd"))

    def test_bad_http_status_rejected(self):
        class BadOpener:
            def open(self, request, timeout):
                response = Response(b"error")
                response.status = 404
                return response
        with self.assertRaises(iconlib.PackageError):
            verify_releases.fetch_asset(verify_releases.RELEASE_BASE + "example/a.zip", 20, BadOpener())

    def test_pending_entries_do_not_download(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = verify_releases.verify_releases({"libraries": [{"availability": "pending-publication"}]}, temporary)
            self.assertEqual(result["packages"], 0)
            self.assertEqual(list(Path(temporary).iterdir()), [])
