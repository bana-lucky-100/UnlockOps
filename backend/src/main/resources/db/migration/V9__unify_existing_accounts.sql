-- Move the original mock organisation onto the current workflow, without moving users
-- between tenants or changing passwords, budgets, old requests, or raw audit events.
-- Policy text is frozen from the supplied v1.1 corpus; later changes need a new revision.
INSERT INTO policy_revisions(policy_id,revision,company_id,doc_id,article,source_path,source_hash,content,is_mock)
SELECT md5('unlockops:existing:policy')::uuid,1,c.id,'EXISTING-POLICY','POL-01~08 / OFF / FLOW',
 'V9 / data/phase2/policies/company-a-policy-v3.md + data/company-a-access-matrix.md',
 '3cc7c49e261be79524b8cee2269ee51e8e2e5073fb207efffb05d4dc81b96386',$existing_policy$# 기존 시연 조직 — 통합 워크플로 정책 revision 1

원문: 제공된 RAG v1.1과 기존 직원·권한 표. 개별 문서 버전과 이 묶음 revision은 별개입니다.

## FLOW | COMMON | 1 | 현재 승인 경로

신규·재분석 요청은 부서장 → SaaS 담당자의 순차 승인을 모두 받습니다. 기존 단일 승인은 재사용하지 않습니다. 부서장은 departments.head_id, 시연 SaaS 담당자는 기존 문서에 명시된 song_ops입니다. 중복·본인 승인이나 누락된 담당자는 추측하지 않고 수동 검토합니다.

## POL-LEGACY | COMMON | 1 | 기존 조직의 권한 상한

기존 직원·권한 표의 직무·직급 상한을 유지합니다. GitHub 일반 저장소 Write와 Jira 일반 프로젝트 Developer는 개발 직무 대리 이상에게만 허용합니다. TF 전용 자원은 현재 TF 구성원 조건을 따릅니다. Notion 편집은 소속 부서 문서에 한해 대리 이상이며, 일반·TF·기밀 문서는 보기 권한만 신청할 수 있습니다. Copilot 단가는 기존 부서 예산표에서 이관하며 값이 서로 다르면 가격 확인을 요청합니다.

## POL-01 | COMMON | v1.1 | 제1조(목적)

문서: SaaS 권한 부여 기본 원칙

제1조(목적) 이 규정은 업무용 SaaS(Snowflake, Databricks, Salesforce, Datadog, Tableau Cloud, Figma, GitHub, Jira, Slack, Notion)의 접근 권한을 부여·변경·회수하는 기준을 정한다.

## POL-01 | COMMON | v1.1 | 제2조(최소 권한)

문서: SaaS 권한 부여 기본 원칙

제2조(최소 권한) 권한은 업무 수행에 필요한 최소 범위로 부여한다. 쓰기나 관리자 권한을 요청했어도 요청 사유가 읽기만으로 충분하면 읽기를 먼저 제안하고, 그 범위로 승인을 올린다. 요청한 상위 권한은 부여하지 않는다.

## POL-01 | COMMON | v1.1 | 제3조(부여 대상)

문서: SaaS 권한 부여 기본 원칙

제3조(부여 대상) TF 명단에 등재된 구성원은 해당 TF 전용 자원에 대해 SaaS별 기준(POL-03~05, POL-08~14)에 따라 권한을 받을 수 있다.

## POL-01 | COMMON | v1.1 | 제4조(승인)

문서: SaaS 권한 부여 기본 원칙

제4조(승인) 권한 부여는 회사 흐름 문서에 정한 승인 단계(예: 부서장 → IT 권한 관리)를 순서대로 모두 통과한 뒤에만 실행한다. 한 단계라도 반려하면 이후 단계는 진행하지 않고 권한을 부여하지 않는다. 요청자는 자신의 요청을 승인할 수 없다. 회사 흐름 문서에서 승인자를 찾을 수 없으면 승인자를 추측하지 않고 담당자 검토로 넘긴다.

## POL-01 | COMMON | v1.1 | 제5조(기록과 확인)

문서: SaaS 권한 부여 기본 원칙

제5조(기록과 확인) 부여한 권한은 사유와 근거 조항을 함께 기록하고, 부여 후 실제로 반영되었는지 다시 조회해 확인한다.

## POL-02 | COMMON | v1.1 | 제1조(구성원 자격)

문서: TF 구성원 권한 기준

제1조(구성원 자격) TF 구성원은 인사 발령 또는 TF 명단 등재로 확인한다. 구두 주장만으로는 구성원으로 인정하지 않는다.

## POL-02 | COMMON | v1.1 | 제2조(전용 자원)

문서: TF 구성원 권한 기준

제2조(전용 자원) TF 전용 자원은 TF 코드명으로 식별한다. 예: GitHub 저장소 `payment-*`, Jira 프로젝트 키 `PAY`, Slack 채널 `#proj-payment`, Notion 페이지 `[PAY] 결제 개편 TF 위키`, Figma 프로젝트 `[PAY] 결제 개편 TF`, Databricks 작업 공간 폴더 `reco-*`(추천 모델).

## POL-02 | COMMON | v1.1 | 제3조(비구성원)

문서: TF 구성원 권한 기준

