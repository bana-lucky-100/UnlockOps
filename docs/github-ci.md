# GitHub main 보호 설정과 기본 CI

이 문서는 기본 CI의 사용 방법과 GitHub에서 직접 적용할 `main` 보호 설정을 정리합니다. 현재 연결된 개인 액세스 토큰은 보호 설정 조회 시 `403 Resource not accessible by personal access token`을 반환하여, 보호 설정을 직접 변경하지 않았습니다.

## 1. 기본 CI 구성

[ci.yml](../.github/workflows/ci.yml) 하나에서 실행 조건과 검사 단계를 관리합니다. 별도 검사 스크립트나 패키지 설치는 필요하지 않습니다.

- `main` 대상 PR 생성·수정, `main` 반영, 수동 실행에서 동작합니다.
- 검사 이름은 **Repository checks**입니다. 보호 규칙에서 사용할 때 이 이름을 선택합니다.
- GitHub 기본 토큰의 `contents: read`만 사용합니다. 별도 API 키나 서버 비밀번호는 필요하지 않습니다.
- 변경 파일의 끝에 생긴 불필요한 빈 줄·공백 뒤 탭·충돌 표시를 검사합니다. Markdown 줄 끝 공백은 허용합니다.
- 설정 파일 문법, 문서 링크, 환경변수 값은 별도 자동 검사 대상이 아닙니다.

현재 서비스 프로젝트는 초기화 전이므로 Vue·Spring·Python 서비스의 빌드·테스트는 포함하지 않았습니다. 서비스가 준비되면 실제 실행 명령에 맞는 job을 추가합니다.

## 2. 로컬 검사

레포 루트에서 Git만 있으면 실행할 수 있습니다. 아래 명령은 현재 작업 폴더의 추적 파일 변경을 검사합니다. CI에서는 PR 기준 커밋 또는 푸시 전 커밋부터의 변경을 검사합니다.

```sh
git -c core.whitespace=blank-at-eof,space-before-tab diff --check
```

스테이징한 변경은 다음 명령으로 검사합니다.

```sh
git -c core.whitespace=blank-at-eof,space-before-tab diff --cached --check
```

새 파일은 스테이징한 뒤 검사합니다.

## 3. CI 활성화

1. 이 변경을 작업 브랜치에 커밋하고 푸시합니다.
2. 기본 브랜치 `main`을 대상으로 PR을 만듭니다.
3. PR의 **Checks** 또는 저장소 **Actions → CI**에서 **Repository checks**가 통과하는지 확인합니다.
4. Actions가 꺼져 있다면 관리자 계정으로 **Settings → Actions → General**에서 허용합니다. 조직 정책이 제한하면 조직 관리자에게 확인합니다.

필수 검사로 지정하기 전 실제 PR에서 검사가 성공한 것을 먼저 확인합니다. 아직 실행되지 않은 검사 이름을 강제로 등록하면 PR이 대기 상태로 남을 수 있습니다.

## 4. main 보호 설정

[UnlockOps 브랜치 설정](https://github.com/bana-lucky-100/UnlockOps/settings/branches)을 관리자 계정으로 엽니다. 기존 `main` 보호 규칙이 있으면 새 규칙을 겹쳐 만들기보다 해당 규칙을 확인해 수정합니다.

1. **Settings → Branches → Add classic branch protection rule**을 선택합니다. 화면에 따라 버튼이 **Add rule**로 표시될 수 있습니다.
2. **Branch name pattern**에 `main`을 입력합니다.
3. 아래 항목을 설정하고 저장합니다.

| 설정 | 권장 값 |
| --- | --- |
| Require a pull request before merging | 켜기 |
| Require approvals | 1명 |
| Dismiss stale pull request approvals when new commits are pushed | 켜기 |
| Require conversation resolution before merging | 켜기 |
| Do not allow bypassing the above settings | 켜기: 관리자도 같은 규칙 적용 |
| Allow force pushes | 끄기 |
| Allow deletions | 끄기 |

4. 3절의 CI가 실제로 통과한 뒤 같은 규칙에서 **Require status checks to pass before merging**을 켭니다.
5. **Repository checks**를 검색해 추가합니다. **Require branches to be up to date before merging**도 켜는 것을 권장합니다.
6. 저장 후 `main` 보호 규칙과 필수 검사 이름이 표시되는지 확인합니다.

리뷰 승인은 PR 작성자 이외에 저장소 쓰기 권한이 있는 팀원이 해야 합니다. 관리자에게도 규칙을 적용하면 작성자 혼자 승인하고 병합할 수 없습니다.

## 5. API로 설정하려는 경우

GitHub 계정의 관리자 역할과 개인 액세스 토큰의 권한은 별개입니다. 보호 규칙을 변경하려면 토큰이 `UnlockOps`에 접근할 수 있고 **Repository permissions → Administration: Read and write** 권한을 가져야 합니다.

토큰 값을 문서나 채팅에 붙이지 않습니다. 브라우저에서 4절을 직접 설정하면 현재 토큰의 권한을 변경할 필요가 없습니다.

## 6. 서비스 초기화 후 확장

- Frontend: 결정한 Node 버전과 잠금 파일로 설치하고 lint·빌드·테스트를 실행합니다.
- Backend: 결정한 JDK 버전과 Gradle 또는 Maven Wrapper로 빌드·테스트를 실행합니다.
- Python: 결정한 Python 버전과 의존성으로 코드 검사·테스트를 실행합니다.
- 서비스별 작업을 추가해도 **Repository checks** 이름은 유지합니다. 새 작업도 필수 검사로 만들려면 실제 통과 후 GitHub 보호 규칙에 추가합니다.

기본 CI 워크플로는 경로 필터 없이 실행합니다. 필수 검사를 경로 필터로 건너뛰게 변경하면 PR이 검사 대기 상태로 남을 수 있으므로 함께 확인합니다.

## 참고

- [GitHub 브랜치 보호](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
- [GitHub 보호 브랜치 API](https://docs.github.com/en/rest/branches/branch-protection)
