import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from size_fluent import resize


class FluentSizesTest(unittest.TestCase):
    def manifest(self):
        return {'library_id':'fluent-ui','style_id':'regular-24','conversion':{'revision':'a'*40},'icons':[{'id':'add-regular-24','core_icon_name':'add-regular-24','path':'icons/add-regular-24.svg','sha256':'b'*64}]}

    def test_new_size_namespace_preserves_artwork_hash_without_mutating_source(self):
        original=self.manifest();converted=resize(original,'24','regular','c'*40)
        self.assertEqual('fluent-ui-24',converted['library_id'])
        self.assertEqual('regular',converted['style_id'])
        self.assertEqual('add-regular',converted['icons'][0]['core_icon_name'])
        self.assertEqual(original['icons'][0]['sha256'],converted['icons'][0]['sha256'])
        self.assertEqual('add-regular-24',original['icons'][0]['id'])

    def test_wrong_source_style_or_identity_is_rejected(self):
        with self.assertRaises(ValueError):resize(self.manifest(),'20','regular','c'*40)
        source=self.manifest();source['icons'][0]['core_icon_name']='other'
        with self.assertRaises(ValueError):resize(source,'24','regular','c'*40)
