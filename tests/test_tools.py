import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('installer',ROOT/'tools/install_skill.py')
installer=importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def test_install_to_space_path_and_refuse_overwrite(self):
        with tempfile.TemporaryDirectory(prefix='skill tools ') as tmp:
            dest=Path(tmp)/'skills with spaces'
            result=installer.install(dest)
            self.assertIn('LICENSE',result['verified_files'])
            self.assertNotIn(str(dest),json.dumps(result))
            with self.assertRaises(ValueError):installer.install(dest)
            script=dest/'lottery-analyst/scripts/lottery_cli.py'
            p=subprocess.run([sys.executable,str(script),'rules'],capture_output=True,encoding='utf-8',timeout=30)
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertEqual(json.loads(p.stdout)['rules']['dlt']['front'],[35,5])

    def test_no_recursive_install(self):
        with self.assertRaises(ValueError):installer.install(installer.SOURCE/'nested')

    def test_license_matches_standalone_distribution(self):
        self.assertEqual((ROOT/'LICENSE').read_text(encoding='utf-8'),
                         (installer.SOURCE/'LICENSE').read_text(encoding='utf-8'))
