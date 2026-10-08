# AgentBudget

Ubuntu 上的本机 Agent 额度监视器。窗口与 GNOME 顶栏只显示 **A · Cursor API** 和 **G · Codex 周额度**，展开后查看 **C · Cursor Models** 及两份订阅周期。

登录态与用量只留在本机；公开仓库只包含工具、测试和使用虚构数据生成的设计预览。

## 界面

| 位置 | 内容 |
|---|---|
| 窗口主界面 | A / G 已用百分比、额度刻度、各自的重置时间 |
| 展开详情 | C 本期已用百分比与金额；Cursor / Codex 订阅周期 |
| GNOME 顶栏 | ` A 12%  ·  G 56%`（虚构示例），缓存值以 `~` 标记 |

主数字取整到百分点。A 在 Cursor 计费周期结束时重置，G 在 Codex 周额度窗口结束时重置；**G 的周额度重置与订阅续费是两个不同时间**。

曜石、暖瓷两套主题；默认深色。右键打开设置，选择大小、缩放、刷新间隔、置顶及窗口 / 顶栏模式。左键拖动窗口；点击「展开详情」查看次要信息；Tab 聚焦后按空格或 Enter 展开，F5 刷新，菜单键打开右键菜单。

![窗口预览（虚构数据）](design/agentbudget-v2.1-preview.png)

[展开预览与设计说明](design/INK-LEDGER.md)

## 安装与运行

Ubuntu 22.04+、GTK 3、Node.js 12+。Cursor 和 Codex 必须在本机登录；顶栏模式需要 AppIndicator 扩展（Ubuntu 通常已启用）。

```bash
sudo dpkg -i ./dist/agentbudget_2.1.0_all.deb
agentbudget
```

全新系统若提示缺少依赖，执行 `sudo apt --fix-broken install`。旧版 CursorBudget 包会自动被替换，已有主题和显示偏好继续保留。

从源码运行：

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 python3-cairo nodejs
git clone https://github.com/Xukun-Cia/AgentBudget.git
cd AgentBudget
PYTHONPATH=. python3 -m agentbudget
```

本地构建与测试：

```bash
node tests/run-tests.js
TZ=Asia/Shanghai python3 tests/test_python.py
python3 scripts/render_card_preview.py
./scripts/build-deb.sh
```

构建会先运行隐私检查，输出 `dist/agentbudget_<version>_all.deb`。源码运行优先使用本仓库的取数脚本，避免误读系统安装的旧版脚本。

## 周期与额度来源

**Cursor**：读取本机编辑器登录态，直连官网摘要与备用用量接口。周期起止始终作为一对更新，当前有效周期优先，避免旧备用响应覆盖新周期。API 和 Models 的额度分母优先从官方百分比与总消费反推；Ultra 档回退值分别为 $500、$3000。

**Codex**：读取本机 `~/.codex/auth.json`，直连用量接口，选择主额度组的约七日窗口；重置时间由服务端提供。网络超时、限流或临时服务故障会重试一次，仍失败时可保留 15 分钟内的有效额度并标为缓存；登录失效不会被缓存掩盖。

**Codex 订阅周期的限制**：用量接口不提供账单周期，登录令牌中的订阅日期也可能过期。有效日期直接展示；过期后，仅在用量接口仍确认 Plus / Pro 套餐、原日期能识别为月付或年付时，按日历续期并标注 **「预计」**。推算保留月末及闰年锚点，不使用固定 30 天；不能判断时显示「暂不可用」。预计日期不代表已核实扣款，改套餐、暂停或修改账单日后应以官方账单为准。

新版不再拉取今日消费事件，也不再写今日 Codex 采样账本；旧版本地账本保留但不读取。Cursor 与 Codex 用量并行刷新，默认约 60 秒一次。

## 隐私

应用没有云端账号，也不上传数据至第三方服务器。请求仅发往 Cursor / OpenAI 自己的服务。

| 数据 | 保存位置 | GitHub / 安装包 |
|---|---|---|
| Cursor 登录态 | 本机 Cursor 的 `state.vscdb` | 不包含 |
| Codex 登录态 | 本机 `~/.codex/auth.json` | 不包含 |
| 桌面设置 | `~/.config/agentbudget/config.json` | 不包含 |
| 旧版今日账本 | `~/.config/agentbudget/codex-daily.json` | 不包含 |
| 可选调试记录 | 仓库外的 `~/.config/agentbudget/debug/` | 不包含 |

`lib/status-json.js` 仅输出白名单汇总字段，不输出令牌、邮箱、账号标识或原始事件。窗口不会启用调试落盘；手动设置 `AGENTBUDGET_DEBUG=1` 才会写入递归脱敏的诊断记录，目录权限 `0700`、文件 `0600`。

打包只从源码白名单复制文件。凭据、数据库、环境配置、个人设置、日志、开发代理目录及安装产物均不应进入 Git。设计预览由 `scripts/render_card_preview.py` 的虚构数据生成，不调用真实账号。

## 目录

- `agentbudget/`：GTK / Cairo 窗口、GNOME 顶栏、配置与快照解析。
- `lib/`：Cursor / Codex 数据请求、周期选择和续期推算、脱敏工具。
- `scripts/`：构建、隐私扫描、虚构数据预览及诊断工具。
- `tests/`：数据边界、周期回归、隐私与界面内容验证。
- `design/`：视觉说明与虚构数据预览。

使用 Cursor Dashboard 与 ChatGPT 的非公开接口，可能随官方更新失效。本项目与 Cursor、OpenAI 官方无关。

MIT License
