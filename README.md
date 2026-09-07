# CursorBudget

本机 **Cursor + GPT 订阅额度**小工具：主视图只保留 Cursor API、Cursor Models 与 GPT 周额度三项；今日用量、日用建议、套餐周期及其他 GPT 限额按需展开。

> **主产品是 Ubuntu 桌面应用**（`.deb`）：悬浮卡或钉在 GNOME 顶栏，不必打开 Cursor 窗口。  
> 同仓库另有可选的 **Cursor 编辑器配套**，方便在状态栏扫一眼；两者共用取数逻辑，互不依赖。

登录态和用量**只留在这台电脑**。公开仓库是纯工具代码，不含账号、token、邮箱或个人消费明细。

---

## 桌面应用（推荐）

### 两种显示模式

| 模式 | 做什么 |
|---|---|
| **悬浮卡** | 三项主视图：**Cursor API**、**Cursor Models**、**GPT 周额度**；点击「展开详情」查看完整日账和其他 GPT 限额 |
| **顶栏** | 应用图标 + `A API% · C Cursor% · G GPT%`（例如 `A 9.46% · C 7.30% · G 1%`） |

右键卡片或点顶栏条目，可在「悬浮卡 / 顶栏」之间切换。

视觉说明见 [`design/INK-LEDGER.md`](design/INK-LEDGER.md)。

### 安装

需要 Ubuntu 22.04+（GTK 3）、本机已登录过 Cursor、系统有 `nodejs`。顶栏模式需要 GNOME AppIndicator（Ubuntu 默认开启）。

本地构建后的升级包可直接安装：

```bash
sudo apt install ./dist/cursorbudget_1.2.1_all.deb
cursorbudget
```

取数脚本兼容 Ubuntu 自带的 Node.js 12+（`apt install nodejs`）。

