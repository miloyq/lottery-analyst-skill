# 命令与口径

`python <Skill绝对路径>/scripts/lottery_cli.py --db <SQLite路径> <子命令>`。macOS/Linux 可使用 python3。全局参数在子命令之前。业务输出为 UTF-8 JSON，操作错误写 stderr、退出码 2；help/version 和参数解析提示为普通文本。默认数据库为当前工作目录下 `lottery-data/lottery.sqlite3`。

源项目 PowerShell 示例（安装后替换脚本路径）：

```powershell
$script = Join-Path (Get-Location) 'lottery-analyst/scripts/lottery_cli.py'
python $script sync --game ssq --limit 120
python $script sync --game dlt --limit 120
python $script stats --game ssq --window 100
python $script generate --game ssq --target TARGET_ISSUE --mode uniform
python $script generate --game ssq --target TARGET_ISSUE --mode constrained --seed 42
python $script generate --game dlt --target TARGET_ISSUE --mode diverse
python $script records
python $script check --game ssq --issue DRAW_ISSUE --front 1 2 3 4 5 6 --back 1
python $script review --id 1
python $script backtest --game dlt --mode constrained --warmup 30 --window 60 --seed 42
```

将 TARGET_ISSUE 替换为已明确的目标期，将 DRAW_ISSUE 替换为要核对的开奖期；示例号码只演示语法。已存在于库中的开奖期不允许新建推荐，review 在未抓取目标期结果时明确报错。macOS/Linux 也可直接用 `python3 /安装目录/lottery-analyst/scripts/lottery_cli.py` 运行相同子命令。

`sync` 默认遍历接口全部可用历史；`--start/--end` 是闭区间，要求指定边界有记录。与 `--limit` 合用时取范围内最近 N 期。检查分页顺序/重叠/总数变化、同年连续期号、跨年首期 001、日期递增及号码合法。不按每周固定天数判断缺期，以容纳休市/延期。

`stats --before YYYYNNN` 严格排除该期及以后；window 为最近 N 期。频次是号码出现期数。遗漏为样本末端连续未出现期数，本期出现为 0；整个样本未出现时 censored=true，仅代表下界。冷热以 N × 每期号码数 / 区内总号码数为理论期望，频次高于为热、低于为冷、等于为中性。逐期对两个区分别给出和值、跨度、奇偶数量、连号对和三区分布；1,2,3 有两个连号对。区间在 rules.json 配置。

## 策略

`--config file.json` 示例：

```json
{"sum_range":[80,130],"odd_range":[2,4],"max_consecutive":2,"attempts":30000}
```

均为前区约束；范围为闭区间。constrained 未给和值范围时，仅以训练窗口和值第 10%/90% 顺序统计量为界，对均匀候选拒绝采样。uniform 不接受号码约束，每区不放回均匀采样，注间不重复。diverse 默认任意两注前后区交集之和最多 2，可配置 max_overlap，并接受上述前区约束。改善组合覆盖不等于提高中奖率。组数 1..100，达到尝试上限整批失败，不保存部分组合。

## 保存与回测

SQLite 表 fetches 存时间、URL、完整响应及 SHA256；draws 以彩种+期号为主键；strategies 存有效配置；recommendations 存目标期、时间、种子、历史摘要、版本和追加状态；reviews 存核奖及开奖摘要；backtests 存逐期组合、配置及结果。生成和回测输出也包含引擎版本和规则配置摘要。固定种子用于同一 Python 环境复现，不保证不同 Python 版本产生完全相同号码。重复同步幂等，内容冲突事务回滚，不自动覆盖，需调查或另建数据库。

回测每期只以该期之前最多 window 期生成。start/end 截取后前 warmup 期用于预热。每期 seed=基准 seed+该期在截取数据中的下标，不自动调参。回测仅基本投注，每注 2 元；任一命中奖金缺失，总奖金就是 null。保存 train_first/train_last/train_hash 供审计。事后抓取的历史只能保证开奖顺序无未来号码泄漏，不能证明历史网络可得时间。参数应事先确定，不得事后挑最佳成绩作为未来承诺。
