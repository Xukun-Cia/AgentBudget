# CursorBudget

本机日账：按**中国法定工作日**（9:00–20:00 连续折算）看 Cursor API 还剩多少、今天花了多少。

有两副面孔，互不依赖：

1. **Ubuntu 桌面应用**（`.deb`）— 悬浮卡或钉在 GNOME 顶栏，不需要打开 Cursor 窗口
2. **Cursor / VS Code 状态栏扩展** — 仍可装在编辑器里

登录态和用量**只留在这台电脑**。这个公开仓库是纯小工具，不含账号、token、邮箱或你的消费明细。

## 设计

不是系统监视器。卡片是一本竖着翻的日账：宣纸 / 砚台两色，左侧赭石书脊，用量用朱砂提醒。顶栏只留三个没有名称的数字。

| 表面 | 显示 |
|---|---|
| **顶栏** | `◔10.52  ▮44.99%  ◑2.81%` — 剩余工作日、本周期 API 用量、今日 API 用量。只有小图标和数字，没有中英名称 |
| **悬浮卡** | 完整日账：日估、Auto 池、套餐 included/bonus、计费周期、工作日时钟 |

右键（或点顶栏图标）可在「悬浮卡 / 顶栏」之间切换。

### 用量口径

与 Dashboard 百分比条对齐。分母优先用官方 `totalSpend` + 三个百分比反推，硬编码仅作回退：

| 池 | 百分比分母（当前 Ultra 回退） | 说明 |
|---|---|---|
| Other Models（API） | **$500** | 第三方模型（Claude / GPT / Gemini 等） |
| Cursor Models（Auto） | **$3000** | Auto / Composer / Grok / Vega |
| 合计 | **$3500** | 对应 `totalPercentUsed` |

`plan.limit`（Ultra 约 **$400**）是套餐 included 购买额度，和上面百分比条的分母不是同一口径。

今日窗口：当天 9:00 → 次日 9:00。日估 = 剩余 API% ÷ 剩余折算工作日；最后不足 1 个工作日时按剩余全额计，且日估 + 已用 ≤ 100%。

## 隐私红线

CursorBudget **没有云端账号，也不上传任何东西**。

| 数据 | 在哪 | 会不会进 GitHub |
|---|---|---|
| Cursor 登录 JWT | 本机 `~/.config/Cursor/User/globalStorage/state.vscdb`（Cursor 自己写的） | 否 |
| 用量请求 | 本机进程直连 `cursor.com`（和打开官网 Dashboard 一样） | 否 |
| 桌面设置 | 本机 `~/.config/cursorbudget/config.json`（主题、刷新间隔，无账号） | 否 |
| 调试落盘 | 仅当设置了 `CURSORBUDGET_DEBUG=1`，写到 `~/.config/cursorbudget/debug/` | 否（已 gitignore） |

公开仓库里**不应出现**：token、userId、邮箱、`probe-results.json`、`api-response.json`、把个人 token 数 / 用量% 写死在源码里。

桌面端通过 `lib/status-json.js` 取数，stdout **只有汇总数字**，不含 token / userId / 原始事件。

软依赖：长期不打开 Cursor，本地 JWT 可能过期，需要再登录一次让 Cursor 写回 token。这是登录态新鲜度，不是必须挂着编辑器窗口。

## 安装桌面版

需要 Ubuntu 22.04+（GTK 3）、已登录过 Cursor、系统有 `nodejs`。顶栏模式需要 GNOME AppIndicator（Ubuntu 默认开启）。

```bash
curl -LO https://github.com/Xukun-Cia/CursorBudget/releases/download/v1.0.2/cursorbudget_1.0.2_all.deb
sudo apt install ./cursorbudget_1.0.2_all.deb
cursorbudget
```

桌面取数脚本兼容 Ubuntu 自带的 Node.js 12+（`apt install nodejs`）。悬浮卡视觉遵循 **Ink Ledger**（`design/INK-LEDGER.md`）：单一衬线、对等双池、规则线下方留白。

或从源码：

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 python3-cairo nodejs
git clone https://github.com/Xukun-Cia/CursorBudget.git
cd CursorBudget
PYTHONPATH=. python3 -m cursorbudget
```

打包：

```bash
./scripts/build-deb.sh
# dist/cursorbudget_1.0.0_all.deb
```

配置在 `~/.config/cursorbudget/config.json`。默认 60 秒刷新。

## 安装编辑器扩展

```bash
git clone https://github.com/Xukun-Cia/CursorBudget.git
cd CursorBudget
bash install.sh
```

然后在 Cursor 里执行 **Developer: Reload Window**。`install.sh` 同步到 `~/.cursor/extensions/local.cursorbudget-<version>/`。

设置里搜索 `cursorBudget`：刷新间隔、是否显示状态栏、警告 / 严重阈值。

命令：`CursorBudget: Refresh` / `Menu` / `Open Dashboard`。

## 要求

- 桌面版：Python 3.8+、PyGObject、GTK 3、Node.js、本机已有 Cursor 登录态
- 扩展：Cursor 或 VS Code ≥ 1.85，系统有 `python3`（读本地 SQLite）

## 目录

```
CursorBudget/
├── cursorbudget/         # Ubuntu 桌面应用（日账卡片 + 顶栏）
├── bin/cursorbudget
├── data/cursorbudget.desktop
├── extension.js          # 编辑器扩展
├── package.json
├── install.sh
├── lib/
│   ├── compute.js        # 共享：取数 + 日估
│   ├── status-json.js    # 桌面端 CLI，只输出脱敏快照
│   ├── cursorApi.js      # 读本地 token，请求 Dashboard
│   ├── usageDetails.js
│   ├── workdays.js
│   └── holidays.json
├── scripts/build-deb.sh
└── budget.py             # 旧终端脚本，口径已过时
```

## 免责声明

使用 Cursor Dashboard 的**非公开 API**，可能随 Cursor 更新失效。仅供个人使用，与 Cursor 官方无关。

## License

MIT