제3조(비구성원) TF 구성원이 아닌 직원은 TF 전용 자원의 쓰기·참여 권한을 받을 수 없다. 먼저 TF 리더에게 구성원 등재를 요청하도록 안내한다.

## POL-02 | COMMON | v1.1 | 제4조(회수)

문서: TF 구성원 권한 기준

제4조(회수) TF가 종료되면 TF 전용 자원 권한은 회수 검토 대상이 된다. 유료 좌석의 회수 후보 기준과 점검 방식은 POL-06 제5조를 따른다. 회수 여부는 사람이 결정하며 자동 회수는 하지 않는다.

## POL-03 | GITHUB | v1.1 | 제1조(접근 단위)

문서: GitHub 접근 권한 기준

제1조(접근 단위) 저장소 접근은 개인 단위가 아니라 팀(Team) 멤버십으로 부여한다.

## POL-03 | GITHUB | v1.1 | 제2조(Write)

문서: GitHub 접근 권한 기준

제2조(Write) TF 전용 저장소의 Write 권한은 개발 직무인 TF 구성원에게 팀 멤버십(Write)으로 부여할 수 있다.

## POL-03 | GITHUB | v1.1 | 제3조(Read 우선)

문서: GitHub 접근 권한 기준

제3조(Read 우선) 개발 직무가 아닌 구성원은 Read 권한으로 제한한다.

## POL-03 | GITHUB | v1.1 | 제4조(Admin 금지)

문서: GitHub 접근 권한 기준

제4조(Admin 금지) Admin 권한은 자동 진단·부여 대상이 아니다. 보안팀의 별도 절차로만 처리한다. 다만 Admin을 요청했어도 요청 사유가 코드 열람뿐이면 POL-01 제2조에 따라 Read를 제안한다.

## POL-03 | GITHUB | v1.1 | 제5조(확인)

문서: GitHub 접근 권한 기준

제5조(확인) 부여 후 팀 멤버십과 저장소 권한을 다시 조회해 반영 여부를 확인한다.

## POL-04 | JIRA | v1.0 | 제1조(접근 단위)

문서: Jira 프로젝트 역할 기준

제1조(접근 단위) 프로젝트 접근은 프로젝트 역할(Role) 단위로 부여한다. 제품 접근 자격이 있어도 프로젝트 역할이 없으면 프로젝트가 보이지 않을 수 있다.

## POL-04 | JIRA | v1.0 | 제2조(Developer)

문서: Jira 프로젝트 역할 기준

제2조(Developer) 개발 직무인 TF 구성원에게 해당 프로젝트의 Developer 역할(이슈 조회·생성·편집·상태 변경)을 부여할 수 있다.

## POL-04 | JIRA | v1.0 | 제3조(Viewer)

문서: Jira 프로젝트 역할 기준

제3조(Viewer) 개발 직무가 아닌 구성원은 Viewer(조회) 역할을 기본으로 한다.

## POL-04 | JIRA | v1.0 | 제4조(Admin 금지)

문서: Jira 프로젝트 역할 기준

제4조(Admin 금지) Project Admin 역할은 자동 진단·부여 대상이 아니다.

## POL-05 | SLACK | v1.0 | 제1조(비공개 채널)

문서: Slack 채널 초대 기준

제1조(비공개 채널) TF 구성원은 해당 TF 전용 비공개 채널(`#proj-*`)의 초대 대상이다.

## POL-05 | SLACK | v1.0 | 제2조(비구성원)

문서: Slack 채널 초대 기준

제2조(비구성원) TF 구성원이 아닌 직원은 TF 전용 채널에 초대하지 않고 사유를 안내한다.

## POL-05 | SLACK | v1.0 | 제3조(외부 게스트)

문서: Slack 채널 초대 기준

제3조(외부 게스트) 외부 협력사 게스트 초대는 TF 리더와 IT 보안 담당의 승인이 모두 필요하다. (이번 시연 범위 밖, 확장)

## POL-06 | COMMON | v1.1 | 제1조(신청 대상)

문서: 유료 좌석·예산 기준

제1조(신청 대상) 유료 좌석이나 사용량 기반 권한은 해당 SaaS 권한표가 정한 허용 직군의 구성원만 신청할 수 있다. GitHub Copilot처럼 개발 전용으로 정한 좌석은 개발 직무 구성원만 신청할 수 있으며, 허용 직군이 아니면 요청을 거절한다.

## POL-06 | COMMON | v1.1 | 제2조(예산 확인)

문서: 유료 좌석·예산 기준

제2조(예산 확인) 좌석 1개의 월 비용 또는 사용량 기반 권한의 예상 월 비용(예: GitHub Copilot Business 좌석 월 19달러, GH-OFF-03)이 소속 부서의 잔여 월 예산 이하일 때만 승인을 올린다. 실제 단가는 회사 계약을 따르며, 각 SaaS의 공식 정가는 해당 공식 요약 문서(SN·DB·SF·DD·TB·FG-OFF-01)를 참고한다. 사용량 기반 비용은 권한표에 정한 가정값으로 계산한 예상 금액이며, 권한을 부여했다고 실제 사용료가 확정된 것은 아니다.

## POL-06 | COMMON | v1.1 | 제3조(예산 부족)

문서: 유료 좌석·예산 기준

