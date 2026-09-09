"""Official website adapters. Never substitute synthetic/third-party results."""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation
from .core import LotteryError, issue_id, validate_history, validate_draw

ENDPOINTS = {
    'ssq': 'https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice',
    'dlt': 'https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry',
}
REFERERS = {'ssq': 'https://www.cwl.gov.cn/ygkj/wqkjgg/ssq/', 'dlt': 'https://m.lottery.gov.cn/'}


def money(value):
    if value in (None, '', '---', '-1'):
        return None
    try:
        n = Decimal(str(value).replace(',', ''))
        if not n.is_finite() or n < 0:
            raise InvalidOperation
        return str(n)
    except InvalidOperation as e:
        raise LotteryError('官方奖金字段格式异常') from e


def parse_row(game, raw):
    if game == 'ssq':
        prizes = {}
        for p in raw['prizegrades']:
            tier = str(p['type'])
            if tier in prizes:
                raise LotteryError('官方奖表包含重复奖级')
            prizes[tier] = money(p['typemoney'])
        # Explicit published prize table determines special-rule status; pool after draw does not.
        special = None
        if '7' in prizes:
            special = prizes['7'] is not None
        row = {'issue': raw['code'], 'date': raw['date'][:10],
               'front': [int(n) for n in raw['red'].split(',')], 'back': [int(raw['blue'])],
               'prizes': {k:v for k,v in prizes.items() if v is not None},
               'additional_prizes': {}, 'special': special,
               'detail_url': urllib.parse.urljoin('https://www.cwl.gov.cn', raw['detailsLink'])}
    else:
        if str(raw.get('lotteryGameNum')) != '85' or raw.get('verify') != 1:
            raise LotteryError('大乐透官方数据彩种错误或尚未确认')
        nums = [int(n) for n in raw['lotteryDrawResult'].split()]
        if len(nums) != 7:
            raise LotteryError('大乐透开奖号码数量异常')
        prizes, additional = {}, {}
        cn = '一二三四五六七八九'
        for p in raw['prizeLevelList']:
            if p.get('awardType') != 0:
                continue  # Promotions require ticket-level eligibility; retained in raw.
            name = p['prizeLevel']
            if name and name[0] in cn and '等奖' in name:
                target = additional if '追加' in name else prizes
                tier = str(cn.index(name[0])+1)
                value = money(p.get('stakeAmountFormat', p.get('stakeAmount')))
                if value is not None:
                    if tier in target and target[tier] != value:
                        raise LotteryError('官方奖表包含无法区分的重复奖级')
                    target[tier] = value
        row = {'issue': raw['lotteryDrawNum'], 'date': raw['lotteryDrawTime'][:10],
               'front': nums[:5], 'back': nums[5:], 'prizes': prizes, 'additional_prizes': additional,
               'special': None, 'detail_url': raw.get('drawPdfUrl')}
    row['raw'] = raw
    return validate_draw(game, row)


def request_json(url, referer, timeout=20):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': referer, 'Accept': 'application/json'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                if urllib.parse.urlparse(response.url).hostname != urllib.parse.urlparse(url).hostname:
                    raise LotteryError('官方接口重定向至其他域名，已停止')
                body = response.read(20_000_001)
                if len(body) > 20_000_000:
                    raise LotteryError('官方响应超出大小限制')
                return json.loads(body.decode('utf-8-sig'))
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise LotteryError(f'官方数据获取失败：HTTP {e.code} {url}；未生成替代数据') from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt == 2:
                raise LotteryError(f'官方数据获取失败：{e}；未生成替代数据') from e
        except (UnicodeError, json.JSONDecodeError) as e:
            raise LotteryError('官方接口未返回有效 UTF-8 JSON（可能被限流/拦截）；未生成替代数据') from e
        time.sleep(attempt+1)


def fetch(game, start=None, end=None, limit=None, getter=request_json):
    start = issue_id(game, start) if start else None
    end = issue_id(game, end) if end else None
    if start and end and start > end:
        raise LotteryError('起始期号晚于结束期号')
    if limit is not None and not 1 <= limit <= 20000:
        raise LotteryError('limit 必须在 1..20000')
    collected, pages, total, urls = [], [], None, []
    for page in range(1, 1001):
        params = ({'name':'ssq', 'pageNo':page, 'pageSize':100, 'systemType':'PC'} if game == 'ssq' else
                  {'gameNo':85, 'provinceId':0, 'pageNo':page, 'pageSize':100, 'isVerify':1})
        url = ENDPOINTS[game] + '?' + urllib.parse.urlencode(params)
        payload = getter(url, REFERERS[game])
        try:
            if game == 'ssq':
                if payload['state'] != 0:
                    raise LotteryError('福彩接口报告失败')
                items, reported, current = payload['result'], int(payload['total']), int(payload['pageNo'])
            else:
                if payload['success'] is not True:
                    raise LotteryError('体彩接口报告失败')
                val = payload['value']
                items, reported, current = val['list'], int(val['total']), int(val['pageNo'])
            if current != page or not isinstance(items, list) or not items or reported <= 0 or (total is not None and total != reported):
                raise LotteryError('分页为空/错位或抓取期间总数变化，请重试')
            if len(items) > 100 or len(collected) + len(items) > reported:
                raise LotteryError('分页记录数与官方总数不一致')
            total = reported
            batch = [parse_row(game, x) for x in items]
        except (KeyError, TypeError, ValueError) as e:
            raise LotteryError(f'官方响应校验失败：{e}') from e
        if batch != sorted(batch, key=lambda x:x['issue'], reverse=True):
            raise LotteryError('官方分页排序异常')
        if collected and collected[-1]['issue'] <= batch[0]['issue']:
            raise LotteryError('官方分页重复或倒序')
        collected.extend(batch)
        pages.append(payload)
        urls.append(url)
        selected = [r for r in collected if (not start or r['issue'] >= start) and (not end or r['issue'] <= end)]
        if len(collected) >= total or (start and batch[-1]['issue'] <= start) or (limit and len(selected) >= limit):
            break
        time.sleep(.15)
    else:
        raise LotteryError('超过最大页数，历史抓取不完整')
    if limit:
        selected = selected[:limit]
    if not selected:
        raise LotteryError('官方接口没有所请求范围的开奖数据')
    rows = validate_history(game, selected)
    if start and not limit and rows[0]['issue'] != start:
        raise LotteryError('官方接口未覆盖请求起始期号')
    if end and rows[-1]['issue'] != end:
        raise LotteryError('官方接口未覆盖请求结束期号')
    return rows, {'urls':urls, 'pages':pages, 'reported_total':total,
                  'scope':'official_api_available_history', 'first':rows[0]['issue'], 'last':rows[-1]['issue']}
