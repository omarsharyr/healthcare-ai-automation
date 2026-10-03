// Exercise the exported workflow's own JavaScript, without external dependencies.
// Run inside the pinned n8n container (see docs/n8n-intake.md).
const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const workflow = JSON.parse(fs.readFileSync('/workflows/01_request_intake.json', 'utf8'));
const run = (name, json) => {
  const code = workflow.nodes.find(node => node.name === name).parameters.jsCode;
  return new Function('$input', code)({first: () => ({json})})[0].json;
};

test('normalization preserves values and unknown fields for FastAPI validation', () => {
  const input = {patient_reference: 'PAT-10042', request_text: 'short', priority: 'INVALID', unexpected: true};
  const normalized = run('Validate and normalize envelope', {body: input});
  assert.deepEqual(normalized.payload, {...input, source: 'n8n'});
  assert.equal(normalized.forward, true);
  for (const body of [null, [], 'synthetic', 42]) {
    assert.equal(run('Validate and normalize envelope', {body}).response_status, 400);
  }
});

test('backend success requires a real persisted acknowledgement and limits output', () => {
  const body = {request_uuid: '3e99a5fd-d726-4b44-94cf-104a6ab9c001', persisted: true, source: 'n8n', request_text: 'synthetic private text'};
  const response = run('Check backend response', {statusCode: 201, body});
  assert.equal(response.response_status, 201);
  assert.equal(response.success, true);
  assert.equal(response.response_body.request_text, undefined);
  assert.equal(run('Check backend response', {statusCode: 201, body: {persisted: false}}).response_status, 502);
});

test('validation, unavailable, transport and timeout failures produce safe errors', () => {
  const response = run('Check backend response', {statusCode: 422, body: {detail: [
    {loc: ['body', 'PAT-10042'], type: 'extra_forbidden', input: 'synthetic private text'},
  ]}});
  assert.equal(response.response_status, 422);
  assert.deepEqual(response.response_body.errors, [{field: 'body', type: 'extra_forbidden'}]);
  assert.equal(run('Check backend response', {statusCode: 503}).response_status, 503);
  for (const error of ['connect ECONNREFUSED synthetic_password', {message: 'connect ECONNREFUSED'}]) {
    const result = run('Check backend response', {error});
    assert.equal(result.response_status, 502);
    assert.ok(!JSON.stringify(result).includes('synthetic_password'));
  }
  for (const error of ['ETIMEDOUT', {message: 'timeout of 10000ms exceeded'}]) {
    assert.equal(run('Check backend response', {error}).response_status, 504);
  }
});

test('workflow disables retries and saved payloads and contains no credentials', () => {
  const http = workflow.nodes.find(node => node.type === 'n8n-nodes-base.httpRequest');
  assert.equal(http.retryOnFail, false);
  assert.equal(http.parameters.options.timeout, 10000);
  assert.equal(workflow.settings.saveDataSuccessExecution, 'none');
  assert.equal(workflow.settings.saveDataErrorExecution, 'none');
  assert.equal(workflow.settings.saveManualExecutions, false);
  assert.deepEqual(workflow.pinData, {});
  assert.ok(workflow.nodes.every(node => !node.credentials));
});