제3조(예산 부족) 잔여 예산이 좌석 비용 또는 예상 비용보다 적으면 요청을 보류하고, 부서장에게 예산 증액을 요청하도록 안내한다. 예산이 확보되면 최신 규정과 예산으로 다시 검토한다. 추가 비용 없는 대안 권한이 SaaS 권한표에 있을 때만 함께 안내한다.

## POL-06 | COMMON | v1.1 | 제4조(중복)

문서: 유료 좌석·예산 기준

제4조(중복) 요청한 접근 권한을 이미 보유한 직원에게는 추가 부여 없이 현재 권한을 안내하고 완료한다. 이미 유료 좌석을 가진 직원이 같은 좌석을 다시 요청하면 중복 구매하지 않고 거절한다.

## POL-06 | COMMON | v1.1 | 제5조(회수 점검)

문서: 유료 좌석·예산 기준

제5조(회수 점검) (시연용 가정 기준) IT 권한 관리가 매일 09:00에 유료 좌석의 회수 후보를 점검한다. TF가 종료된 뒤 30일 이상 사용하지 않았고, 소속된 다른 TF가 없으며, 유효한 유지 승인이 없는 좌석은 회수 후보다. 퇴사한 직원이 보유한 유료 좌석도 회수 후보다. 다른 TF에 소속되어 있거나, 유지 승인이 있거나, 다시 사용하기 시작한 좌석은 후보에서 제외하고 제외 사유를 기록한다. 이미 알린 후보는 다시 알리지 않는다. 에이전트는 후보 선별과 알림까지만 하며, 회수는 사람이 결정한다.

## POL-07 | COMMON | v1.1 | 제1조(Admin 제외)

문서: Admin·보안 예외 기준

제1조(Admin 제외) Admin·Owner 권한 요청은 자동 부여 대상이 아니다. 요청을 거절하고 IT 보안팀 문의를 안내한다. 다만 요청 사유가 더 낮은 권한(예: 읽기)으로 충분하면 Admin·Owner는 부여하지 않고 POL-01 제2조에 따라 그 최소 권한을 제안한다.

## POL-07 | COMMON | v1.1 | 제2조(구두 승인 무효)

문서: Admin·보안 예외 기준

제2조(구두 승인 무효) "팀장이 허락했다"는 말은 승인 근거가 아니다. 시스템에 기록된 승인만 인정한다.

## POL-07 | COMMON | v1.1 | 제3조(근거 없는 요청)

문서: Admin·보안 예외 기준

제3조(근거 없는 요청) 규정에서 근거 조항을 찾을 수 없는 권한은 부여하지 않고 담당자 검토로 넘긴다.

## POL-08 | NOTION | v1.0 | 제1조(등급)

문서: Notion 문서 보안 등급 기준

제1조(등급) 문서는 일반·내부·기밀 3개 등급으로 나눈다.

## POL-08 | NOTION | v1.0 | 제2조(읽기)

문서: Notion 문서 보안 등급 기준

제2조(읽기) 일반 등급은 전 직원이 읽을 수 있다. 내부 등급은 소속 부서 또는 해당 TF 구성원에게 읽기(Can View)를 부여할 수 있다. 기밀 등급은 지정 부서만 읽을 수 있고, 지정 부서가 아니면 부여하지 않고 부서장 문의를 안내한다.

## POL-08 | NOTION | v1.0 | 제3조(편집)

문서: Notion 문서 보안 등급 기준

제3조(편집) 편집(Can Edit)은 소속 팀 정직원에게 부여할 수 있고, 승인은 POL-01 제4조에 따른다. 기밀 등급 문서는 부서장 승인이 추가로 필요하다. (이번 시연 범위 밖, 확장)

## POL-08 | NOTION | v1.0 | 제4조(전체 액세스 금지)

문서: Notion 문서 보안 등급 기준

제4조(전체 액세스 금지) 전체 액세스(Full access, 공유·권한 관리) 권한은 자동 진단·부여 대상이 아니다.

## GH-OFF-01 | GITHUB | 2026-10-19 | 핵심 요약

문서: GitHub 조직 저장소 역할 구분

GitHub 조직 저장소에는 다섯 가지 역할이 있다. Read는 코드를 직접 고치지 않고 보고 토론에 참여하는 사람용이다. Triage는 이슈·PR·디스커션을 정리할 수 있지만 코드를 push하거나 병합할 수 없다. Write는 저장소에 직접 push하고 PR을 병합할 수 있다. Maintain은 Write에 더해 저장소 설명·병합 방식 같은 관리 설정을 다루되 위험한 작업은 제외된다. Admin은 브랜치 보호, 팀·협력자 접근 관리, 저장소 삭제·이전, 공개 범위 변경 같은 민감한 작업까지 모두 할 수 있다. 역할은 조직 구성원, 외부 협력자, 팀에 부여할 수 있다.

## GH-OFF-01 | GITHUB | 2026-10-19 | 진단 힌트

문서: GitHub 조직 저장소 역할 구분

"저장소에 Push가 안 된다"는 증상은 현재 역할이 Read나 Triage인지, 아예 접근 권한이 없는지를 먼저 확인한다. push는 Write 이상이 필요하다. Admin은 삭제·공개 범위 변경 같은 되돌리기 어려운 작업을 포함하므로 자동 부여 대상에서 제외하는 것이 안전하다. 이 문서는 개인·팀·조직 기본 권한이 겹칠 때 어느 것이 우선하는지는 설명하지 않는다. 그 부분은 팀 접근 관리 문서(GH-OFF-02)에서 확인한다.

