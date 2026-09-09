"""Regression coverage for validation and data selection boundaries."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from test_lottery import fixture
import test_lottery
from lottery.core import LotteryError, validate_draw
from lottery.official import fetch, parse_row
from lottery.storage import Store


class ValidationTests(unittest.TestCase):
    def test_special_rejects_integer(self):
        for value in (0, 1, 'false'):
            with self.subTest(value=value), self.assertRaises(LotteryError):
                validate_draw('ssq', fixture(n=1)[0] | {'special':value})

    def test_reject_invalid_amounts_and_dates(self):
        for amount in ('NaN', 'Infinity', '-1', True, None):
            with self.subTest(amount=amount), self.assertRaises(LotteryError):
                validate_draw('ssq', fixture(n=1)[0] | {'prizes':{'1':amount}})
        with self.assertRaises(LotteryError):
            validate_draw('ssq', fixture(n=1)[0] | {'date':'20250101'})

    def test_duplicate_prize(self):
        raw=test_lottery.OfficialTests().raw()
        raw['prizegrades'].append(copy.deepcopy(raw['prizegrades'][0]))
        with self.assertRaises(LotteryError): parse_row('ssq',raw)

    def test_page_count_mismatch(self):
        payload={'state':0,'pageNo':1,'total':1,'result':[test_lottery.OfficialTests().raw(),test_lottery.OfficialTests().raw()]}
        with self.assertRaises(LotteryError): fetch('ssq',getter=lambda *args:payload)


class SelectionTests(unittest.TestCase):
    def test_single_draw_and_selected_range_ignore_unrelated_gaps(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'test.sqlite3')
            try:
                rows=fixture()
                store.ingest('ssq',rows[:1],{'test':True})
                store.ingest('ssq',rows[10:],{'test':True})
                with self.assertRaises(LotteryError):store.history('ssq')
                self.assertEqual(store.draw('ssq','2025011')['issue'],'2025011')
                self.assertEqual(len(store.history('ssq',start='2025011',end='2025040')),30)
                with self.assertRaises(LotteryError):store.history('ssq',start='2025040',end='2025011')
            finally:store.close()

    def test_cli_accepts_bom_config_and_unicode_paths(self):
        cli=Path(__file__).resolve().parents[1]/'lottery-analyst/scripts/lottery_cli.py'
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp)/'测试 folder';work.mkdir()
            config=work/'config.json'
            config.write_text('{"max_overlap":2}',encoding='utf-8-sig')
            proc=subprocess.run([sys.executable,str(cli),'--db',str(work/'test.sqlite3'),
                'generate','--game','dlt','--target','2025041','--mode','diverse','--config',str(config)],
                capture_output=True,encoding='utf-8',cwd=work,timeout=30)
            self.assertEqual(proc.returncode,0,proc.stderr)
            self.assertEqual(len(json.loads(proc.stdout)['tickets']),5)
