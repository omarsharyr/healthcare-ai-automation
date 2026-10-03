const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const trace = 'df1b40c1-bcdd-4fdd-950f-01f8fd000007';
const uuid = '3e99a5fd-d726-4b44-94cf-104a6ab9c001';
for (const filename of ['01_request_intake.json', '01_healthcare_request_automation.json', '02_agent_operations.json']) {
  test(filename + ': correlation survives response checking and HTTP forwarding', () => {
    const workflow = JSON.parse(fs.readFileSync('/workflows/' + filename, 'utf8'));
    for (const node of workflow.nodes.filter(n => n.type === 'n8n-nodes-base.httpRequest')) {
      assert.equal(node.parameters.sendHeaders, true);
      assert.equal(node.parameters.headerParameters.parameters[0].name, 'X-Correlation-ID');
      if (node.name === 'Process with AI') assert.ok(node.parameters.headerParameters.parameters[0].value.includes('Check backend response'));
      assert.equal(node.retryOnFail, false);
    }
    const name = filename.startsWith('02') ? 'Check agent response' : 'Check backend response';
    const node = workflow.nodes.find(n => n.name === name);
    const json = {headers: {'x-correlation-id':trace},statusCode: filename.startsWith('02') ? 200 : 201,
      body: {persisted:true,request_uuid:uuid,run_uuid:uuid,status:'completed',escalated:false,human_action_required:false,tools_used:[],results:[]}};
    const result = new Function('$input',node.parameters.jsCode)({first:()=>({json})})[0].json;
    assert.equal(result.correlation_id, trace);
    assert.equal(result.success, true);
  });
}
