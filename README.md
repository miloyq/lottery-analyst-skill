# Lottery Analyst Skill

[![Tests](https://github.com/miloyq/lottery-analyst-skill/actions/workflows/test.yml/badge.svg)](https://github.com/miloyq/lottery-analyst-skill/actions/workflows/test.yml)

为 Codex 提供双色球与大乐透的官方开奖统计、号码组合生成、推荐记录、核奖复盘和历史回测。所有计算由 Python 完成，数据保存于本地 SQLite。

**历史统计不能预测随机开奖，选号策略不保证或提高单注中奖概率。**

## 功能

- 官方数据同步：分页获取、号码与日期校验、缺期检测、重复与冲突保护，保留来源和原始响应。
- 历史统计：前后区分别计算频次、遗漏、冷热、连号、和值、跨度、奇偶比及三区分布。
- 三种组合模式：均匀随机、统计约束、多样性组合，默认五组。
- 推荐与复盘：保存目标期、策略、种子、版本和数据摘要，按目标期规则核对基本/追加奖。
- 滚动回测：每一期只用其之前的数据生成组合，记录训练范围、成本与核奖结果。

## 环境与平台

- Python **3.10+**，需包含标准库 SQLite 和 HTTPS 支持；无第三方运行依赖。
- 核心 CLI 面向 **Windows、macOS、Linux**，使用 pathlib 和标准库，不依赖 PowerShell。
- 使用 Skill 需安装 Codex；直接使用 CLI 不需要 Codex、OpenAI API Key 或付费数据接口。
- 自动化测试配置覆盖三个系统的 Python 3.10 / 3.14。各平台的实际通过状态以顶部 CI 链接为准；Codex 发现与官方网络访问仍取决于本机环境。

以下通用命令使用 `python`；macOS/Linux 若只有 `python3`，请替换命令前缀。

## 安装到 Codex

```sh
git clone https://github.com/miloyq/lottery-analyst-skill.git
cd lottery-analyst-skill
python --version
```

安装脚本的 `--destination` 是 **Skill 根目录**，脚本会在其中创建 `lottery-analyst/`。依据 [Codex 官方目录说明](https://learn.chatgpt.com/docs/build-skills)，用户级安装示例：

macOS / Linux：

```sh
python3 tools/install_skill.py --destination "$HOME/.agents/skills"
```

Windows PowerShell：

```powershell
python tools/install_skill.py --destination "$env:USERPROFILE/.agents/skills"
```

也可安装到目标项目的 `.agents/skills`。若当前 Codex 版本实际使用其他 Skill 根目录（例如已验证的 `.codex/skills`），传入该目录；不要在多个根目录重复安装同名 Skill。

安装完成后输入 `$lottery-analyst`。列表未刷新时重启 Codex。可选的发现检查需要 `codex` 命令位于 PATH：

```sh
python tools/verify_discovery.py
```

该辅助工具使用实验性 app-server 协议，输出去标识化检查摘要；不同 Codex 版本可能不兼容。安装脚本拒绝覆盖已有目录。升级时备份旧 Skill，再将其移出发现目录并安装新版；用户数据库存于工作目录，不随 Skill 安装目录移动。卸载时删除安装的 `lottery-analyst` 文件夹即可，数据库保留。

## 在 Codex 中使用

```text
使用 $lottery-analyst 获取双色球最近120期官方开奖，分析最近100期的频次与遗漏。
使用 $lottery-analyst 为我指定的大乐透目标期生成五组多样性组合并保存。
使用 $lottery-analyst 同步最新开奖，复盘推荐记录1。
使用 $lottery-analyst 回测大乐透，预热30期，训练窗口60期，随机种子42。
```

选号前需要明确目标期号；没有目标期时 Skill 会询问。不会自动购买彩票。

## 命令行使用

从项目根目录运行，无需先安装 Skill：

```sh
python lottery-analyst/scripts/lottery_cli.py sync --game ssq --limit 120
python lottery-analyst/scripts/lottery_cli.py stats --game ssq --window 100
python lottery-analyst/scripts/lottery_cli.py sync --game dlt --limit 120
python lottery-analyst/scripts/lottery_cli.py backtest --game dlt --warmup 30 --window 60 --seed 42
```

生成、核奖与复盘（先将 `TARGET_ISSUE`、`DRAW_ISSUE` 替换为实际期号）：

```sh
python lottery-analyst/scripts/lottery_cli.py generate --game ssq --target TARGET_ISSUE --mode uniform
python lottery-analyst/scripts/lottery_cli.py generate --game dlt --target TARGET_ISSUE --mode constrained --count 5
python lottery-analyst/scripts/lottery_cli.py generate --game dlt --target TARGET_ISSUE --mode diverse
python lottery-analyst/scripts/lottery_cli.py records
python lottery-analyst/scripts/lottery_cli.py review --id 1
python lottery-analyst/scripts/lottery_cli.py check --game dlt --issue DRAW_ISSUE --front 1 2 3 4 5 --back 1 2
```

示例号码仅演示参数，不是推荐。复盘前先同步到目标期开奖结果。期号接受 `YYYYNNN`，大乐透也接受 `YYNNN`。

| 子命令 | 用途 |
| --- | --- |
| `rules` | 查看号码范围与奖级版本 |
| `sync` | 获取官方数据；`--limit` 限定近期数量，`--start/--end` 限定范围 |
| `stats` | 统计最近 `--window` 期；`--before` 严格排除指定期及以后 |
| `generate` | 生成并保存；支持 `--mode`、`--count`、`--seed`、`--config` |
| `records` / `review` | 查看推荐或按推荐 ID 复盘 |
| `check` | 从库中读取指定期，核对一注号码；大乐透可加 `--additional` |
| `backtest` | 滚动回测，可设置范围、预热期与训练窗口 |

默认数据库为**当前工作目录**的 `lottery-data/lottery.sqlite3`。全局 `--db` 参数放在子命令前；建议持续操作始终指定同一个数据库：

```sh
python lottery-analyst/scripts/lottery_cli.py --db lottery-data/my-analysis.sqlite3 stats --game ssq
```

业务结果为 UTF-8 JSON。数据/操作错误写入 stderr 并返回退出码 2；`--help`、`--version` 和参数解析提示为普通文本。详细统计口径与策略配置见 [使用参考](lottery-analyst/references/usage.md)。

## 数据与限制

- 数据来自中国福彩网、国家体彩官方接口，详见 [来源与规则](lottery-analyst/references/sources.md)。网站可能限流、拒绝访问或改变字段，程序失败时明确报错，不用合成数据替代。
- 接口可查询数量不等于自发行以来全部历史；程序报告实际首末期。跨年尾期完整性不能只依靠期号证明。
- 大乐透核奖/回测支持 19019 期起；双色球支持基础奖级及 2026014 期起条件性福运奖。未核实的规则不推断。
- 仅支持单式基本/追加核奖，不处理复式/胆拖、倍数、派奖资格、税费及实体票有效性。缺少官方单注金额时返回 `null`。
- 特别规定状态未知时拒绝相关福运奖判断；已存记录冲突不自动覆盖。
- 回测保证按开奖期顺序隔离未来号码，不证明数据在历史时刻已可从网络获取。固定种子用于同一 Python 环境复现，不承诺跨 Python 版本逐注一致。
- 原始数据、推荐和诊断保留在本地且不纳入 Git；程序不上传这些数据。网络请求仅用于获取官方开奖。

## 测试与贡献

```sh
python -m unittest discover -s tests -v
python tools/smoke_test.py
```

测试完全离线；集成测试使用临时数据库和明确标注的合成数据，不需要预先下载开奖，也不修改日常数据。贡献流程见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

项目代码与文档采用 [MIT](LICENSE) 许可。该许可不授予第三方官方网站、标识或数据的额外权利。
