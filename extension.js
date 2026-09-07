const vscode = require('vscode');
const { fetchAndCompute } = require('./lib/compute');
const { buildTooltipLines, fmtPct, fmtGptPct } = require('./lib/usageDetails');
const { reloadHolidayData } = require('./lib/workdays');

let statusBarDaily;
let statusBarUsed;
let statusBarGpt;
let refreshTimer;
let cachedData = null;

function getConfig() {
  const cfg = vscode.workspace.getConfiguration('cursorBudget');
  return {
    refreshInterval: cfg.get('refreshIntervalSeconds', 60),
    showInStatusBar: cfg.get('showInStatusBar', true),
    warningThreshold: cfg.get('warningThresholdPercent', 80),
    criticalThreshold: cfg.get('criticalThresholdPercent', 95),
  };
}

async function updateConfig(key, value) {
  const cfg = vscode.workspace.getConfiguration('cursorBudget');
  await cfg.update(key, value, vscode.ConfigurationTarget.Global);
}

async function loadSnapshot() {
  const config = getConfig();
  return fetchAndCompute({
    refreshInterval: config.refreshInterval,
    warningThreshold: config.warningThreshold,
    criticalThreshold: config.criticalThreshold,
  });
}

function usageIcon(percent, warning, critical) {
  if (percent >= critical) return '$(flame)';
  if (percent >= warning) return '$(warning)';
  return '$(pulse)';
}

function updateStatusBar(data) {
  const items = [statusBarUsed, statusBarDaily, statusBarGpt];
  if (items.some((item) => !item)) return;

  const config = getConfig();
  if (!config.showInStatusBar) {
    items.forEach((item) => item.hide());
    return;
  }

  const tooltip = buildTooltipLines(data);

  if (data.error) {
    const short = data.error.slice(0, 28);
    statusBarUsed.text = `$(warning) ${short}`;
    statusBarDaily.hide();
    statusBarUsed.tooltip = [data.error, data.fetchError || ''].filter(Boolean).join('\n');
    statusBarUsed.command = 'cursorBudget.quickMenu';
    statusBarUsed.show();
    const gpt = data.gpt || {};
    if (gpt.ok) {
      statusBarGpt.text = `$(globe) G ${fmtGptPct(gpt.percent)}`;
      statusBarGpt.tooltip = tooltip;
      statusBarGpt.command = 'cursorBudget.quickMenu';
      statusBarGpt.show();
    } else {
      statusBarGpt.hide();
    }
    return;
  }

  const icon = usageIcon(data.apiPercent, data.warningThreshold, data.criticalThreshold);

  statusBarUsed.text = `${icon} API ${fmtPct(data.apiPercent)}`;
  statusBarDaily.text = `$(graph) Cursor ${fmtPct(data.summary && data.summary.autoPercentUsed)}`;
  const gpt = data.gpt || {};
  if (gpt.ok) {
    statusBarGpt.text = `$(globe) G ${fmtGptPct(gpt.percent)}`;
    statusBarGpt.show();
  } else {
    statusBarGpt.text = '$(globe) G —';
    statusBarGpt.show();
  }

  for (const item of items) {
    item.tooltip = tooltip;
    item.command = 'cursorBudget.quickMenu';
    item.show();
  }
}

function buildQuickPickItems() {
  const config = getConfig();
  return [
    {
      label: '$(globe) 打开 Cursor 用量 Dashboard',
      description: 'cursor.com/dashboard/usage',
      id: 'dashboard',
    },
    {
      label: '$(globe) 打开 GPT 用量页',
      description: 'chatgpt.com settings',
      id: 'gptDashboard',
    },
    {
      label: '$(watch) 设置刷新间隔（秒）',
      description: `当前: ${config.refreshInterval} 秒`,
      id: 'refreshInterval',
    },
    {
      label: '$(sync) 立即刷新',
      description: (cachedData && cachedData.usageSource) || '',
      id: 'refresh',
    },
  ];
}

async function promptRefreshInterval(currentValue) {
  const input = await vscode.window.showInputBox({
    title: '设置刷新间隔',
    prompt: '状态栏自动刷新间隔（秒），最小 10',
    value: String(currentValue),
    validateInput: (v) => {
      const n = Number(v);
      if (isNaN(n) || n < 10) return '请输入不小于 10 的整数';
      if (!Number.isInteger(n)) return '请输入整数秒数';
      return null;
    },
  });
  if (input === undefined) return undefined;
  return Number(input);
}

async function showQuickMenu() {
  const picked = await vscode.window.showQuickPick(buildQuickPickItems(), {
    title: 'CursorBudget',
    placeHolder: '选择操作',
  });
  if (!picked) return;

  const config = getConfig();

  switch (picked.id) {
    case 'dashboard':
      vscode.env.openExternal(vscode.Uri.parse('https://cursor.com/dashboard/usage'));
      break;
    case 'gptDashboard':
      vscode.env.openExternal(vscode.Uri.parse('https://chatgpt.com/#settings/Usage'));
      break;
    case 'refreshInterval': {
      const val = await promptRefreshInterval(config.refreshInterval);
      if (val === undefined) return;
      await updateConfig('refreshIntervalSeconds', val);
      break;
    }
    case 'refresh': {
      reloadHolidayData();
      await refresh();
      vscode.window.showInformationMessage('CursorBudget: 已刷新');
      break;
    }
  }
}

async function refresh() {
  try {
    cachedData = await loadSnapshot();
    updateStatusBar(cachedData);
  } catch (err) {
    if (statusBarUsed) {
      statusBarUsed.text = '$(error) Budget Error';
      statusBarUsed.tooltip = String(err);
      statusBarUsed.command = undefined;
      statusBarUsed.show();
    }
    if (statusBarDaily) statusBarDaily.hide();
    if (statusBarGpt) statusBarGpt.hide();
  }
}

function startTimer() {
  stopTimer();
  const interval = getConfig().refreshInterval * 1000;
  refreshTimer = setInterval(() => refresh(), interval);
}

function stopTimer() {
  if (refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
}

function createStatusBarItem(context, priority) {
  const item = vscode.window.createStatusBarItem(
    vscode.StatusBarAlignment.Left,
    priority,
  );
  context.subscriptions.push(item);
  return item;
}

function activate(context) {
  // VS Code: higher priority = further left
  statusBarUsed = createStatusBarItem(context, -98);
  statusBarDaily = createStatusBarItem(context, -99);
  statusBarGpt = createStatusBarItem(context, -100);

  context.subscriptions.push(
    vscode.commands.registerCommand('cursorBudget.refresh', async () => {
      reloadHolidayData();
      await refresh();
      vscode.window.showInformationMessage('CursorBudget: 已刷新');
    }),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('cursorBudget.openDashboard', () => {
      vscode.env.openExternal(vscode.Uri.parse('https://cursor.com/dashboard/usage'));
    }),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('cursorBudget.quickMenu', showQuickMenu),
  );

  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration('cursorBudget')) {
        startTimer();
        refresh();
      }
    }),
  );

  refresh();
  startTimer();
}

function deactivate() {
  stopTimer();
  for (const item of [statusBarDaily, statusBarUsed, statusBarGpt]) {
    if (item) item.dispose();
  }
  statusBarDaily = null;
  statusBarUsed = null;
  statusBarGpt = null;
}

module.exports = { activate, deactivate };
