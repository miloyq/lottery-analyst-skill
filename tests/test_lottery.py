"""All rows below are explicitly synthetic test fixtures, never production draws."""
import copy
import json
import random
import sqlite3
import sys
import tempfile
import unittest
import urllib.error
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'lottery-analyst'/'scripts'))
from lottery.core import *
from lottery.official import parse_row, fetch, request_json, money
from lottery.storage import Store


def fixture(game='ssq', n=40):
    rng = random.Random(8)
    return [{'issue':f'2025{i+1:03}', 'date':str(date(2025,1,1)+timedelta(days=i*2)),
             **{p:sorted(rng.sample(range(1,RULES[game][p][0]+1),RULES[game][p][1])) for p in ('front','back')},
             'prizes':{str(k):str(k*10) for k in range(1,10)},'additional_prizes':{'1':'80','2':'40'},
             'special':False,'source':'SYNTHETIC_TEST_ONLY'} for i in range(n)]


class RuleTests(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(issue_id('dlt','26014'),'2026014')
        for game,s in [('ssq','26014'),('dlt','26000'),('ssq','2002001'),('dlt','abc')]:
            with self.subTest(s=s), self.assertRaises(LotteryError): issue_id(game,s)

    def test_invalid_ticket(self):
        for nums in ([1,1,3,4,5,6],[0,2,3,4,5,6],[1,2,3,4,5,34],[True,2,3,4,5,6],[1,2,3]):
            with self.subTest(nums=nums),self.assertRaises(LotteryError): ticket('ssq',nums,[1])

    def test_boundaries(self):
        self.assertEqual(version('dlt','26013')['id'],'dlt-2019')
        self.assertEqual(version('dlt','26014')['id'],'dlt-2026')
        self.assertEqual(version('ssq','2026014')['id'],'ssq-2026')
        with self.assertRaises(LotteryError): version('dlt','19018')

    def test_history_errors(self):
        rows = fixture()
        for bad in (rows[:2]+rows[1:2],rows[:1]+rows[2:4]):
            with self.assertRaises(LotteryError): validate_history('ssq',bad)
        rows[0]['date']='2099-01-01'
        with self.assertRaises(LotteryError): validate_history('ssq',rows)


class StatsTests(unittest.TestCase):
    def test_hand_verified(self):
        rows=fixture(n=2)
        rows[0].update(front=[1,2,3,4,5,6],back=[1])
        rows[1].update(front=[1,3,5,7,9,11],back=[2])
        s=statistics('ssq',rows)
        self.assertEqual(s['front']['frequency'][1],2)
        self.assertEqual(s['front']['frequency'][2],1)
        self.assertEqual(s['front']['omission'][2],{'draws':1,'censored':False})
        self.assertEqual(s['front']['omission'][33],{'draws':2,'censored':True})
        self.assertEqual(s['back']['omission'][2]['draws'],0)
        self.assertEqual(s['per_draw'][0]['front']['sum'],21)
        self.assertEqual(s['per_draw'][0]['front']['span'],5)
        self.assertEqual(s['per_draw'][0]['front']['odd_even'],[3,3])
        self.assertEqual(s['per_draw'][0]['front']['consecutive_count'],5)
        self.assertEqual(s['per_draw'][0]['front']['zones'],[6,0,0])

    def test_empty(self):
        with self.assertRaises(LotteryError): statistics('ssq',[])

    def test_frequency_totals(self):
        for game in RULES:
            s=statistics(game,fixture(game))
            for part in ('front','back'):
                self.assertEqual(sum(s[part]['frequency'].values()),40*RULES[game][part][1])


class GenerationTests(unittest.TestCase):
    def test_modes(self):
        for game in RULES:
            for mode in ('uniform','constrained','diverse'):
                r=generate(game,mode,seed=19,history=fixture(game))
                self.assertEqual(len(r['tickets']),5)
                self.assertEqual(len({dump(t) for t in r['tickets']}),5)
                for t in r['tickets']: self.assertEqual(ticket(game,**t),t)
                self.assertEqual(r,generate(game,mode,seed=19,history=fixture(game)))

    def test_constraints(self):
        r=generate('ssq','constrained',seed=4,history=fixture(),config={'sum_range':[90,120],'odd_range':[3,3],'max_consecutive':0})
        for t in r['tickets']:
            f=features('ssq','front',t['front'])
            self.assertTrue(90<=f['sum']<=120)
            self.assertEqual(f['odd_even'][0],3)
            self.assertEqual(f['consecutive_count'],0)

    def test_diversity(self):
        r=generate('dlt','diverse',seed=3)
        for i,a in enumerate(r['tickets']):
            for b in r['tickets'][i+1:]: self.assertLessEqual(sum(len(set(a[p])&set(b[p])) for p in a),2)

    def test_fail_closed(self):
        with self.assertRaises(LotteryError): generate('ssq','constrained')
        with self.assertRaises(LotteryError): generate('ssq','uniform',config={'sum_range':[1,2]})
        with self.assertRaises(LotteryError): generate('ssq','diverse',config={'sum_range':[0,0],'attempts':10})
        with self.assertRaises(LotteryError): generate('ssq',count=0)
        with self.assertRaises(LotteryError): generate('ssq',config={'typo':1})

    def test_uniform_probability(self):
        self.assertEqual(generate('ssq',seed=1)['jackpot_probability_per_ticket'],'1/17721088')
        self.assertEqual(generate('dlt',seed=1)['jackpot_probability_per_ticket'],'1/21425712')


class CheckTests(unittest.TestCase):
    def test_all_hit_patterns(self):
        # Independent expected tables; enumerate all possible front/back hit counts.
        tables={('ssq','2025001'):{(6,1):1,(6,0):2,(5,1):3,(5,0):4,(4,1):4,(4,0):5,(3,1):5,(2,1):6,(1,1):6,(0,1):6},
                ('dlt','25001'):{(5,2):1,(5,1):2,(5,0):3,(4,2):4,(4,1):5,(3,2):6,(4,0):7,(3,1):8,(2,2):8,(3,0):9,(2,1):9,(1,2):9,(0,2):9},
                ('dlt','26014'):{(5,2):1,(5,1):2,(5,0):3,(4,2):3,(4,1):4,(4,0):5,(3,2):5,(3,1):6,(2,2):6,(3,0):7,(2,1):7,(1,2):7,(0,2):7}}
        for (game,issue),expected in tables.items():
            f,b=RULES[game]['front'][1],RULES[game]['back'][1]
            draw={'issue':issue,'date':('2026-02-02' if '26' in issue else '2025-01-01'),'front':list(range(1,f+1)),'back':list(range(1,b+1))}
            for a in range(f+1):
                for c in range(b+1):
                    t={'front':list(range(1,a+1))+list(range(f+1,2*f-a+1)), 'back':list(range(1,c+1))+list(range(b+1,2*b-c+1))}
                    with self.subTest(game=game,issue=issue,hits=(a,c)):
                        self.assertEqual(check(game,t,draw)['tier'],expected.get((a,c)))

    def test_special(self):
        draw={'issue':'2026014','date':'2026-02-01','front':[1,2,3,4,5,6],'back':[1]}
        t={'front':[1,2,3,20,21,22],'back':[2]}
        with self.assertRaises(LotteryError): check('ssq',t,draw)
        self.assertEqual(check('ssq',t,draw|{'special':True})['tier'],7)
        self.assertIsNone(check('ssq',t,draw|{'special':False})['tier'])

    def test_money_additional(self):
        d=fixture('dlt',1)[0]
        self.assertEqual(check('dlt',d,d,True)['amount_yuan'],'90')
        d['additional_prizes']={}
        self.assertIsNone(check('dlt',d,d,True)['amount_yuan'])


class BacktestTests(unittest.TestCase):
    def test_future_mutation_invariance(self):
        rows=fixture(n=40)
        first=backtest('ssq',rows,'constrained',seed=9,warmup=30,window=10)
        changed=copy.deepcopy(rows)
        changed[35]['front']=[2,4,6,8,10,12]
        second=backtest('ssq',changed,'constrained',seed=9,warmup=30,window=10)
        self.assertEqual(first['folds'][:5],second['folds'][:5])
        self.assertEqual(first['folds'][5]['tickets'],second['folds'][5]['tickets'])
        self.assertTrue(all(f['train_last']<f['target'] for f in first['folds']))

    def test_prefix_consistency(self):
        a=backtest('dlt',fixture('dlt',35),warmup=30)
        b=backtest('dlt',fixture('dlt',40),warmup=30)
        self.assertEqual(a['folds'],b['folds'][:5])
        self.assertEqual(a['cost_yuan'],50)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.s=Store(Path(self.tmp.name)/'test.db')
    def tearDown(self):
        self.s.close();self.tmp.cleanup()
    def test_idempotence_and_conflict(self):
        rows=fixture(n=3)
        self.assertEqual(self.s.ingest('ssq',rows,{'test':True})['inserted'],3)
        self.assertEqual(self.s.ingest('ssq',rows,{'test':True})['inserted'],0)
        rows[0]['back']=[16]
        with self.assertRaises(LotteryError): self.s.ingest('ssq',rows,{'test':True})
        self.assertEqual(self.s.db.execute('SELECT COUNT(*) FROM fetches').fetchone()[0],2)

    def test_recommend_review(self):
        rows=fixture(n=3);self.s.ingest('ssq',rows[:2],{'test':True})
        gen=generate('ssq',seed=8,history=rows[:2])
        rid=self.s.recommend('ssq','2025003',gen)['recommendation_id']
        with self.assertRaises(LotteryError): self.s.review(rid)
        self.s.ingest('ssq',rows[2:],{'test':True})
        result=self.s.review(rid)
        self.assertEqual(len(result['results']),5)
        self.assertEqual(result,self.s.review(rid))
        with self.assertRaises(LotteryError): self.s.recommend('ssq','2025002',gen)


class OfficialTests(unittest.TestCase):
    def raw(self, issue='2025001', day='2025-01-01'):
        return {'code':issue,'date':day+'(三)','red':'01,02,03,04,05,06','blue':'01','detailsLink':'/test',
                'prizegrades':[{'type':1,'typemoney':'1,000'},{'type':7,'typemoney':''}]}
    def test_ssq_parse(self):
        d=parse_row('ssq',self.raw())
        self.assertEqual(d['prizes']['1'],'1000')
        self.assertFalse(d['special'])
    def test_bad_parse(self):
        r=self.raw();r['red']='01,01,02,03,04,05'
        with self.assertRaises(LotteryError): parse_row('ssq',r)
        with self.assertRaises(LotteryError): money('NaN')
    def test_dlt_promotion_separation(self):
        raw={'lotteryGameNum':'85','verify':1,'lotteryDrawNum':'26066','lotteryDrawTime':'2026-06-15',
             'lotteryDrawResult':'01 02 03 04 05 01 02','prizeLevelList':[
             {'awardType':0,'prizeLevel':'三等奖','stakeAmountFormat':'6666'},
             {'awardType':1,'prizeLevel':'三等奖派奖','stakeAmountFormat':'3333'}]}
        self.assertEqual(parse_row('dlt',raw)['prizes']['3'],'6666')
    def test_fetch_validates(self):
        payload={'state':0,'total':2,'pageNo':1,'result':[self.raw('2025002','2025-01-03'),self.raw()]}
        rows,prov=fetch('ssq',getter=lambda *args:payload)
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['issue'],'2025001')
        with self.assertRaises(LotteryError): fetch('ssq',end='2025003',getter=lambda *args:payload)
        payload['result'][0]['code']='2025003'
        with self.assertRaises(LotteryError): fetch('ssq',getter=lambda *args:payload)
    def test_no_fabrication(self):
        with self.assertRaises(LotteryError): fetch('ssq',getter=lambda *args:{'state':1})
        with patch('urllib.request.urlopen',side_effect=urllib.error.URLError('offline')),patch('time.sleep'):
            with self.assertRaises(LotteryError): request_json('https://www.cwl.gov.cn/test','https://www.cwl.gov.cn/')


if __name__=='__main__': unittest.main()
