/** Where this machine keeps AgentBudget state. Never inside the repo. */
const os = require('os');
const path = require('path');

const APP_DIR_NAME = 'agentbudget';

function stateDir() {
  return (
    process.env.AGENTBUDGET_STATE_DIR
    || path.join(os.homedir(), '.config', APP_DIR_NAME)
  );
}

function debugDir() {
  return path.join(stateDir(), 'debug');
}

module.exports = { APP_DIR_NAME, stateDir, debugDir };
