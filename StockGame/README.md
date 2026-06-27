# StockGame (주식 미니게임 / ministock)

S-Future-Conference 행사용 **주식 모의투자 미니게임** 모듈입니다.
참가자(팀)가 인증키로 자기 팀을 확인한 뒤, 정해진 종목(A~F)에 자금을 베팅하면 고정 수익률 시나리오에 따라 정산되어 팀의 보유 현금이 즉시 갱신됩니다.

> 빌드/배포 스크립트와 docker-compose에서는 **`ministock`(`jasgo/sfc_ministock`)** 이라는 이름으로 다뤄집니다. 폴더명은 `StockGame`입니다.

---

## 기술 스택

| 구분 | 내용 |
|------|------|
| 런타임 | Node.js 22 (**CommonJS**, `require` 사용 — 다른 Node 모듈과 달리 ESM 아님) |
| 웹 프레임워크 | Express 5 |
| 데이터 처리 | xlsx (SheetJS), iconv-lite (UTF-8 BOM 인코딩 처리) |
| 프론트엔드 | 순수 HTML/CSS/JS (Tailwind 유틸 클래스 사용) |
| 컨테이너 | Docker (`node:22-alpine`) |
| 포트 | **3005** |

---

## 디렉터리 구조

```
StockGame/
├── index.js              # Express 서버 + 정산 로직 (진입점)
├── package.json
├── Dockerfile
└── public/
    └── index.html        # 모의투자 입력 화면 (인증키 → 종목 선택 → 베팅)
```

데이터 파일은 자체 보관하지 않고 **V2 모듈의 데이터를 공유**합니다:
`../V2/data/Teams.csv.csv` (읽기 + 쓰기)

---

## 동작 방식

1. 참가자가 `index.html`에서 인증키를 입력하면 `/api/verify-key`로 팀과 현재 보유 현금을 확인합니다.
2. 종목(A~F)과 베팅 금액을 입력해 `/api/invest`를 호출합니다.
3. 서버가 인증키–팀 일치를 2차 검증한 뒤, 고정 수익률 시나리오로 정산하고 `Teams.csv.csv`의 해당 팀 `capital`(현금)을 갱신합니다.
4. 갱신된 CSV는 V2 메인 화면·ManagerDashboard에도 반영됩니다.

### 하드코딩된 게임 설정 (행사마다 바뀔 수 있는 값)
- **종목별 수익률 배수(`STOCK_SCENARIO`):** A 0.7 · B 0.5 · C 0.3 · D 1.3 · E 1.5 · F 1.7
  (예: D 종목에 베팅하면 베팅액 × 1.3 으로 정산)
- **팀 인증키(`SECRET_KEYS`):** 1588→OpenAI · 2424→Tesla · 3693→삼성전자 · 4885→Palantir · 5959→Instagram · 6256→Amazon · 7749→Google · 8881→NVIDIA
- **팀명→ID 매핑(`TEAM_NAME_TO_ID`):** OpenAI→A · Tesla→B · 삼성전자→C · Palantir→D · Instagram→E · Amazon→F · Google→G · NVIDIA→H

> ⚠️ 동일한 인증키·팀 매핑이 StockGame과 ManagerDashboard 양쪽에 각각 하드코딩되어 있습니다. 값을 바꿀 때는 두 곳을 모두 수정해야 합니다.

---

## API

| 경로 | 메서드 | 설명 |
|------|--------|------|
| `/api/verify-key` | GET | 쿼리 `key`로 인증키 검증, 팀명·팀ID·현재 현금 반환 |
| `/api/invest` | POST | body `{ secretKey, teamId, stockId, amount }` — 인증 2차 검증 후 정산, CSV 갱신 |

정산 공식: `정산액 = round(베팅액 × 수익률 / 10) × 10` (원 단위 절사), `새 현금 = 현재현금 − 베팅액 + 정산액`

---

## 실행 방법

### 로컬 실행
```bash
cd StockGame
npm install
# ⚠️ iconv-lite가 코드에서 쓰이는데 package.json에 누락되어 있으니 함께 설치
npm install iconv-lite
node index.js      # → http://localhost:3005
```
> 상위 경로에 `../V2/data/Teams.csv.csv` 가 존재해야 정상 동작합니다.

### Docker / compose
```bash
./build.sh ministock           # jasgo/sfc_ministock:latest 빌드·푸시
docker compose up -d ministock # compose의 ministock 서비스
```
compose에서는 `./V2/data`가 컨테이너 `/V2/data`로 마운트됩니다(서버 코드의 상대경로 `../V2/data`와 맞물림).

---

## ⚠️ 인계 시 확인 / 주의 사항

- **`iconv-lite` 의존성 누락.** `index.js`가 `require('iconv-lite')`를 호출하지만 `package.json`의 dependencies에는 없습니다. Docker 이미지나 `npm install`만으로는 모듈을 못 찾아 실행이 실패하므로, package.json에 추가하는 것을 권장합니다.
- **V2 데이터에 강하게 결합.** `../V2/data/Teams.csv.csv` 경로가 하드코딩되어 있습니다. 단독 실행 시 이 파일이 없으면 동작하지 않으며, compose에서도 V2 데이터 볼륨 마운트가 전제입니다.
- **CSV 동시 접근 / 인코딩.** Teams CSV를 V2·ManagerDashboard와 공유하며 읽고 씁니다. 한글 깨짐 방지를 위해 쓰기 시 UTF-8 BOM(`\ufeff`)을 강제 주입하므로(pandas `utf-8-sig` 호환), 인코딩 규칙을 함부로 바꾸면 다른 모듈에서 깨질 수 있습니다.
- **CSV 컬럼 의존.** 코드가 `Team`, `capital` 컬럼명을 기준으로 동작합니다. CSV 헤더가 바뀌면 정산이 실패합니다.
- **하드코딩된 인증키/수익률**은 행사 시나리오에 종속적인 값입니다. 새 행사 준비 시 반드시 검토하세요.
