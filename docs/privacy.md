# 数据流与隐私

CLI 的 sync 子命令向中国福彩网或国家体彩官方接口请求开奖数据，不上传本地数据库、推荐号码或个人信息。核心程序不读取浏览器账户、Cookie 或 OpenAI 凭据。

默认数据库为当前工作目录下 lottery-data/lottery.sqlite3，保存官方原始响应、抓取时间、推荐、配置及复盘。自行选择的 --db 路径和配置路径可能出现在本地异常信息中，分享输出前应检查。

artifacts/ 用于本地诊断和构建产物，默认被 Git 忽略。tools/verify_discovery.py 会启动本机 Codex app-server，受本机 Codex 的配置和权限约束；保存的摘要不包含用户主目录、安装路径或原始服务端错误。不要把其他 Codex 运行日志直接上传到 Issue。

提交源码前检查暂存文件及 Git 作者/提交者邮箱。忽略规则不能阻止显式强制添加文件，也不能清除已进入历史的内容。如果误传实际凭据，应先撤销或轮换，再按 GitHub 官方流程处理历史和缓存。构建包与第三方数据应单独检查后再分发。

参考：[GitHub 敏感数据清理说明](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)。
