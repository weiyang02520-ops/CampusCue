# CampusCue 发布流程

## 版本来源

CampusCue 产品版本以 `campuscue/__init__.py` 的 `__version__` 为准，前端 `campuscue/web/package.json` 与 `package-lock.json` 必须保持一致。AstrBot 底座版本独立记录在根 `pyproject.toml`，不要把两者混为一个版本号。

每次发布都要在 `CAMPUSCUE_CHANGELOG.md` 增加日期、用户可见变化、迁移要求、已知风险和回滚方式。正式版使用 `MAJOR.MINOR.PATCH`；不兼容的备份格式、配置或数据库迁移必须提升主版本并提供显式迁移器。

## 发布门禁

1. 从干净的 Python 3.12 环境安装依赖，执行全部 CampusCue 测试、AstrBot 入口测试、Ruff、`pip check`、前端 Node 测试、`npm audit` 和生产构建。
2. 在临时目录执行 `scripts/test_windows_installer.ps1`，覆盖首次安装、升级备份、过期文件清理、默认保留数据的卸载。
3. 用隔离数据库启动最新版，验证 loopback 监听、页面、API、完整备份和进程归属启停；不得在发布验证中使用真实用户数据库。
4. 运行 `scripts/package_campuscue_delivery.ps1` 和 `scripts/validate_campuscue_delivery.ps1`，再从验证脚本给出的临时解压目录复验安装器、测试和前端构建。
5. 记录源码 ZIP、外层交付 ZIP 和签名安装器的 SHA-256。发布后不得原地替换同版本文件；任何变化都必须提升版本并重新生成哈希。

## Windows 签名边界

当前双击安装入口是源码包内的批处理和 PowerShell 安装器，适合受控交付和评审，尚不等同于已签名的消费级安装器。批处理文件本身不能获得 Authenticode 信任；公开商业分发前应使用 MSIX、WiX 或 Inno Setup 生成单一安装器，并用受信任的 EV/OV 代码签名证书签名安装器与卸载器。

签名必须在所有构建和打包步骤之后完成。用 `signtool verify /pa /all /v` 验证证书链、时间戳和摘要算法，再在一台从未安装过 CampusCue 的标准 Windows 账户上确认 SmartScreen、安装、升级、卸载和“已安装的应用”行为。证书私钥只能保存在硬件令牌或受控签名服务中，不能进入源码包、CI 日志、`.env` 或项目状态记录。

没有可用证书时，不得伪造“已签名”声明。可以交付 `SHA256SUMS.txt` 供完整性核对，但哈希不能替代发布者身份签名。

## 外部验收边界

真实 QQ 接收/推送与火山方舟抽取必须使用专门的隔离账号、测试群和预算上限。验收数据不得来自真实班级群；日志和完整备份在交付给第三方前都要做人工隐私复核。