从源码跑：

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 python3-cairo nodejs
git clone https://github.com/Xukun-Cia/CursorBudget.git
cd CursorBudget
PYTHONPATH=. python3 -m cursorbudget
```

打包 `.deb`：

```bash
./scripts/build-deb.sh
# → dist/cursorbudget_<version>_all.deb
```

本地配置：`~/.config/cursorbudget/config.json`（主题、刷新间隔、显示模式等，无账号字段）。默认约 60 秒刷新。

### 用量口径

与 Cursor Dashboard 百分比条对齐。分母优先用官方 `totalSpend` + 三个百分比反推，硬编码仅作回退：

| 池 | 百分比分母（当前 Ultra 回退） | 说明 |
|---|---|---|
| Other Models（API） | **$500** | 第三方模型（Claude / GPT / Gemini 等） |
| Cursor Models（Auto） | **$3000** | Auto / Composer / Grok / Vega 等 |
| 合计 | **$3500** | 对应 `totalPercentUsed` |

`plan.limit`（Ultra 约 **$400**）是套餐 included 购买额度，和上面百分比条的分母不是同一口径。

**GPT / ChatGPT Pro**（本机已登录官方 GPT App 时）：

| 项 | 来源 | 说明 |
|---|---|---|
| 套餐 | `~/.codex/auth.json` 的 plan claim + ChatGPT 只读额度响应 | 例如 Pro |
| 周额度 % | 主额度组中约 7 日的窗口 | 当前服务端按 1 个百分点步进；界面不显示虚假的 `.00` |
| 其他限额 | 主额度组的短窗口及额外额度组的全部窗口 | 例如 Codex Spark 5 小时/周额度、Reserve 周额度 |
| 订阅周期 | id_token 里的 active_start / active_until | 只作日期，不写邮箱 |

没有 GPT 登录态时，卡上仍留「GPT 周额度」一行，并写明原因；Cursor 账本不受影响。解析器同时兼容当前 ChatGPT 用量响应与官方 app-server 的多额度结构，但不会为每次刷新另启 app-server，以避免和已登录桌面应用争用 refresh token。

网络超时、限流或服务端临时错误会自动重试一次；若仍失败，应用会把最近 15 分钟内的有效 GPT 百分比标为「缓存值」继续显示（顶栏用 `~` 标记）。登录过期等非临时错误不会被缓存掩盖。

- **今日窗口**：当天 9:00 → 次日 9:00  
- **日估**：剩余 API% ÷ 剩余折算工作日；最后不足 1 个工作日时按剩余全额计，且日估 + 已用 ≤ 100%

---

## 隐私红线

CursorBudget **没有云端账号，也不上传任何东西**。

| 数据 | 在哪 | 会不会进 GitHub |
|---|---|---|
| Cursor 登录 JWT | 本机 `~/.config/Cursor/User/globalStorage/state.vscdb`（Cursor 写入） | 否 |
| GPT 登录 JWT | 本机 `~/.codex/auth.json`（官方 GPT App / Codex 写入） | 否 |
| 用量请求 | 本机进程直连 `cursor.com` 与 `chatgpt.com`（与打开官网相同） | 否 |
| 桌面设置 | 本机 `~/.config/cursorbudget/config.json` | 否 |
| 调试落盘 | 仅当 `CURSORBUDGET_DEBUG=1` 时写入递归脱敏后的 `~/.config/cursorbudget/debug/`，目录 `0700`、文件 `0600` | 否（仓库外） |

桌面端通过 `lib/status-json.js` 取数，stdout **只有白名单汇总字段**，不含 token、邮箱、userId、accountId 或原始事件。HTTP 错误也不会回显可能包含账号信息的响应正文。

软依赖：长期不打开 Cursor，本地 JWT 可能过期，再登录一次即可。这是登录态新鲜度，不是必须挂着编辑器窗口。

公开仓库里**不应出现**：token、userId、邮箱、`probe-results.json`、`api-response.json`，或把个人用量写死在源码里。

---

## 可选：编辑器配套

若希望在 Cursor / VS Code 状态栏也看到同样摘要，可额外安装配套扩展（**不是**使用本工具的前提）：

```bash
git clone https://github.com/Xukun-Cia/CursorBudget.git
cd CursorBudget
bash install.sh
```

然后在编辑器里执行 **Developer: Reload Window**。  
`install.sh` 同步到 `~/.cursor/extensions/local.cursorbudget-<version>/`。

状态栏三项：Cursor API · Cursor Models · GPT 周额度。完整明细保留在提示与悬浮卡展开区。
设置里搜索 `cursorBudget`；命令面板有「立即刷新 / 打开用量页 / 快捷菜单」。

---

## 要求

| 场景 | 依赖 |
|---|---|
| **桌面应用** | Python 3.8+、PyGObject、GTK 3、Node.js、本机 Cursor 登录态 |
| 编辑器配套（可选） | Cursor 或 VS Code ≥ 1.85；系统有 `python3`（读本地 SQLite） |

---

## 目录

```
CursorBudget/
├── cursorbudget/          # Ubuntu 桌面应用（悬浮卡 + 顶栏）
├── bin/cursorbudget
├── data/cursorbudget.desktop
├── design/                # Ink Ledger 视觉说明与预览
├── lib/                   # 桌面与扩展共用的取数 / 日估
│   ├── compute.js
│   ├── status-json.js     # 桌面 CLI，脱敏快照
│   ├── cursorApi.js
│   ├── gptApi.js          # 本机 GPT App 登录态 + 周限额
│   ├── usageDetails.js
│   ├── workdays.js
│   └── holidays.json
├── extension.js           # 可选编辑器配套
├── package.json           # 配套扩展清单（非桌面安装入口）
├── install.sh             # 仅同步编辑器配套
├── scripts/build-deb.sh   # 打桌面 .deb
└── budget.py              # 旧终端脚本，口径过时，勿作主入口
```

---

## 免责声明

使用 Cursor Dashboard 的**非公开 API**，可能随 Cursor 更新失效。仅供个人使用，与 Cursor 官方无关。

## License

MIT