## GH-OFF-01 | GITHUB | 2026-10-19 | 원문

문서: GitHub 조직 저장소 역할 구분

- 출처: GitHub Docs, "Repository roles for an organization"
- 링크: https://docs.github.com/en/organizations/managing-user-access-to-your-organizations-repositories/managing-repository-roles/repository-roles-for-an-organization
- 확인 날짜: 2026-10-19
- 이 문서는 원문을 우리 말로 요약·재작성한 것이다. 최신 내용은 원문 링크를 확인한다.

## GH-OFF-02 | GITHUB | 2026-10-19 | 핵심 요약

문서: GitHub 팀을 통한 저장소 접근 관리

조직 저장소에 팀 접근 권한을 주거나 바꾸거나 없애는 일은 저장소 설정에서 한다. 이 일은 해당 저장소에 admin 권한이 있는 사람이 할 수 있다. 팀 maintainer는 팀이 직접 받은 저장소 권한을 제거할 수 있다. 상위 팀에서 상속된 권한은 직접 바꿀 수 없고, 상위 팀의 권한을 바꾸거나 상위 팀에서 저장소를 제거해야 한다. 상위 팀에 저장소를 추가하거나 제거하면 하위 팀도 같은 영향을 받는다.

## GH-OFF-02 | GITHUB | 2026-10-19 | 진단 힌트

문서: GitHub 팀을 통한 저장소 접근 관리

팀 멤버십이 있는데도 push가 안 되면 팀이 그 저장소에 어떤 역할로 연결되어 있는지, 그 권한이 직접 부여된 것인지 상위 팀에서 상속된 것인지 순서대로 확인한다. 권한을 부여한 뒤에는 팀 멤버십과 저장소 권한을 다시 조회해 반영 여부를 확인한다. 주의할 점은 비공개 저장소 접근을 제거하면 그 사람이 만든 해당 저장소의 포크가 삭제될 수 있다는 것이다. 로컬 복제본은 남는다. 접근을 회수하는 요청에서는 이 영향을 함께 안내한다.

## GH-OFF-02 | GITHUB | 2026-10-19 | 원문

문서: GitHub 팀을 통한 저장소 접근 관리

- 출처: GitHub Docs, "Managing team access to an organization repository"
- 링크: https://docs.github.com/en/organizations/managing-user-access-to-your-organizations-repositories/managing-repository-roles/managing-team-access-to-an-organization-repository
- 확인 날짜: 2026-10-19
- 이 문서는 원문을 우리 말로 요약·재작성한 것이다. 최신 내용은 원문 링크를 확인한다.

## GH-OFF-03 | GITHUB | 2026-10-22 | 핵심 요약

문서: GitHub Copilot 플랜별 가격 (요약)

GitHub Copilot의 조직용 플랜은 Business와 Enterprise가 있다. 가격은 좌석을 부여한 수 기준으로 매겨진다. Copilot Business는 부여된 좌석 1개당 월 19달러, Copilot Enterprise는 부여된 좌석 1개당 월 39달러이다.

## GH-OFF-03 | GITHUB | 2026-10-22 | 진단 힌트

문서: GitHub Copilot 플랜별 가격 (요약)

좌석을 부여하는 순간 월 비용이 발생하므로 승인 전에 부서 잔여 예산을 확인한다(POL-06 제2조). 이미 좌석을 가진 직원의 재요청은 중복 구매하지 않는다(POL-06 제4조). 좌석을 회수하면 Business 기준 월 19달러가 절감된다. 이 문서는 무료·개인 플랜과 사용량 초과 요금, 계약별 할인은 다루지 않는다.

## GH-OFF-03 | GITHUB | 2026-10-22 | 원문

문서: GitHub Copilot 플랜별 가격 (요약)

- 출처: GitHub Docs, "Plans for GitHub Copilot"
- 링크: https://docs.github.com/en/copilot/get-started/plans
- 확인 날짜: 2026-10-22
- 이 문서는 원문을 우리 말로 요약·재작성한 것이다. 최신 내용은 원문 링크를 확인한다.

## JR-OFF-01 | JIRA | 2026-10-19 | 핵심 요약

문서: Jira 프로젝트 역할과 권한 스킴

Atlassian 문서는 Jira의 프로젝트를 '스페이스(space)'라고 부른다. 스페이스 역할은 권한 스킴에서 특정 사용자 대신 쓰는 자리표시자다. Jira 관리자가 역할을 만들고 권한 스킴에 역할별 권한을 정하면, 각 스페이스의 스페이스 관리자가 자기 스페이스에서 그 역할에 사람을 지정한다. 같은 권한 스킴을 여러 스페이스가 써도 접근 범위는 스페이스별로 나뉜다. 역할은 권한 부여 외에 알림, 작업 항목 보안 수준, 워크플로 조건, 필터·대시보드 접근에도 쓰인다. Free 사이트에서는 스페이스 권한 스킴과 스페이스 역할을 쓸 수 없다.

## JR-OFF-01 | JIRA | 2026-10-19 | 진단 힌트

문서: Jira 프로젝트 역할과 권한 스킴

