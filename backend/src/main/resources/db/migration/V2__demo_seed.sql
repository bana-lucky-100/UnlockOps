INSERT INTO departments(id,code,name) VALUES
('00000000-0000-0000-0000-000000000001','DEV','개발팀'),
('00000000-0000-0000-0000-000000000002','DATA','데이터팀'),
('00000000-0000-0000-0000-000000000003','OPS','운영팀'),
('00000000-0000-0000-0000-000000000004','HR','인사팀'),
('00000000-0000-0000-0000-000000000005','FIN','재무팀');
-- Password hashes are filled once by DemoSeed using DEMO_PASSWORD, never logged.
INSERT INTO users(id,employee_no,login_id,email,name,role,department_id,job_grade,job_family) VALUES
('10000000-0000-0000-0000-000000000001','E-001','kim_dev','kim.dev@example.test','김개발','REQUESTER','00000000-0000-0000-0000-000000000001','사원','DEV'),
('10000000-0000-0000-0000-000000000002','E-002','park_lead','park.lead@example.test','박리더','APPROVER','00000000-0000-0000-0000-000000000001','차장','DEV'),
('10000000-0000-0000-0000-000000000003','E-003','lee_ops','lee.ops@example.test','이운영','REQUESTER','00000000-0000-0000-0000-000000000003','대리','NON_DEV'),
('10000000-0000-0000-0000-000000000004','E-004','choi_copilot','choi@example.test','최코파','REQUESTER','00000000-0000-0000-0000-000000000001','과장','DEV'),
('10000000-0000-0000-0000-000000000005','E-005','jung_data','jung@example.test','정데이터','REQUESTER','00000000-0000-0000-0000-000000000002','대리','DEV'),
('10000000-0000-0000-0000-000000000006','E-006','han_hr','han@example.test','한인사','APPROVER','00000000-0000-0000-0000-000000000004','과장','NON_DEV'),
('10000000-0000-0000-0000-000000000007','E-007','oh_dev','oh@example.test','오개발','REQUESTER','00000000-0000-0000-0000-000000000001','대리','DEV'),
('10000000-0000-0000-0000-000000000008','E-008','yoon_head','yoon@example.test','윤부장','APPROVER','00000000-0000-0000-0000-000000000001','부장','DEV'),
('10000000-0000-0000-0000-000000000009','E-009','song_ops','song@example.test','송운영','APPROVER','00000000-0000-0000-0000-000000000003','부장','NON_DEV'),
('10000000-0000-0000-0000-000000000010','E-010','seo_fin','seo@example.test','서재무','APPROVER','00000000-0000-0000-0000-000000000005','과장','NON_DEV'),
('10000000-0000-0000-0000-000000000011','E-011','hong_data','hong@example.test','홍데이터','APPROVER','00000000-0000-0000-0000-000000000002','부장','DEV');
UPDATE departments SET head_id = CASE code
 WHEN 'DEV' THEN '10000000-0000-0000-0000-000000000008'::uuid
 WHEN 'DATA' THEN '10000000-0000-0000-0000-000000000011'::uuid
 WHEN 'OPS' THEN '10000000-0000-0000-0000-000000000009'::uuid
 WHEN 'HR' THEN '10000000-0000-0000-0000-000000000006'::uuid
 WHEN 'FIN' THEN '10000000-0000-0000-0000-000000000010'::uuid END;
