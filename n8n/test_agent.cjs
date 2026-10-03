const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const workflow = JSON.parse(fs.readFileSync('/workflows/02_agent_operations.json', 'utf8'));
const run = json => new Function('$input', workflow.nodes.find(n => n.name === 'Check agent response').parameters.jsCode)({first: () => ({json})})[0].json;
test('agent success and fallback preserve escalation and human action flags', () => {
  for (const escalated of [true, false]) {
    const result = run({statusCode:200, body:{run_uuid:'f44ff046-b236-43bc-9625-83fcd1bce006',status:'fallback',escalated,human_action_required:true,tools_used:[],results:[],prompt:'synthetic private prompt'}});
    assert.equal(result.success, true);
    assert.equal(result.escalated, escalated);
    assert.equal(result.response_body.human_action_required, true);
    assert.equal(result.response_body.prompt, undefined);
  }
});
test('transport and validation errors do not reflect input or upstream secrets', () => {
  for (const [input,status] of [[{statusCode:422,body:{input:'private'}},422],[{error:'ETIMEDOUT synthetic-key'},504],[{statusCode:503},503],[{statusCode:200,body:{}},502]]) {
    const result = run(input);
    assert.equal(result.response_status,status);
    assert.ok(!JSON.stringify(result).includes('synthetic-key'));
  }
});
test('HTTP calls have no retries and exported workflow contains no credentials or pins', () => {
  const http = workflow.nodes.find(n => n.type === 'n8n-nodes-base.httpRequest');
  assert.equal(http.parameters.url, 'http://backend:8000/api/v1/agent/run');
  assert.equal(http.retryOnFail,false);
  assert.equal(http.parameters.options.timeout,45000);
  assert.deepEqual(workflow.connections['IF Escalated'].main.map(c => c[0].node),['Human Review','Return Result']);
  assert.equal(workflow.settings.saveDataSuccessExecution,'none');
  assert.equal(workflow.settings.saveDataErrorExecution,'none');
  assert.ok(workflow.nodes.every(n => !n.credentials));
  assert.deepEqual(workflow.pinData,{});
});