프로젝트가 보이지 않을 때는 사용자가 해당 스페이스의 필요한 역할(예: Developer)에 지정되어 있는지 확인한다. 역할에 사람을 넣는 일은 해당 스페이스의 관리자가 한다. 앱이나 연동 서비스(예: Slack)가 Jira에서 작업하게 하려면 권한 스킴에 `atlassian-addons-project-access` 역할이 필요하다. 이 문서는 사용자를 역할에 추가하는 구체적인 클릭 절차와 기본 제공 역할 목록은 다루지 않는다. 그 부분은 다른 Atlassian 문서를 확인한다.

## JR-OFF-01 | JIRA | 2026-10-19 | 원문

문서: Jira 프로젝트 역할과 권한 스킴

- 출처: Atlassian Support, 스페이스(프로젝트) 역할 문서 (문서 제목: "How to use space roles")
- 링크: https://support.atlassian.com/jira-cloud-administration/docs/manage-project-role-membership
- 확인 날짜: 2026-10-19
- 이 문서는 원문을 우리 말로 요약·재작성한 것이다. 최신 내용은 원문 링크를 확인한다.

## JR-OFF-02 | JIRA | 2026-10-19 | 핵심 요약

문서: Jira 프로젝트 미노출 트러블슈팅

Jira에 로그인은 되지만 프로젝트(스페이스)와 작업 항목이 하나도 보이지 않으면, 그 사용자에게 Browse Projects(프로젝트 찾아보기) 권한이 없는 경우가 많다. Jira 애플리케이션을 쓸 수 있는 자격(jira-users, jira-developers 같은 그룹 소속)과 프로젝트의 Browse Projects 권한은 서로 다른 것이어서, 애플리케이션 접근만 있으면 화면은 열려도 프로젝트 목록은 비어 있을 수 있다. Browse Projects는 개별 사용자, 그룹, 스페이스 역할 중 하나로 부여된다. 이 문서는 Jira Cloud 전용이다.

## JR-OFF-02 | JIRA | 2026-10-19 | 진단 힌트

문서: Jira 프로젝트 미노출 트러블슈팅

점검 순서는 이렇다. 문제가 되는 스페이스의 설정에서 권한 메뉴를 열고, Browse Projects 행에 해당 사용자가 개인·그룹·역할 중 어떤 방식으로든 포함되어 있는지 본다. 역할로 부여된 경우에는 사용자가 실제로 그 역할의 멤버인지도 확인한다. 조치는 jira-developers 그룹에 추가하거나 스페이스의 Users/Administrators 역할에 지정하는 방법 중 하나이고, 변경 뒤에는 새로고침을 안내한다. 권한 스킴은 여러 스페이스가 공유하는 경우가 많으므로 수정 전에 영향받는 스페이스를 확인해야 한다.

## JR-OFF-02 | JIRA | 2026-10-19 | 원문

문서: Jira 프로젝트 미노출 트러블슈팅

- 출처: Atlassian Support 지식 베이스, "Users with Jira access can't view any projects or work items"
- 링크: https://support.atlassian.com/jira/kb/new-users-in-the-developers-group-do-not-have-access-to-any-projects-in-jira/
- 확인 날짜: 2026-10-19
- 이 문서는 원문을 우리 말로 요약·재작성한 것이다. 최신 내용은 원문 링크를 확인한다.

## SL-OFF-01 | SLACK | 2026-10-19 | 핵심 요약

문서: Slack 채널 멤버 추가 방법

Slack 채널에 사람을 넣는 방법은 데스크톱에서 채널을 열고 멤버 아이콘을 눌러 Add people을 선택한 뒤 이름, 이메일, 사용자 그룹으로 찾아 추가하는 것이다. 모바일에서는 채널 이름을 눌러 Add를 선택한다. 한 번에 최대 1,000명까지 추가할 수 있고, 목록을 붙여 넣어 한꺼번에 추가할 수도 있다. 프로필에서 이메일을 숨긴 사람은 이메일로 추가할 수 없다. 사용자 그룹 추가는 유료 구독에서 가능하다. Business+와 Enterprise 구독에서는 권한이 있는 소유자와 관리자가 채널 관리 도구로 사람을 추가할 수 있다. 회사 외부 사람은 Slack Connect를 쓰라고 안내한다.

## SL-OFF-01 | SLACK | 2026-10-19 | 진단 힌트

문서: Slack 채널 멤버 추가 방법

채널에 들어가지 못하는 요청은 해당 채널에서 Add people로 추가해 해결한다. 이 문서는 공개 채널과 비공개 채널의 차이, 비공개 채널에 누가 초대할 수 있는지, 채널 관리자(Channel Manager) 권한의 영향은 다루지 않는다. 그 내용은 다른 Slack 도움말에서 추가로 확인해 보강해야 한다(보강 전까지는 사내 규정 POL-05를 기준으로 판단). 외부 협력사 인원은 일반 추가가 아니라 게스트 또는 Slack Connect 절차를 안내한다(SL-OFF-02).

## SL-OFF-01 | SLACK | 2026-10-19 | 원문

문서: Slack 채널 멤버 추가 방법

- 출처: Slack Help Center, "Add people to a channel"
- 링크: https://slack.com/help/articles/201980108
- 확인 날짜: 2026-10-19
- 이 문서는 원문을 우리 말로 요약·재작성한 것이다. 최신 내용은 원문 링크를 확인한다.

