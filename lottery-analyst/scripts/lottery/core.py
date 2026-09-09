import hashlib
import json
import math
import random
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from . import VERSION

RULES = json.loads(Path(__file__).with_name('rules.json').read_text(encoding='utf-8'))
NOTICE = '历史统计不能预测随机开奖；任何选号策略均不保证或提高单注中奖概率。'


class LotteryError(ValueError):
    pass


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(dump(value).encode()).hexdigest()


def issue_id(game, value):
    s = str(value)
    if game not in RULES:
        raise LotteryError('未知彩种')
    if game == 'dlt' and re.fullmatch(r'\d{5}', s):
        s = '20' + s
    if not re.fullmatch(r'20\d{2}\d{3}', s) or not 1 <= int(s[-3:]) <= 200:
        raise LotteryError('期号必须为 YYYYNNN（大乐透亦接受 YYNNN）')
    if s < RULES[game]['first_issue']:
        raise LotteryError('期号早于彩种发行')
    return s


def ticket(game, front, back):
    if game not in RULES:
        raise LotteryError('未知彩种')
    result = {}
    for part, numbers in [('front', front), ('back', back)]:
        maximum, count = RULES[game][part]
        if (not isinstance(numbers, (list, tuple)) or len(numbers) != count
                or any(type(n) is not int or not 1 <= n <= maximum for n in numbers)
                or len(set(numbers)) != count):
            raise LotteryError(f'{game} {part} 需要 {count} 个不重复的 1..{maximum} 整数')
        result[part] = sorted(numbers)
    return result


