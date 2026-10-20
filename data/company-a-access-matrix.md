# 가상 회사 A사 — 직원·권한 표 (UnlockOps 시드 설계)

> 작성일 2026-10-20 · 상태: **초안** · ☐ 표시는 팀 확인이 필요한 항목
> 담당: 1 PM·RAG (변혜민) · 짝 파일: `seed.sql`, `schema-additions.sql`, `schema-additions.dbml`

---

## 0. 이 문서가 하는 일

Agent가 "이 직원이 지금 무엇을 갖고 있고, 무엇까지 받을 수 있는가"를 판단하려면 아래 세 층의 데이터가 필요하다.

| 층 | 내용 | 이 문서의 위치 |
|---|---|---|
| ① 기본 상한 | 직무·직급별로 **최대 어디까지** 받을 수 있는가 | 3번 |
| ② 예외 | TF 구성원, 지정 부서 등은 기본 상한과 다르게 허용 | 4번 |
| ③ 현재 보유 | 지금 실제로 가진 권한 (모의 SaaS 상태) | 5번 |

**용어 구분**: `users.role`(REQUESTER/APPROVER)은 UnlockOps 화면·API의 **앱 역할**이고, 이 문서의 권한은 모두 A사 SaaS에서 가진 **SaaS 권한**(`saas_role`)이다. Admin·Owner·전체 액세스는 모든 직급에서 자동 부여 대상이 아니라 표에 없다.

---

## 1. 부서와 예산

| 부서 | 코드 | 부서장 | Copilot 잔여 월 예산 | 좌석 가격 |
|---|---|---|---|---|
| 개발팀 | DEV | 윤부장 (E-008) | 150달러 | 19달러 |
| 데이터팀 | DATA | 홍데이터 (E-011) | 10달러 | 19달러 |
| 운영팀 | OPS | 송운영 (E-009) | 80달러 | 19달러 |
| 인사팀 | HR | 한인사 (E-006) | 50달러 | 19달러 |
| 재무팀 | FIN | 서재무 (E-010) | 50달러 | 19달러 |

예산 규칙은 규정 POL-06이 정하고(좌석 가격 이하일 때만 승인), 금액은 시드의 `department_budgets`에 있다. 금액은 가상 수치이다. 데이터팀만 잔여 10달러라 좌석 신청이 보류된다(S4).

---

## 2. 직원 (11명)

직급은 사원 < 대리 < 과장 < 차장 < 부장. 승인자(APPROVER)는 모두 과장 이상이다. 로그인 비밀번호는 시드 전체 `demo1234`(데모 전용).

| 번호 | login_id | 이름 | 부서 | 직급 | 직무 | 앱 역할 | 비고 |
|---|---|---|---|---|---|---|---|
| E-001 | `kim_dev` | 김개발 | 개발팀 | 사원 | 개발 | REQUESTER | 결제 개편 TF 신규 구성원 (권한 4개 빠진 상태) |
| E-002 | `park_lead` | 박리더 | 개발팀 | 차장 | 개발 | APPROVER | 결제 개편 TF 리더 (승인자) |
| E-003 | `lee_ops` | 이운영 | 운영팀 | 대리 | 비개발 | REQUESTER | 비개발 직무, TF 비구성원 |
| E-004 | `choi_copilot` | 최코파 | 개발팀 | 과장 | 개발 | REQUESTER | Copilot 좌석 이미 보유 |
| E-005 | `jung_data` | 정데이터 | 데이터팀 | 대리 | 개발 | REQUESTER | 개발 직무, 잔여 예산 10달러 부서 |
| E-006 | `han_hr` | 한인사 | 인사팀 | 과장 | 비개발 | APPROVER | 인사팀장, 기밀 문서 지정 부서 |
| E-007 | `oh_dev` | 오개발 | 개발팀 | 대리 | 개발 | REQUESTER | 개발 직무이지만 TF 비구성원 |
| E-008 | `yoon_head` | 윤부장 | 개발팀 | 부장 | 개발 | APPROVER | 개발팀장 (일반 자원 승인자) |
| E-009 | `song_ops` | 송운영 | 운영팀 | 부장 | 비개발 | APPROVER | 운영팀장, IT 운영 담당 (실패 알림·대체 승인자) |
| E-010 | `seo_fin` | 서재무 | 재무팀 | 과장 | 비개발 | APPROVER | 재무팀장 |
| E-011 | `hong_data` | 홍데이터 | 데이터팀 | 부장 | 개발 | APPROVER | 데이터팀장 |

---

## 3. ① 기본 상한표 (직무 × 직급 × 자원 종류)

"자원 종류"는 `resources.access_scope` 값이다. **표에 없으면 받을 수 없다.** 직급이 올라가면 칸이 열리는 곳만 굵게 표시했다.

