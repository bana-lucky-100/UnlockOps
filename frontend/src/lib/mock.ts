/**
 * 백엔드가 아직 주지 않는 응답(비용 영향 · 회수 점검)을 화면에서 먼저 확인하기 위한 목업 스위치.
 * .env.local 에 VITE_UO_MOCK=true 를 넣었을 때만 켜진다. 기본값은 꺼짐이라 배포 화면에는 영향이 없다.
 * 목업이 보일 때는 화면에 '목업 데이터' 표시를 붙여 실제 값과 헷갈리지 않게 한다.
 */
export const MOCK = import.meta.env?.VITE_UO_MOCK === 'true'
