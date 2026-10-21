import { writeFile } from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

// Invoked only by MessageRetryIT with measurements from its isolated PostgreSQL and RabbitMQ containers.
let stdin = '';
for await (const chunk of process.stdin) stdin += chunk;
const input = JSON.parse(stdin);
const base = new URL(input.managementUrl);
if (base.protocol !== 'http:' || !['localhost', '127.0.0.1', '[::1]'].includes(base.hostname)) {
  throw new Error('Capture requires the local disposable broker');
}
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE
  ? pathToFileURL(process.env.PLAYWRIGHT_MODULE).href : 'playwright');
const authorization = `Basic ${Buffer.from(`${input.username}:${input.password}`).toString('base64')}`;
let queues;
const deadline = Date.now() + 20000;
while (Date.now() < deadline) {
  const response = await fetch(new URL('/api/queues/%2F', base), { headers: { authorization } });
  if (!response.ok) throw new Error(`Management metrics unavailable: ${response.status}`);
  queues = await response.json();
  const dead = queues.find(queue => queue.name === 'unlockops.dead');
  const results = queues.find(queue => queue.name === 'unlockops.results');
  if (dead?.messages_ready === input.deadReady && results?.messages_unacknowledged === 0) break;
  await new Promise(resolve => setTimeout(resolve, 300));
}
if (queues.find(queue => queue.name === 'unlockops.dead')?.messages_ready !== input.deadReady
    || queues.find(queue => queue.name === 'unlockops.results')?.messages_unacknowledged !== 0) {
  throw new Error('Broker metrics did not reach the asserted test state');
}

const evidence = {
  scenario: input.scenario,
  capturedAt: new Date().toISOString(),
  scope: 'Spring Backend / actual PostgreSQL / actual RabbitMQ; synthetic Agent result fixture',
  problemId: input.problemId,
  eventId: input.eventId,
  fault: input.fault,
  attempts: input.attempts,
  status: input.status,
  inboxEvents: input.inboxEvents,
  auditEvents: input.auditEvents,
  receipts: input.receipts,
  queues: queues.map(queue => ({
    name: queue.name, ready: queue.messages_ready, unacked: queue.messages_unacknowledged,
    total: queue.messages, consumers: queue.consumers,
  })),
};
const filename = name => path.join(input.output, `${input.scenario}-${name}`);
await writeFile(filename('evidence.json'), `${JSON.stringify(evidence, null, 2)}\n`);
const browser = await chromium.launch({ channel: 'chrome', headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
  await page.goto(base.href);
  await page.locator('input[name="username"]').fill(input.username);
  await page.locator('input[name="password"]').fill(input.password);
  await page.locator('input[type="submit"]').click();
  await page.locator('a[href="#/queues"]').first().waitFor();
  await page.goto(new URL('/#/queues', base).href);
  await page.getByRole('link', { name: 'unlockops.dead', exact: true }).waitFor();
  await page.screenshot({ path: filename('rabbitmq.png'), fullPage: true, animations: 'disabled' });

  const titles = {
    '01-transient-recovered': '일시 DB 오류 → 재시도 성공',
    '02-permanent-rejected': '완료 검증 위반 → 즉시 DLQ 격리',
    '03-transient-exhausted': '일시 DB 오류 지속 → 시도 소진 후 DLQ',
  };
  const escape = value => String(value).replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[character]);
  const metrics = [
    ['실제 처리 시도', evidence.attempts], ['요청 상태', evidence.status],
    ['동일 이벤트 inbox', evidence.inboxEvents], ['동일 이벤트 감사 이력', evidence.auditEvents],
    ['요청 실행 영수증', evidence.receipts], ['DLQ Ready', input.deadReady],
  ];
  const html = `<!doctype html><html lang="ko"><meta charset="utf-8">
    <title>RabbitMQ 재시도 실측 결과</title>
    <style>body{font:20px/1.6 system-ui,sans-serif;color:#172033;background:#f4f6fa;margin:0;padding:56px}
    main{background:#fff;padding:40px;max-width:1160px;margin:auto;border:1px solid #d6dce6}
    h1{font-size:32px;margin:8px 0 24px}p{margin:8px 0}code{font-size:17px;word-break:break-all}
    table{border-collapse:collapse;width:100%;margin-top:28px}td{padding:12px;border-bottom:1px solid #d6dce6}
    td:last-child{font-weight:600}.scope{font-size:16px;color:#45536b}</style>
    <main><p class="scope">일회용 환경 · Backend / PostgreSQL / RabbitMQ 통합 검증</p>
    <h1>${escape(titles[input.scenario] ?? input.scenario)}</h1>
    <p>요청 ID <code>${escape(evidence.problemId)}</code></p>
    <p>이벤트 ID <code>${escape(evidence.eventId)}</code></p>
    <p>주입 오류 <code>${escape(evidence.fault)}</code></p>
    <table>${metrics.map(([label, value]) => `<tr><td>${escape(label)}</td><td>${escape(value)}</td></tr>`).join('')}</table>
    <p class="scope">${escape(new Date(evidence.capturedAt).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' }))} KST</p>
    <p class="scope">Agent 결과는 테스트 fixture입니다. 실제 Python Agent/MCP 실행·권한 변경 증거와 구분합니다.<br>
    처리 횟수는 롤백에도 유지되는 PostgreSQL sequence로 측정했습니다.</p></main></html>`;
  await writeFile(filename('evidence.html'), html);
  await page.setContent(html);
  await page.screenshot({ path: filename('evidence.png'), fullPage: true, animations: 'disabled' });
  console.log(`Captured ${input.scenario}: dashboard and measured DB evidence`);
} finally {
  await browser.close();
}
