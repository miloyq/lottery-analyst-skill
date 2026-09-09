# 来源与限制

核实日期 2026-09-07。官方接口无公开 SLA，可能限流或改变字段。失败明确报错，不生成替代开奖。

- 双色球：`https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice`，name=ssq、pageNo/pageSize、systemType=PC。解析 result 的 code/date/red/blue/prizegrades。
- 大乐透：`https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry`，gameNo=85、provinceId=0、isVerify=1、pageNo/pageSize。解析 value.list，核验 lotteryGameNum/verify；奖表仅 awardType=0 进入基本/追加金额，派奖保留在 raw。
- [双色球规则（四川福彩）](https://www.scflcp.com.cn/yxgz/823145252.jhtml)及[生效公告（深圳福彩）](https://www.szlottery.org/fcw/fcxw/tzgg/content/post_1649773.html)：2026014 起特别规定期间 3+0 中福运奖。以当期官方第七奖级有无金额识别状态，字段缺失为未知，不能用开奖后奖池简单推断。
- [大乐透现行规则](https://m.lottery.gov.cn/ksjz/m/yxgz_dlt/)及[官方计算器](https://m.lottery.gov.cn/mltsz/jsq/index.html)：26014 起七奖级。
- [大乐透 2019 公告（重庆体彩）](https://www.cqtcw.net/h5/aritcle/1308502863290585088/h5/content_1308502863290585088.html)：19019 起九奖级。

独立配置位于 scripts/lottery/rules.json。大乐透 19019 之前规则尚未完整验证，核奖/回测拒绝，号码统计仍支持。金额只用当期发布奖表，避免套用当前奖金忽视封顶/限额赔付。双色球特别规定未知仅阻止相关 3+0 判断。

仅支持单式基本和大乐透追加核奖，不含复式/胆拖拆票、倍数、派奖资格、税费或实体票有效性。奖金缺失为未知。后续变更需官方核实并增加版本和边界测试。

接口 total 是可查询数量，并非完整发行历史。程序报告实际范围；跨年期号不能单独证明上一年尾期没有缺失。
