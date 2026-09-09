import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import json
from .core import LotteryError, dump, digest, validate_history, validate_draw, issue_id, check
from . import VERSION


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path):
        path = Path(path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS fetches(id INTEGER PRIMARY KEY,game TEXT NOT NULL,created TEXT NOT NULL,hash TEXT NOT NULL,payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS draws(game TEXT NOT NULL,issue TEXT NOT NULL,day TEXT NOT NULL,payload TEXT NOT NULL,fetch_id INTEGER NOT NULL REFERENCES fetches(id),PRIMARY KEY(game,issue));
        CREATE TABLE IF NOT EXISTS strategies(id INTEGER PRIMARY KEY,game TEXT NOT NULL,mode TEXT NOT NULL,config TEXT NOT NULL,hash TEXT NOT NULL UNIQUE);
        CREATE TABLE IF NOT EXISTS recommendations(id INTEGER PRIMARY KEY,game TEXT NOT NULL,target TEXT NOT NULL,created TEXT NOT NULL,strategy_id INTEGER NOT NULL REFERENCES strategies(id),payload TEXT NOT NULL,additional INTEGER NOT NULL,version TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS reviews(recommendation_id INTEGER PRIMARY KEY REFERENCES recommendations(id),created TEXT NOT NULL,draw_hash TEXT NOT NULL,payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS backtests(id INTEGER PRIMARY KEY,created TEXT NOT NULL,game TEXT NOT NULL,config TEXT NOT NULL,payload TEXT NOT NULL,version TEXT NOT NULL);
        ''')

    def close(self):
        self.db.close()

    def history(self, game, before=None, window=None, start=None, end=None):
        rows = [json.loads(x[0]) for x in self.db.execute('SELECT payload FROM draws WHERE game=? ORDER BY issue', (game,))]
        start = issue_id(game, start) if start else None
        end = issue_id(game, end) if end else None
        if start and end and start > end:
            raise LotteryError('起始期号晚于结束期号')
        rows = [x for x in rows if (not start or x['issue'] >= start) and (not end or x['issue'] <= end)]
        if before:
            before = issue_id(game, before)
            rows = [x for x in rows if x['issue'] < before]
        if window is not None:
            if window < 1:
                raise LotteryError('window 必须为正数')
            rows = rows[-window:]
        return validate_history(game, rows)

    def draw(self, game, issue):
        row = self.db.execute('SELECT payload FROM draws WHERE game=? AND issue=?',
                              (game, issue_id(game, issue))).fetchone()
        if row is None:
            raise LotteryError('未找到官方开奖结果，请先 sync')
        return validate_draw(game, json.loads(row[0]))

    def ingest(self, game, rows, provenance):
        rows = validate_history(game, rows)
        if not rows:
            raise LotteryError('禁止保存空抓取结果')
        with self.db:
            # Corrections require an explicit investigation, never silently overwrite settled data.
            for row in rows:
                old = self.db.execute('SELECT payload FROM draws WHERE game=? AND issue=?', (game,row['issue'])).fetchone()
                if old:
                    previous = json.loads(old[0])
                    semantic = ('date','front','back','prizes','additional_prizes','special')
                    if any(previous.get(k) != row.get(k) for k in semantic):
                        raise LotteryError(f"官方记录与已存数据冲突：{row['issue']}；事务已回滚")
            fetch_id = self.db.execute('INSERT INTO fetches(game,created,hash,payload) VALUES(?,?,?,?)',
                (game,now(),digest(provenance),dump(provenance))).lastrowid
            inserted = 0
            for row in rows:
                cur = self.db.execute('INSERT OR IGNORE INTO draws VALUES(?,?,?,?,?)',
                    (game,row['issue'],row['date'],dump(row),fetch_id))
                inserted += cur.rowcount
        return {'inserted':inserted,'received':len(rows),'fetch_id':fetch_id,'first':rows[0]['issue'],'last':rows[-1]['issue'],
                'coverage':'仅所列范围；官方接口可能不提供自发行以来的全部历史'}

    def recommend(self, game, target, generated, additional=False):
        target = issue_id(game, target)
        if additional and game != 'dlt':
            raise LotteryError('双色球不支持追加')
        if self.db.execute('SELECT 1 FROM draws WHERE game=? AND issue>=?', (game,target)).fetchone():
            raise LotteryError('目标期已开奖或早于库中最新期；历史模拟请使用 backtest')
        if generated['history_last'] and generated['history_last'] >= target:
            raise LotteryError('推荐包含目标期或未来数据')
        strategy = {'game':game,'mode':generated['mode'],'config':generated['effective_config']}
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO strategies(game,mode,config,hash) VALUES(?,?,?,?)',
                (game,generated['mode'],dump(generated['effective_config']),digest(strategy)))
            sid = self.db.execute('SELECT id FROM strategies WHERE hash=?',(digest(strategy),)).fetchone()[0]
            rid = self.db.execute('INSERT INTO recommendations(game,target,created,strategy_id,payload,additional,version) VALUES(?,?,?,?,?,?,?)',
                (game,target,now(),sid,dump(generated),int(additional),VERSION)).lastrowid
        return {'recommendation_id':rid,'target':target,'cost_yuan':len(generated['tickets'])*(3 if additional else 2),**generated}

    def review(self, rid):
        rec = self.db.execute('SELECT * FROM recommendations WHERE id=?',(rid,)).fetchone()
        if rec is None:
            raise LotteryError('推荐记录不存在')
        draw = self.db.execute('SELECT payload FROM draws WHERE game=? AND issue=?',(rec['game'],rec['target'])).fetchone()
        if draw is None:
            raise LotteryError('目标期尚无官方开奖结果，请先 sync')
        draw = json.loads(draw[0])
        result = {'recommendation_id':rid,'results':[check(rec['game'],t,draw,bool(rec['additional'])) for t in json.loads(rec['payload'])['tickets']]}
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO reviews VALUES(?,?,?,?)',(rid,now(),digest(draw),dump(result)))
        return result

    def records(self):
        return [dict(r) | {'payload':json.loads(r['payload'])} for r in self.db.execute('SELECT * FROM recommendations ORDER BY id')]

    def save_backtest(self, game, config, result):
        with self.db:
            rid = self.db.execute('INSERT INTO backtests(created,game,config,payload,version) VALUES(?,?,?,?,?)',
                (now(),game,dump(config),dump(result),VERSION)).lastrowid
        return {'backtest_id':rid,**result}