## SL-OFF-02 | SLACK | 2026-10-19 | 핵심 요약

문서: Slack 게스트 계정 유형 구분

Slack 게스트에는 두 유형이 있다. 멀티채널 게스트는 지정한 여러 채널에 접근하며 일반 멤버와 같은 기준으로 과금되고, 비공개 채널 초대를 받거나 보낼 수 있다. 싱글채널 게스트는 채널 하나에만 접근하며 무료이고, 유료 활성 멤버 1명당 최대 5명까지 초대할 수 있다. 게스트는 공개 채널 생성, 채널 이름 변경·보관·삭제, 다른 멤버 제거, 앱 설치·제거 등이 제한된다. 게스트를 초대하는 일은 워크스페이스 소유자와 관리자만 할 수 있고, 일반 멤버는 초대를 요청할 수 있다. 계정 기간은 자동 비활성화 기한이나 특정 날짜로 정할 수 있고, 비활성화 5일 전에 알림이 간다. 게스트는 유료 요금제에서만 쓸 수 있다.

## SL-OFF-02 | SLACK | 2026-10-19 | 진단 힌트

문서: Slack 게스트 계정 유형 구분

외부 협력사 담당자를 채널에 넣고 싶다는 요청은 일반 멤버 추가가 아니라 게스트 초대 요청이다. 이때 승인 주체는 소유자·관리자이므로 팀 리더 승인만으로 처리하지 않는다(사내 규정 POL-05 제3조). 상대 회사도 자기 Slack을 쓰고 있다면 게스트 대신 Slack Connect가 권장된다. 접근 범위는 필요한 채널 수에 따라 싱글채널과 멀티채널 중 최소한을 선택한다. 이번 시연 범위에서는 확장 항목이다.

## SL-OFF-02 | SLACK | 2026-10-19 | 원문

문서: Slack 게스트 계정 유형 구분

- 출처: Slack Help Center, "Understand guest roles in Slack"
- 링크: https://slack.com/help/articles/202518103-Understand-guest-roles-in-Slack
- 확인 날짜: 2026-10-19
- 이 문서는 원문을 우리 말로 요약·재작성한 것이다. 최신 내용은 원문 링크를 확인한다.

## NT-OFF-01 | NOTION | 2026-10-19 | 핵심 요약

문서: Notion 페이지 공유 및 권한 수준

Notion 페이지 권한 수준은 여섯 가지다. Full access는 편집과 다른 사람 공유까지 할 수 있다. Can edit는 편집은 되지만 공유는 못 한다. Can edit content와 Can create는 데이터베이스 페이지 전용이고, Can create는 Business·Enterprise 요금제에서 제공된다. Can comment는 댓글만 달 수 있다. Can view는 읽기만 가능하다. 공유는 페이지의 Share에서 워크스페이스 멤버나 그룹을 초대하거나, 외부 사람은 이메일로 초대한다(게스트도 자기 Notion 계정이 필요). 링크로 공유할 때는 초대된 사람만, 워크스페이스 전체, 링크를 가진 모든 사람 중에서 고르고 만료 기한을 둘 수 있다.

## NT-OFF-01 | NOTION | 2026-10-19 | 진단 힌트

문서: Notion 페이지 공유 및 권한 수준

문서가 "접근 권한 없음"으로 뜨면 페이지에서 접근 요청을 보낼 수 있고, 작성자나 편집 권한자가 수락하거나 거절한다. 읽기만 가능한 사람이 편집을 원하면 Share에서 편집 권한 요청을 보낸다. 하위 페이지는 상위 페이지의 권한을 그대로 물려받고, 하위에서 따로 바꿀 수도 있다. 여러 경로로 권한이 겹치면 가장 넓은 접근이 적용되므로, 상위 페이지·팀스페이스 설정까지 같이 확인해야 한다. 읽기 요청은 Can view로 최소 부여하고, Full access는 자동 부여 대상에서 제외한다(사내 규정 POL-08).

## NT-OFF-01 | NOTION | 2026-10-19 | 원문

문서: Notion 페이지 공유 및 권한 수준

- 출처: Notion Help Center, "Sharing & permissions settings"
- 링크: https://www.notion.com/help/sharing-and-permissions
- 확인 날짜: 2026-10-19
- 이 문서는 원문을 우리 말로 요약·재작성한 것이다. 최신 내용은 원문 링크를 확인한다.
$existing_policy$,true
FROM companies c WHERE c.id='00000000-0000-0000-0000-000000000000' AND c.code='LEGACY' AND c.is_mock;

