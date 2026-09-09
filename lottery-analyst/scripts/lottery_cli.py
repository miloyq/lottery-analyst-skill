#!/usr/bin/env python3
"""Standard-library-only CLI; all successful output is JSON, errors exit 2."""
import argparse
import json
import sqlite3
import sys
from pathlib import Path
from lottery import VERSION
from lottery.core import LotteryError, RULES, NOTICE, statistics, generate, check, backtest, issue_id
from lottery.official import fetch
from lottery.storage import Store


def parser():
    p = argparse.ArgumentParser(description='双色球/大乐透历史分析与记录；不预测开奖')
    p.add_argument('--version', action='version', version=f'lottery-analyst {VERSION}')
    p.add_argument('--db', default='lottery-data/lottery.sqlite3', help='SQLite 路径，默认相对于当前工作目录')
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('rules')
    sub.add_parser('records')
    r = sub.add_parser('review'); r.add_argument('--id', type=int, required=True)
    for cmd in ('sync','stats','generate','check','backtest'):
        q = sub.add_parser(cmd)
        q.add_argument('--game', choices=RULES, required=True)
        if cmd == 'sync':
            q.add_argument('--start'); q.add_argument('--end'); q.add_argument('--limit',type=int)
        if cmd in ('stats','generate','backtest'):
            q.add_argument('--window',type=int,default=100)
        if cmd == 'stats':
            q.add_argument('--before', help='严格早于此期号')
        if cmd in ('generate','backtest'):
            q.add_argument('--mode',choices=['uniform','constrained','diverse'],default='uniform')
            q.add_argument('--count',type=int,default=5)
            q.add_argument('--seed',type=int,default=0 if cmd=='backtest' else None)
            q.add_argument('--config',type=Path,help='策略 JSON 文件')
        if cmd == 'generate':
            q.add_argument('--target',required=True)
            q.add_argument('--additional',action='store_true')
        if cmd == 'backtest':
            q.add_argument('--warmup',type=int,default=30)
            q.add_argument('--start'); q.add_argument('--end')
        if cmd == 'check':
            q.add_argument('--issue',required=True)
            q.add_argument('--front',type=int,nargs='+',required=True)
            q.add_argument('--back',type=int,nargs='+',required=True)
            q.add_argument('--additional',action='store_true')
    return p


def run(a):
    if a.command == 'rules':
        return {'rules':RULES,'notice':NOTICE}
    store = Store(a.db)
    try:
        config = json.loads(a.config.expanduser().read_text(encoding='utf-8-sig')) if getattr(a,'config',None) else None
        if config is not None and not isinstance(config,dict):
            raise LotteryError('策略配置必须是 JSON 对象')
        if a.command == 'sync':
            rows, source = fetch(a.game,a.start,a.end,a.limit)
            return store.ingest(a.game,rows,source)
        if a.command == 'stats':
            return statistics(a.game,store.history(a.game,a.before,a.window))
        if a.command == 'generate':
            target = issue_id(a.game,a.target)
            rows = store.history(a.game,target,a.window)
            result = generate(a.game,a.mode,a.count,a.seed,rows,config)
            return store.recommend(a.game,target,result,a.additional)
        if a.command == 'check':
            target = issue_id(a.game,a.issue)
            draw = store.draw(a.game, target)
            return check(a.game,{'front':a.front,'back':a.back},draw,a.additional)
        if a.command == 'backtest':
            rows = store.history(a.game, start=a.start, end=a.end)
            result = backtest(a.game,rows,a.mode,a.count,a.seed,a.window,a.warmup,config)
            settings = vars(a).copy(); settings['config'] = config
            return store.save_backtest(a.game,settings,result)
        if a.command == 'review':
            return store.review(a.id)
        return store.records()
    finally:
        store.close()


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    try:
        print(json.dumps(run(parser().parse_args()),ensure_ascii=False,indent=2))
    except (LotteryError, OSError, sqlite3.Error, json.JSONDecodeError, KeyError, TypeError) as e:
        print(json.dumps({'error':str(e)},ensure_ascii=False),file=sys.stderr)
        sys.exit(2)
