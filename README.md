# AgentBudget

本机 **Agent 额度**小工具：主视图只保留 Cursor API、Cursor Models 与 Codex 周额度三项；今日各项消费与两份订阅周期按需展开。

> Ubuntu 桌面应用（`.deb`）：浮在桌面的窗口，或钉在 GNOME 顶栏，不必打开 Cursor 或 Codex。

登录态和用量**只留在这台电脑**。公开仓库是纯工具代码，不含账号、token、邮箱或个人消费明细。

> 1.x 叫 CursorBudget，只盯 Cursor 一家；现在同时盯 Cursor 与 Codex，故改名 AgentBudget。旧包会被新包自动替换，旧设置自动迁移。

---

## 两种显示模式

| 模式 | 做什么 |
|---|---|
| **窗口** | 三项主视图：**Cursor API**、**Cursor Models**、**Codex 周额度**；点「展开详情」看今日账目与订阅周期 |
| **顶栏** | 应用图标 + ` A 12% · C 34% · G 56%`（示例数字） |

三个百分比都取整到一个百分点，不带小数位。右键窗口或点顶栏条目，可在「窗口 / 顶栏」之间切换。

展开后的五行：

| 行 | 含义 |
|---|---|
| 今日 A | 今日 Other Models（API）池消费：占池比例 · 金额 · 笔数 |
| 今日 C | 今日 Cursor Models（Auto）池消费：占池比例 · 金额 · 笔数 |
| 今日 G | 今日 Codex 周额度消耗的百分点（订阅制，无金额） |
| Cursor 周期 | Cursor 计费周期起止 |
| Codex 周期 | ChatGPT / Codex 订阅周期起止 |

视觉说明见 [`design/INK-LEDGER.md`](design/INK-LEDGER.md)。

## 安装

需要 Ubuntu 22.04+（GTK 3）、本机已登录过 Cursor、系统有 `nodejs`。顶栏模式需要 GNOME AppIndicator（Ubuntu 默认开启）。

```bash
sudo apt install ./dist/agentbudget_2.0.0_all.deb
agentbudget
```

取数脚本兼容 Ubuntu 自带的 Node.js 12+（`apt install nodejs`）。