INSERT INTO tfs VALUES ('30000000-0000-0000-0000-000000000001','PAY','결제 개편 TF','10000000-0000-0000-0000-000000000002','2026-10-19',NULL);
INSERT INTO tf_members(tf_id,user_id) VALUES
('30000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000001'),
('30000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000002');
INSERT INTO department_budgets(department_id,remaining_monthly_amount,unit_monthly_price) VALUES
('00000000-0000-0000-0000-000000000001',150,19),
('00000000-0000-0000-0000-000000000002',10,19),
('00000000-0000-0000-0000-000000000003',80,19),
('00000000-0000-0000-0000-000000000004',50,19),
('00000000-0000-0000-0000-000000000005',50,19);
INSERT INTO resources(id,platform,external_id,name,aliases,access_scope,owner_department_id,tf_id,security_grade,designated_department_id) VALUES
('20000000-0000-0000-0000-000000000001','GITHUB','payment-core','payment-core','["결제 저장소"]','TF','00000000-0000-0000-0000-000000000001','30000000-0000-0000-0000-000000000001',NULL,NULL),
('20000000-0000-0000-0000-000000000002','GITHUB','internal-tools','internal-tools','[]','GENERAL','00000000-0000-0000-0000-000000000001',NULL,NULL,NULL),
('20000000-0000-0000-0000-000000000003','GITHUB','docs-site','docs-site','[]','GENERAL','00000000-0000-0000-0000-000000000003',NULL,NULL,NULL),
('20000000-0000-0000-0000-000000000004','GITHUB','copilot-seat','Copilot 좌석','["copilot", "코파일럿", "코파일럿 좌석"]','SEAT',NULL,NULL,NULL,NULL),
('20000000-0000-0000-0000-000000000005','JIRA','PAY','PAY 프로젝트','["PAY 프로젝트"]','TF','00000000-0000-0000-0000-000000000001','30000000-0000-0000-0000-000000000001',NULL,NULL),
('20000000-0000-0000-0000-000000000006','JIRA','DEV','DEV 프로젝트','["DEV 프로젝트"]','GENERAL','00000000-0000-0000-0000-000000000001',NULL,NULL,NULL),
('20000000-0000-0000-0000-000000000007','JIRA','OPS','OPS 프로젝트','["OPS 프로젝트"]','GENERAL','00000000-0000-0000-0000-000000000003',NULL,NULL,NULL),
('20000000-0000-0000-0000-000000000008','SLACK','#general','#general','[]','GENERAL',NULL,NULL,NULL,NULL),
('20000000-0000-0000-0000-000000000009','SLACK','#dev-team','#dev-team','[]','GENERAL','00000000-0000-0000-0000-000000000001',NULL,NULL,NULL),
('20000000-0000-0000-0000-000000000010','SLACK','#proj-payment','#proj-payment','[]','TF','00000000-0000-0000-0000-000000000001','30000000-0000-0000-0000-000000000001',NULL,NULL),
('20000000-0000-0000-0000-000000000011','SLACK','#ops-alerts','#ops-alerts','[]','GENERAL','00000000-0000-0000-0000-000000000003',NULL,NULL,NULL),
('20000000-0000-0000-0000-000000000012','NOTION','company-notice','전사 공지','["전사 공지"]','GENERAL','00000000-0000-0000-0000-000000000004',NULL,'GENERAL',NULL),
('20000000-0000-0000-0000-000000000013','NOTION','dev-wiki','개발팀 위키','["개발팀 위키"]','DEPARTMENT','00000000-0000-0000-0000-000000000001',NULL,'INTERNAL',NULL),
('20000000-0000-0000-0000-000000000014','NOTION','pay-wiki','[PAY] 결제 개편 TF 위키','["결제 개편 TF 위키", "결제 위키", "[PAY] 위키"]','TF','00000000-0000-0000-0000-000000000001','30000000-0000-0000-0000-000000000001','INTERNAL',NULL),
('20000000-0000-0000-0000-000000000015','NOTION','hr-confidential','인사팀 기밀 자료','["인사팀 기밀 자료", "인사 기밀"]','CONFIDENTIAL','00000000-0000-0000-0000-000000000004',NULL,'CONFIDENTIAL','00000000-0000-0000-0000-000000000004');
-- Seed current permissions directly from section 5 of the supplied company matrix.
INSERT INTO permissions(user_id,resource_id,saas_role)
SELECT u.id,r.id,s.role FROM (VALUES
('kim_dev','internal-tools','Read'),('kim_dev','DEV','Viewer'),('kim_dev','#general','Member'),('kim_dev','#dev-team','Member'),('kim_dev','company-notice','Can view'),('kim_dev','dev-wiki','Can view'),
('park_lead','payment-core','Write'),('park_lead','internal-tools','Write'),('park_lead','PAY','Developer'),('park_lead','DEV','Developer'),('park_lead','#general','Member'),('park_lead','#dev-team','Member'),('park_lead','#proj-payment','Member'),('park_lead','company-notice','Can view'),('park_lead','dev-wiki','Can edit'),('park_lead','pay-wiki','Can view'),
('lee_ops','docs-site','Read'),('lee_ops','OPS','Viewer'),('lee_ops','#general','Member'),('lee_ops','#ops-alerts','Member'),('lee_ops','company-notice','Can view'),
('choi_copilot','internal-tools','Write'),('choi_copilot','copilot-seat','Seat'),('choi_copilot','DEV','Developer'),('choi_copilot','#general','Member'),('choi_copilot','#dev-team','Member'),('choi_copilot','company-notice','Can view'),('choi_copilot','dev-wiki','Can edit'),
('jung_data','internal-tools','Write'),('jung_data','DEV','Developer'),('jung_data','#general','Member'),('jung_data','company-notice','Can view'),
('han_hr','#general','Member'),('han_hr','company-notice','Can view'),('han_hr','hr-confidential','Can view'),
('oh_dev','internal-tools','Write'),('oh_dev','DEV','Developer'),('oh_dev','#general','Member'),('oh_dev','#dev-team','Member'),('oh_dev','company-notice','Can view'),('oh_dev','dev-wiki','Can edit'),
('yoon_head','internal-tools','Write'),('yoon_head','DEV','Developer'),('yoon_head','#general','Member'),('yoon_head','#dev-team','Member'),('yoon_head','company-notice','Can view'),('yoon_head','dev-wiki','Can edit'),
('song_ops','docs-site','Read'),('song_ops','OPS','Viewer'),('song_ops','#general','Member'),('song_ops','#ops-alerts','Member'),('song_ops','company-notice','Can view'),
('seo_fin','#general','Member'),('seo_fin','company-notice','Can view'),
('hong_data','internal-tools','Write'),('hong_data','DEV','Developer'),('hong_data','#general','Member'),('hong_data','company-notice','Can view')
) AS s(login_id,resource_key,role)
JOIN users u ON u.login_id=s.login_id JOIN resources r ON r.external_id=s.resource_key;
INSERT INTO github_teams(id,resource_id,saas_role)
SELECT external_id||'-'||lower(x.role), id, x.role FROM resources
CROSS JOIN (VALUES ('Read'),('Write')) AS x(role)
WHERE platform='GITHUB' AND access_scope <> 'SEAT';
INSERT INTO github_team_members(team_id,user_id)
SELECT t.id,p.user_id FROM permissions p JOIN github_teams t
ON t.resource_id=p.resource_id AND t.saas_role=p.saas_role;
INSERT INTO jira_role_permissions(resource_id,saas_role,can_browse)
SELECT r.id,x.role,TRUE FROM resources r CROSS JOIN (VALUES ('Viewer'),('Developer')) AS x(role)
WHERE r.platform='JIRA';
