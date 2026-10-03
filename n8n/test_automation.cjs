const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const workflow = JSON.parse(fs.readFileSync('/workflows/01_healthcare_request_automation.json', 'utf8'));
const uuid = '3e99a5fd-d726-4b44-94cf-104a6ab9c001';
const run = json => new Function('$input', '$', workflow.nodes.find(n => n.name === 'Check processing response').parameters.jsCode)(
  {first: () => ({json})}, name => {
    assert.equal(name, 'Check backend response');
    return {first: () => ({json: {response_body: {request_uuid: uuid}}})};
  })[0].json;

test('all decisions preserve the persisted UUID and exclude raw data', () => {
  for (const decision of ['AUTO_PROCESS', 'HUMAN_REVIEW', 'REJECT']) {
    const result = run({statusCode: 200, body: {request_uuid: uuid, status: 'processed', system_decision: decision, request_text: 'private synthetic text'}});
    assert.equal(result.success, true);
    assert.equal(result.response_body.system_decision, decision);
    assert.equal(result.response_body.request_text, undefined);
  }
});
test('processing failures preserve UUID without reflecting upstream details', () => {
  for (const [input, expected] of [
    [{error: 'ETIMEDOUT synthetic_secret'}, 504], [{statusCode: 409}, 409],
    [{statusCode: 503}, 503], [{statusCode: 500}, 502],
    [{statusCode: 200, body: {request_uuid: 'wrong', status: 'processed', system_decision: 'AUTO_PROCESS'}}, 502],
    [{statusCode: 200, body: {request_uuid: uuid, status: 'processed', system_decision: 'INVALID'}}, 502],
  ]) {
    const result = run(input);
    assert.equal(result.response_status, expected);
    assert.equal(result.success, false);
    assert.equal(result.response_body.request_uuid, uuid);
    assert.equal(result.response_body.persisted, true);
    assert.ok(!JSON.stringify(result).includes('synthetic_secret'));
  }
});
test('routes backend decisions to display branches, with bounded HTTP calls and no credentials', () => {
  const rules = workflow.nodes.find(n => n.name === 'IF Decision').parameters.rules.values;
  assert.deepEqual(rules.map(r => r.outputKey), ['AUTO_PROCESS', 'HUMAN_REVIEW', 'REJECT']);
  assert.deepEqual(workflow.connections['IF Decision'].main.slice(0, 3).map(c => c[0].node), ['Complete', 'Review Queue', 'Reject']);
  for (const node of workflow.nodes.filter(n => n.type === 'n8n-nodes-base.httpRequest')) {
    assert.equal(node.retryOnFail, false);
    assert.ok(node.parameters.options.timeout <= 45000);
  }
  assert.ok(workflow.nodes.every(n => !n.credentials));
  assert.deepEqual(workflow.pinData, {});
  assert.equal(workflow.settings.saveDataSuccessExecution, 'none');
  assert.equal(workflow.settings.saveDataErrorExecution, 'none');
  assert.equal(workflow.settings.saveManualExecutions, false);
});
