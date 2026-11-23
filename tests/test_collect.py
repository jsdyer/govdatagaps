import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import collect


class FakeResponse:
    def __init__(self, body): self.body = body
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, size): return self.body[:size]


class CollectionTests(unittest.TestCase):
    def test_response_classes_keep_blocked_and_missing_distinct(self):
        for code, expected in [(200,'reachable'),(206,'reachable'),(404,'unavailable'),(410,'unavailable'),(403,'blocked'),(429,'blocked'),(503,'inconclusive')]:
            self.assertEqual(collect.classify_status(code), expected)

    def test_normalization_preserves_distinct_dates_and_cadence(self):
        raw={'title_translated':{'en':'A record'},'metadata_modified':'2026-11-01','date_modified':'2025-01-01','frequency':'as_needed','organization':{'title':'Publisher'},'resources':[{'id':'r','name_translated':{'en':'File'},'url':'https://example.com/x.csv','format':'CSV'}]}
        result=collect.normalize(raw,{'id':'x','label':'X','theme':'Example'},'abc')
        self.assertEqual(result['dataset_modified'],'2025-01-01')
        self.assertEqual(result['metadata_modified'],'2026-11-01')
        self.assertEqual(result['frequency'],'as_needed')
        self.assertEqual(result['resources'][0]['name'],'File')

    def test_failed_metadata_refresh_cannot_replace_prior_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'config').mkdir();(root/'web/data').mkdir(parents=True)
            (root/'config/watchlist.json').write_text(json.dumps([{'id':'x','label':'X','theme':'T'}]))
            before='{"captures": [{"id": "prior"}]}'
            (root/'web/data/manifest.json').write_text(before)
            with patch.object(collect,'request',return_value=FakeResponse(b'{"success":false,"error":{"__type":"Validation Error"}}')):
                with self.assertRaises(ValueError): collect.collect(root)
            self.assertEqual((root/'web/data/manifest.json').read_text(),before)
            self.assertFalse((root/'web/data/snapshots').exists())

    def test_real_baseline_raw_responses_match_stored_hashes(self):
        data=collect.ROOT/'web/data'
        manifest=json.loads((data/'manifest.json').read_text())
        self.assertGreaterEqual(len(manifest['captures']),1)
        for capture in manifest['captures']:
            snapshot_path=collect.ROOT/'web'/capture['file'].removeprefix('./')
            snapshot=json.loads(snapshot_path.read_text())
            collect.validate(snapshot)
            for row in snapshot['datasets']:
                body=(collect.ROOT/'web'/row['raw_file'].removeprefix('./')).read_bytes()
                self.assertEqual(hashlib.sha256(body).hexdigest(),row['source_sha256'])
                raw=json.loads(body)
                if row['state']=='present':
                    self.assertTrue(raw['success'])
                    self.assertEqual(raw['result']['id'],row['id'])

    def test_source_urls_reject_local_credentials_and_non_http_schemes(self):
        for value in ['file:///etc/passwd','http://localhost/x','http://127.0.0.1/x','https://user:pass@example.com','http://example.com:8080/x']:
            with self.assertRaises(ValueError): collect.public_url(value)

    def test_unknown_state_invalidates_capture(self):
        with self.assertRaises(ValueError):
            collect.validate({'schema_version':1,'captured_at':'2026-11-23','datasets':[{'id':'x','state':'failed','source_api':'https://example.com'}]})


if __name__=='__main__': unittest.main()