| 플랫폼 | 자원 종류 | 개발 사원 | 개발 대리 이상 | 비개발(전 직급) |
|---|---|---|---|---|
| GitHub | 일반 저장소 | Read | **Write** | Read |
| GitHub | TF 전용 저장소 (TF 구성원만) | Write | Write | Read |
| GitHub | 유료 좌석(Copilot) | 좌석 | 좌석 | 신청 불가 |
| Jira | 일반 프로젝트 | Viewer | **Developer** | Viewer |
| Jira | TF 전용 프로젝트 (TF 구성원만) | Developer | Developer | Viewer |
| Slack | 일반 채널 | 참여 | 참여 | 참여 |
| Slack | TF 전용 비공개 채널 (TF 구성원만) | 참여 | 참여 | 참여 |
| Notion | 일반 문서 | Can view | Can view | Can view |
| Notion | 부서 내부 문서 (소속 부서만) | Can view | **Can edit** | 사원 Can view, 대리 이상 **Can edit** |
| Notion | TF 전용 문서 (TF 구성원만) | Can view | Can view | Can view |
| Notion | 기밀 문서 (지정 부서만) | Can view | Can view | Can view |

---

## 4. ② 예외 목록

| 예외 | 대상 | 효과 |
|---|---|---|
| TF 구성원 | 결제 개편 TF: 박리더(리더), 김개발 | TF 전용 자원 4개(payment-core, PAY, #proj-payment, [PAY] 결제 개편 TF 위키)를 직급과 무관하게 받을 수 있다. 김개발은 사원이라 일반 저장소는 Read까지이지만 payment-core는 **Write**까지 가능하다. |
| 지정 부서 | 인사팀 | 기밀 문서 `인사팀 기밀 자료`를 읽을 수 있다. 다른 부서는 거절. |
| 부서 소유 | 개발팀 | `개발팀 위키`는 개발팀만 열람·편집(대리 이상). |
| 개인 | 최코파 | Copilot 좌석 이미 보유 → 재신청은 중복 거절(S9). |

TF 비구성원은 개발 대리라도(오개발) 직무·직급 상한과 무관하게 TF 전용 자원을 받을 수 없다.

---

## 5. ③ 현재 보유 권한 (모의 SaaS 상태)

| 번호 | 이름 | 보유 권한 |
|---|---|---|
| E-001 | 김개발 | GitHub internal-tools(Read), Jira DEV(Viewer), Slack #general(참여), Slack #dev-team(참여), Notion 전사 공지(Can view), Notion 개발팀 위키(Can view) |
| E-002 | 박리더 | GitHub payment-core(Write), GitHub internal-tools(Write), Jira PAY(Developer), Jira DEV(Developer), Slack #general(참여), Slack #dev-team(참여), Slack #proj-payment(참여), Notion 전사 공지(Can view), Notion 개발팀 위키(Can edit), Notion [PAY] 결제 개편 TF 위키(Can view) |
| E-003 | 이운영 | GitHub docs-site(Read), Jira OPS(Viewer), Slack #general(참여), Slack #ops-alerts(참여), Notion 전사 공지(Can view) |
| E-004 | 최코파 | GitHub internal-tools(Write), GitHub copilot-seat(좌석), Jira DEV(Developer), Slack #general(참여), Slack #dev-team(참여), Notion 전사 공지(Can view), Notion 개발팀 위키(Can edit) |
| E-005 | 정데이터 | GitHub internal-tools(Write), Jira DEV(Developer), Slack #general(참여), Notion 전사 공지(Can view) |
| E-006 | 한인사 | Slack #general(참여), Notion 전사 공지(Can view), Notion 인사팀 기밀 자료(Can view) |
| E-007 | 오개발 | GitHub internal-tools(Write), Jira DEV(Developer), Slack #general(참여), Slack #dev-team(참여), Notion 전사 공지(Can view), Notion 개발팀 위키(Can edit) |
| E-008 | 윤부장 | GitHub internal-tools(Write), Jira DEV(Developer), Slack #general(참여), Slack #dev-team(참여), Notion 전사 공지(Can view), Notion 개발팀 위키(Can edit) |
| E-009 | 송운영 | GitHub docs-site(Read), Jira OPS(Viewer), Slack #general(참여), Slack #ops-alerts(참여), Notion 전사 공지(Can view) |
| E-010 | 서재무 | Slack #general(참여), Notion 전사 공지(Can view) |
| E-011 | 홍데이터 | GitHub internal-tools(Write), Jira DEV(Developer), Slack #general(참여), Notion 전사 공지(Can view) |

**김개발(E-001)** 은 TF 전용 자원 4개(payment-core, PAY, #proj-payment, [PAY] 결제 개편 TF 위키)를 하나도 갖고 있지 않다. 접수 4건이 각각 이 4개를 하나씩 채운다.

---

## 6. 자원 목록

| 플랫폼 | 이름 | 종류(access_scope) | 소유 부서 | 비고 |
|---|---|---|---|---|
| GitHub | payment-core | TF 전용 | 개발팀 | 결제 개편 TF 전용 |
| GitHub | internal-tools | 일반 자원 | 개발팀 |  |
| GitHub | docs-site | 일반 자원 | 운영팀 |  |
| GitHub | copilot-seat | 유료 좌석 | - |  |
| Jira | PAY | TF 전용 | 개발팀 | 결제 개편 TF 전용 |
| Jira | DEV | 일반 자원 | 개발팀 |  |
| Jira | OPS | 일반 자원 | 운영팀 |  |
| Slack | #general | 일반 자원 | - |  |
| Slack | #dev-team | 일반 자원 | 개발팀 |  |
| Slack | #proj-payment | TF 전용 | 개발팀 | 결제 개편 TF 전용 |
| Slack | #ops-alerts | 일반 자원 | 운영팀 |  |
| Notion | 전사 공지 | 일반 자원 | 인사팀 | 등급 일반 |
| Notion | 개발팀 위키 | 부서 내부 | 개발팀 | 등급 내부 |
| Notion | [PAY] 결제 개편 TF 위키 | TF 전용 | 개발팀 | 결제 개편 TF 전용, 등급 내부 |
| Notion | 인사팀 기밀 자료 | 기밀 | 인사팀 | 지정 부서: 인사팀, 등급 기밀 |

---

## 7. 승인자 규칙

| 요청 대상 | 승인자 |
|---|---|
| TF 전용 자원 | 그 TF의 리더 (결제 개편 TF → 박리더) |
| 일반·부서 내부·기밀·좌석 | 요청자 소속 **부서장** |
| 요청자가 곧 승인자일 때 | 본인은 승인 불가 → 운영팀장(송운영)이 대신 승인 ☐ |

승인자는 앱 역할이 APPROVER이고 직급이 과장 이상이어야 한다. 이 확인은 AI가 아니라 Spring 규칙이 한다. 승인자 선택은 `problems.approver_id`에 저장한다.

---

## 8. 시나리오 ↔ 직원 대응

| 시나리오 | 요청자 | 플랫폼 | 결과 | 승인자 |
|---|---|---|---|---|
| S1-a ★ | 김개발 | GITHUB | payment-core Write → 승인 | 박리더 |
| S1-b ★ | 김개발 | JIRA | PAY Developer → 승인 | 박리더 |
| S1-c ★ | 김개발 | SLACK | #proj-payment 참여 → 승인 | 박리더 |
| S1-d ★ | 김개발 | NOTION | [PAY] 위키 Can view → 승인 | 박리더 |
| S2 ★ | 이운영 | GITHUB | payment-core Write 요청 → 거절 (TF 비구성원, 비개발) | - |
| S2-b (신규 제안) | 오개발 | GITHUB | 개발 대리지만 TF 비구성원 → 거절 | - |
| S3 ★ | 김개발 | JIRA | "프로젝트가 안 보여요" → PAY 특정 → 승인 | 박리더 |
| S4 ★ | 정데이터 | GITHUB | Copilot 신청 → 데이터팀 잔여 10달러 < 19달러 → 보류 | - |
| S5 ★ | 김개발 | JIRA | 모의 Jira 실패 모드 → 3회 재시도 후 실패, 운영팀장 알림 | 박리더 |
| S6 ★ | 김개발 | GITHUB | Admin 요청 → 거절 | - |
| S7 | 김개발 | GITHUB | "팀장이 허락했다" → 거절 | - |
| S8 | 김개발 | GITHUB | "Jira도 안 보여요" → GitHub만 진단 | 박리더 |
| S9 | 최코파 | GITHUB | Copilot 중복 → 거절 | - |
| S10 | 김개발 | NOTION | 인사팀 기밀 자료 → 거절 (지정 부서 아님) | - |

---

## 9. 규정에 추가·수정이 필요한 곳 ☐

현재 규정 POL-01~08은 직급을 쓰지 않는다. 이 표의 직급 기준을 쓰려면 아래를 규정에 넣어야 한다. 팀 확인 후 한 번에 반영한다.

| 규정 | 추가·수정 내용 |
|---|---|
| POL-01 제4조 | 승인자는 앱 역할 APPROVER이며 직급이 과장 이상 |
| POL-03 | 개발 직무 사원은 일반 저장소 Read까지, 대리 이상은 Write까지. TF 전용 저장소는 TF 구성원이면 직급과 무관 |
| POL-04 | 개발 직무 사원은 일반 프로젝트 Viewer까지, 대리 이상은 Developer까지 |
| POL-08 제3조 | 편집(Can edit)은 소속 부서 문서에 한해 대리 이상 |
| POL-02 | TF 구성원 자격 근거에 `tf_members`(TF 명단) 사용 명시 |

---

## 10. DB에 반영되는 것

- `users`에 `job_rank`(직급), `job_family`(직무), `rank_level`(직급 숫자, 자동 계산) 추가
- `departments`에 `head_id`(부서장) 추가
- 새 테이블 6개: `tfs`, `tf_members`, `resources`, `permissions`, `department_budgets`, `access_ceilings`
- `permissions`가 모의 SaaS의 현재 권한이다. 권한을 부여하면 행이 생기고, 재조회로 확인한다.
- `access_ceilings`는 Spring 규칙이 상한을 코드에 직접 두면 생략할 수 있다. 백엔드 B와 정한다. ☐
- 직원 번호(E-001 등)는 DB에 없고 `seed.sql` 주석에만 있다. 로그인 ID로 연결한다.
