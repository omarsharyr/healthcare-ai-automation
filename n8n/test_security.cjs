const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
for (const filename of ['01_request_intake.json','01_healthcare_request_automation.json','02_agent_operations.json']) {
  test(filename + ': browser and media-type guards reject before FastAPI', () => {
    const workflow=JSON.parse(fs.readFileSync('/workflows/'+filename,'utf8'));
    const node=workflow.nodes.find(n=>['Validate envelope','Validate and normalize envelope'].includes(n.name));
    const run=headers=>new Function('$input',node.parameters.jsCode)({first:()=>({json:{headers,body:{message:'Synthetic message'}}})})[0].json;
    assert.equal(run({'content-type':'application/json',origin:'https://evil.example'}).response_status,403);
    assert.equal(run({'content-type':'application/json',origin:'null'}).response_status,403);
    assert.equal(run({'content-type':'application/x-www-form-urlencoded'}).response_status,415);
    const valid=run({'content-type':'application/json; charset=utf-8'});
    assert.equal(valid.valid ?? valid.forward,true);
    assert.ok(workflow.nodes.every(n=>!n.credentials));
    assert.ok(!workflow.nodes.some(n=>/executeCommand|readWriteFile|localFileTrigger/.test(n.type)));
  });
}
