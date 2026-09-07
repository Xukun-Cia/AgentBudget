# CursorBudget

本机 **Cursor + GPT 订阅日账**小工具：按中国法定工作日（每天 9:00–20:00 连续折算）看 Cursor 本周期还剩多少、今天花了多少；同时读本机 GPT App 登录态，展示 ChatGPT Pro 的周限额。

> **主产品是 Ubuntu 桌面应用**（`.deb`）：悬浮卡或钉在 GNOME 顶栏，不必打开 Cursor 窗口。  
> 同仓库另有可选的 **Cursor 编辑器配套**，方便在状态栏扫一眼；两者共用取数逻辑，互不依赖。

登录态和用量**只留在这台电脑**。公开仓库是纯工具代码，不含账号、token、邮箱或个人消费明细。

---

## 桌面应用（推荐）

### 两种显示模式

| 模式 | 做什么 |
|---|---|
| **悬浮卡** | Ink Ledger 日账：剩余工作日、**API 池**、**Cursor 池**、**GPT 周限**、今日 API、日估、套餐与周期 |
| **顶栏** | 应用图标 + `API累计% ※ 今日API% · G 周限%`（例如 `67.09% ※ 3.93% · G 0.00%`） |

右键卡片或点顶栏条目，可在「悬浮卡 / 顶栏」之间切换。

视觉说明见 [`design/INK-LEDGER.md`](design/INK-LEDGER.md)。

### 安装

需要 Ubuntu 22.04+（GTK 3）、本机已登录过 Cursor、系统有 `nodejs`。顶栏模式需要 GNOME AppIndicator（Ubuntu 默认开启）。

```bash
curl -LO https://github.com/Xukun-Cia/CursorBudget/releases/download/v1.1.0/cursorbudget_1.1.0_all.deb
sudo apt install ./cursorbudget_1.1.0_all.deb
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
| 套餐 | `~/.codex/auth.json` 的 plan claim + `/backend-api/wham/usage` | 例如 Pro |
| 周限 % | `rate_limit.primary_window.used_percent` | 默认约 7 日窗，到点重置 |
| 订阅周期 | id_token 里的 active_start / active_until | 只作日期，不写邮箱 |

没有 GPT 登录态时，卡上仍留「GPT 周限」一行，并写明原因；Cursor 账本不受影响。

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
| 调试落盘 | 仅当 `CURSORBUDGET_DEBUG=1` 时写入 `~/.config/cursorbudget/debug/` | 否（已 gitignore） |

桌面端通过 `lib/status-json.js` 取数，stdout **只有汇总数字**，不含 token / userId / 原始事件。

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

状态栏五项：日历（剩余日）· 波形（API%）· 历史（今日）· 图表（日估）· GPT 周限。  
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