def validate_draw(game, row):
    out = dict(row)
    out.update(ticket(game, row['front'], row['back']))
    out['issue'] = issue_id(game, row['issue'])
    try:
        if not isinstance(row['date'], str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', row['date']):
            raise ValueError('expected YYYY-MM-DD')
        day = date.fromisoformat(row['date'])
    except (TypeError, ValueError) as e:
        raise LotteryError('无效开奖日期') from e
    today = datetime.now(timezone(timedelta(hours=8))).date()
    if day > today or str(day.year) != out['issue'][:4]:
        raise LotteryError('开奖日期与期号年份冲突或处于未来')
    if out.get('special') is not None and type(out['special']) is not bool:
        raise LotteryError('特别规定状态必须为布尔值或未知')
    for field in ('prizes', 'additional_prizes'):
        amounts = out.get(field, {})
        if not isinstance(amounts, dict):
            raise LotteryError('奖金额必须为奖级到金额的映射')
        for tier, value in amounts.items():
            try:
                amount = Decimal(str(value))
                if not isinstance(tier, str) or not re.fullmatch('[1-9]', tier) or not amount.is_finite() or amount < 0:
                    raise InvalidOperation
            except (InvalidOperation, ValueError) as e:
                raise LotteryError('奖级或奖金格式异常') from e
    return out


def validate_history(game, rows):
    rows = sorted((validate_draw(game, x) for x in rows), key=lambda x: x['issue'])
    for prev, curr in zip(rows, rows[1:]):
        if curr['issue'] == prev['issue'] or curr['date'] <= prev['date']:
            raise LotteryError('重复期号或非递增开奖日期')
        a, b = prev['issue'], curr['issue']
        if a[:4] == b[:4] and int(b[-3:]) != int(a[-3:]) + 1:
            raise LotteryError(f'历史数据缺期：{a} -> {b}')
        if a[:4] != b[:4] and (int(b[:4]) != int(a[:4]) + 1 or b[-3:] != '001'):
            raise LotteryError('历史数据跨年不连续')
    return rows


def version(game, issue):
    issue = issue_id(game, issue)
    applicable = [v for v in RULES[game]['versions'] if v['start'] <= issue]
    if not applicable:
        raise LotteryError('该期历史奖级规则尚未验证；大乐透核奖/回测支持自 19019 期起')
    return applicable[-1]


def features(game, part, numbers):
    nums = sorted(numbers)
    odd = sum(n % 2 for n in nums)
    pairs = [[a, b] for a, b in zip(nums, nums[1:]) if b == a + 1]
    return {'sum': sum(nums), 'span': nums[-1] - nums[0], 'odd_even': [odd, len(nums)-odd],
            'consecutive_pairs': pairs, 'consecutive_count': len(pairs),
            'zones': [sum(lo <= n <= hi for n in nums) for lo, hi in RULES[game]['zones'][part]]}


def statistics(game, rows):
    rows = validate_history(game, rows)
    if not rows:
        raise LotteryError('无历史数据，不能计算统计')
    out = {'n': len(rows), 'first_issue': rows[0]['issue'], 'last_issue': rows[-1]['issue'],
           'history_hash': digest(rows), 'notice': NOTICE}
    for part in ('front', 'back'):
        maximum, count = RULES[game][part]
        freq = Counter(n for row in rows for n in row[part])
        omissions = {}
        for n in range(1, maximum+1):
            gap = next((i for i, row in enumerate(reversed(rows)) if n in row[part]), len(rows))
            omissions[n] = {'draws': gap, 'censored': gap == len(rows)}
        expected = len(rows)*count/maximum
        out[part] = {'frequency': {n: freq[n] for n in range(1, maximum+1)},
                     'omission': omissions, 'expected_frequency': expected,
                     'hot': [n for n in range(1, maximum+1) if freq[n] > expected],
                     'cold': [n for n in range(1, maximum+1) if freq[n] < expected],
                     'neutral': [n for n in range(1, maximum+1) if freq[n] == expected]}
    out['per_draw'] = [{'issue': row['issue'], **{p: features(game, p, row[p]) for p in ('front', 'back')}} for row in rows]
    return out


def strategy_config(game, mode, supplied=None):
    if game not in RULES:
        raise LotteryError('未知彩种')
    if supplied is not None and not isinstance(supplied, dict):
        raise LotteryError('策略配置必须是对象')
    if mode not in ('uniform', 'constrained', 'diverse'):
        raise LotteryError('未知选号模式')
    config = dict(supplied or {})
    allowed = {'sum_range', 'odd_range', 'max_consecutive', 'max_overlap', 'attempts'}
    if set(config) - allowed:
        raise LotteryError('未知策略配置字段：' + ','.join(set(config)-allowed))
    for key in ('sum_range', 'odd_range'):
        if key in config:
            v = config[key]
            if not isinstance(v, list) or len(v) != 2 or any(type(n) is not int for n in v) or not 0 <= v[0] <= v[1]:
                raise LotteryError(f'{key} 必须为非负整数闭区间')
    for key in ('max_consecutive', 'max_overlap', 'attempts'):
        if key in config and (type(config[key]) is not int or config[key] < 0):
            raise LotteryError(f'{key} 必须为非负整数')
    if not 1 <= config.get('attempts', 30000) <= 1000000:
        raise LotteryError('attempts 必须在 1..1000000')
    if mode == 'uniform' and set(config)-{'attempts'}:
        raise LotteryError('均匀随机模式不接受号码约束')
    if mode != 'diverse' and 'max_overlap' in config:
        raise LotteryError('max_overlap 仅适用于多样性模式')
    return config


def generate(game, mode='uniform', count=5, seed=None, history=None, config=None):
    if type(count) is not int or not 1 <= count <= 100:
        raise LotteryError('组数必须在 1..100')
    config = strategy_config(game, mode, config)
    history = validate_history(game, history or [])
    if mode == 'constrained' and not history:
        raise LotteryError('统计约束模式需要真实历史数据')
    effective = dict(config)
    if mode == 'constrained' and 'sum_range' not in effective:
        sums = sorted(sum(row['front']) for row in history)
        effective['sum_range'] = [sums[int((len(sums)-1)*.1)], sums[int((len(sums)-1)*.9)]]
    rng = random.Random(seed) if seed is not None else random.SystemRandom()
    selected, seen = [], set()
    for _ in range(effective.get('attempts', 30000)):
        t = {p: sorted(rng.sample(range(1, RULES[game][p][0]+1), RULES[game][p][1])) for p in ('front', 'back')}
        key = dump(t)
        if key in seen:
            continue
        f = features(game, 'front', t['front'])
        if any(k in effective and not effective[k][0] <= val <= effective[k][1]
               for k, val in [('sum_range', f['sum']), ('odd_range', f['odd_even'][0])]):
            continue
        if f['consecutive_count'] > effective.get('max_consecutive', 100):
            continue
        if mode == 'diverse' and any(sum(len(set(t[p]) & set(s[p])) for p in t) > effective.get('max_overlap', 2) for s in selected):
            continue
        selected.append(t)
        seen.add(key)
        if len(selected) == count:
            return {'tickets': selected, 'mode': mode, 'seed': seed, 'effective_config': effective,
                    'engine_version': VERSION, 'rules_hash': digest(RULES[game]),
                    'history_hash': digest(history), 'history_last': history[-1]['issue'] if history else None,
                    'jackpot_probability_per_ticket': f"1/{math.comb(*RULES[game]['front'])*math.comb(*RULES[game]['back'])}", 'notice': NOTICE}
    raise LotteryError('达到尝试上限，约束无法满足；未保存部分组合，请放宽约束')


def check(game, chosen, draw, additional=False):
    chosen = ticket(game, chosen['front'], chosen['back'])
    draw = validate_draw(game, draw)
    if additional and game != 'dlt':
        raise LotteryError('双色球不支持追加')
    hits = [len(set(chosen[p]) & set(draw[p])) for p in ('front', 'back')]
    key = '+'.join(map(str, hits))
    v = version(game, draw['issue'])
    tier = v['tiers'].get(key)
    if key in v.get('conditional', {}):
        if draw.get('special') is None:
            raise LotteryError('本期双色球特别规定状态未知，无法精确判断福运奖')
        tier = v['conditional'][key] if draw['special'] else None
    amount, reason = None, None
    if tier is None:
        amount = Decimal(0)
    else:
        raw = draw.get('prizes', {}).get(str(tier))
        if raw is not None:
            amount = Decimal(str(raw))
        else:
            reason = '缺少该期官方单注奖金，不能计算精确奖金'
        if additional and tier in (1, 2):
            extra = draw.get('additional_prizes', {}).get(str(tier))
            if extra is None:
                amount, reason = None, '缺少官方追加单注奖金'
            elif amount is not None:
                amount += Decimal(str(extra))
    return {'issue': draw['issue'], 'hits': hits, 'tier': tier, 'rule_version': v['id'],
            'amount_yuan': str(amount) if amount is not None else None, 'amount_note': reason,
            'scope': '单式基本/追加奖金；不含另行派奖、税费及实体票资格审查'}


def backtest(game, rows, mode='uniform', count=5, seed=0, window=100, warmup=30, config=None):
    rows = validate_history(game, rows)
    if window < 1 or warmup < 1 or len(rows) <= warmup:
        raise LotteryError('窗口/预热期无效或历史数据不足')
    records = []
    for i in range(warmup, len(rows)):
        train = rows[max(0, i-window):i]
        generated = generate(game, mode, count, seed+i, train, config)
        results = [check(game, t, rows[i]) for t in generated['tickets']]
        records.append({'target': rows[i]['issue'], 'train_first': train[0]['issue'],
                        'train_last': train[-1]['issue'], 'train_hash': digest(train),
                        'tickets': generated['tickets'], 'results': results})
    totals = Counter(str(r['tier']) for item in records for r in item['results'])
    return {'folds': records, 'tier_counts': dict(totals), 'cost_yuan': len(records)*count*2,
            'engine_version': VERSION, 'rules_hash': digest(RULES[game]),
            'payout_yuan': None if any(r['amount_yuan'] is None for x in records for r in x['results']) else
            str(sum((Decimal(r['amount_yuan']) for x in records for r in x['results']), Decimal(0))),
            'window': window, 'warmup': warmup, 'seed': seed, 'notice': NOTICE,
            'method': '逐期滚动；训练只含目标期之前记录；事后采集数据不能证明历史可得时间；策略未自动调参'}