从源码跑：

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 python3-cairo nodejs
git clone https://github.com/Xukun-Cia/AgentBudget.git
cd AgentBudget
PYTHONPATH=. python3 -m agentbudget
```

打包 `.deb`：

```bash
./scripts/build-deb.sh
# → dist/agentbudget_<version>_all.deb
```

本地状态都在 `~/.config/agentbudget/`：`config.json`（主题、刷新间隔、显示模式等，无账号字段）、`codex-daily.json`（今日 G 的采样日账，只有百分比）。默认约 60 秒刷新。

## 用量口径

### Cursor

与 Cursor Dashboard 百分比条对齐。分母优先用官方 `totalSpend` + 三个百分比反推，硬编码仅作回退：

| 池 | 百分比分母（Ultra 档回退值） | 说明 |
|---|---|---|
| Other Models（API） | **$500** | 第三方模型（Claude / GPT / Gemini 等） |
| Cursor Models（Auto） | **$3000** | Auto / Composer / Grok / Vega 等 |

**今日窗口**是当天 9:00 → 次日 9:00，通宵那一段仍记在开工那天。今日账目按事件所属模型分进上面两个池，与 Dashboard 同一套归类；事件没拉全时该行会标「未拉全」。

### Codex

本机已登录官方 GPT App / Codex 时：

| 项 | 来源 | 说明 |
|---|---|---|
| 套餐 | `~/.codex/auth.json` 的 plan claim | 例如 Pro |
| 周额度 % | 主额度组中约 7 日的窗口 | 服务端按 1 个百分点步进 |
| 订阅周期 | id_token 里的 active_start / active_until | 只作日期，不写邮箱 |

**今日 G 只能在本机算出来。** 官方接口只给滚动窗口的已用比例，没有按天口径、也没有金额。所以每次刷新都把周额度百分比采样落到本地日账，今日消耗 = 今天窗口内的正增量之和；周窗口重置时，新读数整个计入当日。

若某天的第一次采样不是从 9:00 开始（比如中途才打开应用），这个数只能是下限，界面写成 `≥2%`；下限为 0 时写「—」，不装作当天没花。跨 9:00 时若采样没断过（前后两次不超过 15 分钟），基线会延续，那天就是准确值。

没有 Codex 登录态时，卡上仍留「Codex 周额度」一行并写明原因；Cursor 账本不受影响。网络超时、限流或服务端临时错误会自动重试一次；若仍失败，应用会把最近 15 分钟内的有效百分比标为「缓存值」继续显示（顶栏用 `~` 标记）。登录过期等非临时错误不会被缓存掩盖。

---

## 隐私红线

AgentBudget **没有云端账号，也不上传任何东西**。

| 数据 | 在哪 | 会不会进 GitHub |
|---|---|---|
| Cursor 登录 JWT | 本机 `~/.config/Cursor/User/globalStorage/state.vscdb`（Cursor 写入） | 否 |
| Codex 登录 JWT | 本机 `~/.codex/auth.json`（官方 GPT App / Codex 写入） | 否 |
| 用量请求 | 本机进程直连 `cursor.com` 与 `chatgpt.com`（与打开官网相同） | 否 |
| 桌面设置 | 本机 `~/.config/agentbudget/config.json` | 否 |
| 今日 G 日账 | 本机 `~/.config/agentbudget/codex-daily.json`，只有百分比与时间戳，文件 `0600` | 否 |
| 调试落盘 | 仅当 `AGENTBUDGET_DEBUG=1` 时写入递归脱敏后的 `~/.config/agentbudget/debug/`，目录 `0700`、文件 `0600` | 否（仓库外） |

桌面端通过 `lib/status-json.js` 取数，stdout **只有白名单汇总字段**，不含 token、邮箱、userId、accountId 或原始事件。HTTP 错误也不会回显可能包含账号信息的响应正文。

软依赖：长期不打开 Cursor，本地 JWT 可能过期，再登录一次即可。这是登录态新鲜度，不是必须挂着编辑器窗口。

公开仓库里**不应出现**：token、userId、邮箱、`probe-results.json`、`api-response.json`，或把个人用量写死在源码里。

---

## 要求

| 项 | 依赖 |
|---|---|
| 运行 | Python 3.8+、PyGObject、GTK 3、Node.js、本机 Cursor 登录态 |
| 今日 G | 本机 Codex 登录态；数值随应用运行时长积累 |

---

## 目录

```
AgentBudget/
├── agentbudget/           # Ubuntu 桌面应用（窗口 + 顶栏）
│   ├── app.py             # 卡片绘制与主控
│   ├── indicator.py       # GNOME 顶栏 StatusNotifierItem
│   ├── fetch.py           # 调 Node CLI，读脱敏快照
│   ├── fmt.py             # 两个界面共用的数字格式
│   └── settings.py
├── bin/agentbudget
├── data/agentbudget.desktop
├── design/                # Ink Ledger 视觉说明与预览
├── lib/                   # 取数逻辑（Node）
│   ├── status-json.js     # CLI，输出脱敏快照
│   ├── compute.js
│   ├── cursorApi.js
│   ├── gptApi.js          # 本机 Codex 登录态 + 周额度
│   ├── gptLedger.js       # 今日 G 的本机采样日账
│   ├── usageDetails.js    # 池额度反推与今日分桶
│   ├── dayWindow.js       # 9:00→9:00 日窗口
│   ├── localState.js
│   └── privacy.js
├── scripts/build-deb.sh   # 打 .deb
└── tests/
```

---

## 免责声明

使用 Cursor Dashboard 与 ChatGPT 的**非公开 API**，可能随官方更新失效。仅供个人使用，与 Cursor、OpenAI 官方均无关。

## License

MIT
