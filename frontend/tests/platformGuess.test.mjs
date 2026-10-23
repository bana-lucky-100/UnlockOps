import test from 'node:test'
import assert from 'node:assert/strict'
import { guessPlatforms } from '../src/lib/platformGuess.ts'
import { personaName } from '../src/lib/persona.ts'

test('문장에서 플랫폼 이름(영문·한글)을 찾는다', () => {
  assert.deepEqual(guessPlatforms('분석용 Snowflake 웨어하우스가 필요해요'), ['SNOWFLAKE'])
  assert.deepEqual(guessPlatforms('스노우플레이크 써야 해요'), ['SNOWFLAKE'])
  assert.deepEqual(guessPlatforms('코파일럿 좌석 필요해요'), ['GITHUB'])
  assert.deepEqual(guessPlatforms('태블로 대시보드 게시'), ['TABLEAU_CLOUD'])
})
test('브랜드 이름이 없을 때만 자원 단어로 추측하고, 여러 개면 모두 돌려준다', () => {
  assert.deepEqual(guessPlatforms('payment-core 저장소 쓰기 권한'), ['GITHUB'])
  assert.deepEqual(guessPlatforms('Jira 이슈를 Slack 채널에 공유'), ['JIRA', 'SLACK'])
  assert.deepEqual(guessPlatforms('권한이 필요해요'), [])
})
test('시연 이름은 화면에서만 페르소나로 바꾸고 모르는 이름은 그대로', () => {
  assert.equal(personaName('김개발(A)'), '김지성')
  assert.equal(personaName('송운영(A)'), '신형철')
  assert.equal(personaName('박팀장(B)'), '박팀장(B)')
  assert.equal(personaName(null), null)
})
