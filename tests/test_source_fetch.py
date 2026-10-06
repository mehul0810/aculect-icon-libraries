import io
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from fetch_sources import snapshot
import iconlib


class SourceFetchTest(unittest.TestCase):
    def archive(self,path,name,payload,kind=tarfile.REGTYPE):
        with tarfile.open(path,"w") as target:
            member = tarfile.TarInfo(name)
            member.size = len(payload)
            member.type = kind
            target.addfile(member,io.BytesIO(payload))

    def test_exclusion_json_has_metadata_bound_and_svg_retains_artwork_bound(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = b'x'*(iconlib.MAX_SVG+1)
            self.archive(root/'data.tar','snapshot/assets/icons/example/exclusions.json',payload)
            snapshot(root/'data.tar',root/'data',['example'])
            self.assertEqual(payload,(root/'data/example/exclusions.json').read_bytes())
            self.archive(root/'svg.tar','snapshot/assets/icons/example/solid/icon.svg',payload)
            with self.assertRaises(ValueError): snapshot(root/'svg.tar',root/'svg',['example'])

    def test_traversal_and_symlinks_fail_without_writing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name,kind in [('snapshot/assets/icons/example/../../escape.svg',tarfile.REGTYPE),('snapshot/assets/icons/example/icon.svg',tarfile.SYMTYPE)]:
                self.archive(root/'bad.tar',name,b'no',kind)
                with self.assertRaises(ValueError): snapshot(root/'bad.tar',root/'out',['example'])
            self.assertFalse((root/'escape.svg').exists())