-- Only roles supported by the current grant writer enter the request catalogue.
WITH roles AS (
 SELECT r.*,x.code,x.external_role,x.kind
 FROM resources r JOIN companies c ON c.id=r.company_id
 CROSS JOIN LATERAL (
   SELECT 'READ' AS code,'Read' AS external_role,'ROLE' AS kind WHERE r.platform='GITHUB' AND r.access_scope<>'SEAT'
   UNION ALL SELECT 'WRITE','Write','ROLE' WHERE r.platform='GITHUB' AND r.access_scope<>'SEAT'
   UNION ALL SELECT 'COPILOT_SEAT','Seat','SEAT' WHERE r.platform='GITHUB' AND r.external_id='copilot-seat' AND r.access_scope='SEAT'
   UNION ALL SELECT 'VIEWER','Viewer','ROLE' WHERE r.platform='JIRA'
   UNION ALL SELECT 'DEVELOPER','Developer','ROLE' WHERE r.platform='JIRA'
   UNION ALL SELECT 'MEMBER','Member','MEMBERSHIP' WHERE r.platform='SLACK'
   UNION ALL SELECT 'VIEWER','Can view','ROLE' WHERE r.platform='NOTION'
   UNION ALL SELECT 'EDITOR','Can edit','ROLE' WHERE r.platform='NOTION' AND (r.access_scope='DEPARTMENT'
     OR EXISTS(SELECT 1 FROM permissions p WHERE p.resource_id=r.id AND p.saas_role='Can edit'))
 ) x
 WHERE c.id='00000000-0000-0000-0000-000000000000' AND c.code='LEGACY' AND c.is_mock
)
INSERT INTO entitlements(id,company_id,resource_id,code,kind)
SELECT md5('unlockops:existing:entitlement:'||id||':'||code)::uuid,company_id,id,code,kind FROM roles;

INSERT INTO entitlement_revisions(entitlement_id,revision,company_id,external_role,mapping)
SELECT e.id,1,e.company_id,
 CASE WHEN r.platform='GITHUB' THEN CASE e.code WHEN 'READ' THEN 'Read' WHEN 'WRITE' THEN 'Write' ELSE 'Seat' END
      WHEN r.platform='JIRA' THEN CASE e.code WHEN 'VIEWER' THEN 'Viewer' ELSE 'Developer' END
      WHEN r.platform='NOTION' THEN CASE e.code WHEN 'VIEWER' THEN 'Can view' ELSE 'Can edit' END ELSE 'Member' END,
 jsonb_build_object('mock',true,'scope','assigned_resource_only','requires_existing_account',true,
   'allows_admin',false,'includes_seat',e.kind='SEAT','requires_existing_data_access',false,'uses_job_family',true,
   'allowed_job_families',CASE WHEN e.code IN ('WRITE','DEVELOPER','COPILOT_SEAT') THEN '["DEV"]'::jsonb ELSE '["DEV","NON_DEV"]'::jsonb END,
   'allowed_job_grades',CASE WHEN (e.code IN ('WRITE','DEVELOPER') AND r.access_scope<>'TF') OR e.code='EDITOR'
       THEN '["대리","과장","차장","부장"]'::jsonb ELSE '["사원","대리","과장","차장","부장"]'::jsonb END,
   'grantable',e.code<>'EDITOR' OR r.access_scope='DEPARTMENT')
FROM entitlements e JOIN resources r ON r.id=e.resource_id
WHERE e.company_id='00000000-0000-0000-0000-000000000000';

-- Original seat prices live on department_budgets. Do not choose an arbitrary
-- company-wide price when those rows disagree: a missing price requires review.
WITH seat_price AS (
 SELECT min(b.unit_monthly_price) AS amount,min(b.currency) AS currency
 FROM department_budgets b JOIN departments d ON d.id=b.department_id
 WHERE d.company_id='00000000-0000-0000-0000-000000000000'
 HAVING count(DISTINCT (b.unit_monthly_price,b.currency))=1
)
INSERT INTO pricing_revisions(pricing_id,revision,company_id,entitlement_id,entitlement_revision,
 monthly_amount,currency,cost_basis,source_kind,source_reference,effective_from,policy_id,policy_revision)
SELECT md5('unlockops:existing:price:'||e.id)::uuid,1,e.company_id,e.id,1,
 CASE WHEN e.kind='SEAT' THEN s.amount ELSE 0 END,
 CASE WHEN e.kind='SEAT' THEN s.currency ELSE 'USD' END,
 CASE WHEN e.kind='SEAT' THEN 'SEAT_MONTHLY' ELSE 'NO_ADDITIONAL_COST' END,
 'SYNTHETIC_CONTRACT',CASE WHEN e.kind='SEAT' THEN 'V9:existing-department_budgets' ELSE 'V9:no-additional-cost' END,
 DATE '1970-01-01',md5('unlockops:existing:policy')::uuid,1
FROM entitlements e LEFT JOIN seat_price s ON true
WHERE e.company_id='00000000-0000-0000-0000-000000000000' AND (e.kind<>'SEAT' OR s.amount IS NOT NULL);

INSERT INTO approval_route_revisions(route_id,revision,company_id,code,policy_id,policy_revision,steps)
SELECT md5('unlockops:existing:route')::uuid,1,company_id,'DEFAULT',policy_id,revision,'["DEPARTMENT_HEAD","SAAS_OPERATOR"]'::jsonb
FROM policy_revisions WHERE policy_id=md5('unlockops:existing:policy')::uuid AND revision=1;

-- Department heads are declared data. The existing song_ops identity is the
-- explicitly documented mock SaaS operator. Missing/duplicate/self approvers
-- remain subject to the same fail-closed planner checks as every other tenant.
INSERT INTO operator_assignments(company_id,user_id,department_id,platform,capability)
SELECT d.company_id,u.id,d.id,p.platform,'DEPARTMENT_HEAD'
FROM departments d JOIN users u ON u.id=d.head_id AND u.company_id=d.company_id
CROSS JOIN (VALUES ('GITHUB'),('JIRA'),('SLACK'),('NOTION')) p(platform)
WHERE d.company_id='00000000-0000-0000-0000-000000000000' AND u.role='APPROVER' AND u.employment_status='ACTIVE'
ON CONFLICT DO NOTHING;
INSERT INTO operator_assignments(company_id,user_id,department_id,platform,capability)
SELECT d.company_id,u.id,d.id,p.platform,'SAAS_OPERATOR'
FROM departments d JOIN users u ON u.company_id=d.company_id AND u.login_id='song_ops'
CROSS JOIN (VALUES ('GITHUB'),('JIRA'),('SLACK'),('NOTION')) p(platform)
WHERE d.company_id='00000000-0000-0000-0000-000000000000' AND u.role='APPROVER' AND u.employment_status='ACTIVE'
ON CONFLICT DO NOTHING;

-- The old provider represented mock accounts by users, not external SaaS facts.
-- This observation is explicitly synthetic; data access/usage are not invented.
INSERT INTO saas_context_facts(company_id,user_id,platform,account_exists,license_active,data_access,
 work_scope_assigned,job_function,observed_at,source_reference)
SELECT u.company_id,u.id,p.platform,true,true,NULL,true,
 CASE WHEN u.job_family='DEV' THEN 'DEV' ELSE 'UNKNOWN' END,now(),'V9:existing-mock-users'
FROM users u JOIN companies c ON c.id=u.company_id
CROSS JOIN (VALUES ('GITHUB'),('JIRA'),('SLACK'),('NOTION')) p(platform)
WHERE c.id='00000000-0000-0000-0000-000000000000' AND c.code='LEGACY' AND c.is_mock
ON CONFLICT DO NOTHING;

-- Match the previous provider's source of truth: GitHub team memberships,
-- Jira role + browse scheme, and permissions for the remaining mock platforms.
CREATE TEMP TABLE existing_effective_roles ON COMMIT DROP AS
SELECT m.user_id,t.resource_id,t.saas_role,coalesce(p.granted_at,u.created_at) AS granted_at
FROM github_team_members m JOIN github_teams t ON t.id=m.team_id
JOIN resources r ON r.id=t.resource_id JOIN users u ON u.id=m.user_id AND u.company_id=r.company_id
LEFT JOIN permissions p ON p.user_id=m.user_id AND p.resource_id=t.resource_id
WHERE r.company_id='00000000-0000-0000-0000-000000000000'
UNION ALL
SELECT p.user_id,p.resource_id,p.saas_role,p.granted_at
FROM permissions p JOIN resources r ON r.id=p.resource_id JOIN users u ON u.id=p.user_id AND u.company_id=r.company_id
WHERE r.company_id='00000000-0000-0000-0000-000000000000' AND (r.platform<>'GITHUB' OR r.access_scope='SEAT')
 AND (r.platform<>'JIRA' OR EXISTS(SELECT 1 FROM jira_role_permissions j
   WHERE j.resource_id=p.resource_id AND j.saas_role=p.saas_role AND j.can_browse));

-- A higher existing role also satisfies its lower role; these rows are an
-- import of effective access, never new grants and never another budget charge.
INSERT INTO access_assignments(id,company_id,user_id,resource_id,entitlement_id,entitlement_revision,origin_tf_id,granted_at)
SELECT md5('unlockops:existing:assignment:'||p.user_id||':'||e.id)::uuid,e.company_id,p.user_id,e.resource_id,e.id,1,r.tf_id,min(p.granted_at)
FROM existing_effective_roles p JOIN entitlements e ON e.resource_id=p.resource_id
JOIN entitlement_revisions er ON er.entitlement_id=e.id AND er.revision=1 JOIN resources r ON r.id=e.resource_id
WHERE p.saas_role=er.external_role OR (p.saas_role='Write' AND e.code='READ')
 OR (p.saas_role IN ('Developer','Can edit') AND e.code='VIEWER')
GROUP BY e.company_id,p.user_id,e.resource_id,e.id,r.tf_id;
INSERT INTO mock_entitlement_memberships(assignment_id,company_id,user_id,entitlement_id,entitlement_revision,mapping)
SELECT a.id,a.company_id,a.user_id,a.entitlement_id,a.entitlement_revision,er.mapping
FROM access_assignments a JOIN entitlement_revisions er ON er.entitlement_id=a.entitlement_id AND er.revision=a.entitlement_revision
WHERE a.company_id='00000000-0000-0000-0000-000000000000';
INSERT INTO assignment_usage(assignment_id,company_id,observation_status,observed_at,source_reference)
SELECT id,company_id,'UNKNOWN',now(),'V9:existing-access:no-usage-observation'
FROM access_assignments WHERE company_id='00000000-0000-0000-0000-000000000000';

-- Immutable snapshot for interpreting the original result after a user elects
-- to reanalyse a pending request. No old plan/approval authorises current work.
INSERT INTO problem_events(event_id,problem_id,kind,payload)
SELECT md5('unlockops:existing:record:'||p.id)::uuid,p.id,'WORKFLOW_HISTORY_IMPORTED',to_jsonb(p)
FROM problems p WHERE p.contract_version=1;
