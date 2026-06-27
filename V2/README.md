# V2 (메인 게임 서버 / 발표 화면)

S-Future-Conference의 **중심 모듈**입니다. 행사장에 띄우는 메인 발표·차트 화면, 참가자용 주식 주문(거래) 화면, 그리고 게임 데이터를 읽고 쓰는 데이터 API를 제공합니다.

전체 시스템에서 **데이터 허브** 역할을 하며, `V2/data/` 폴더의 CSV 파일을 StockGame·ManagerDashboard 등 다른 모듈과 공유합니다.

---

## 기술 스택

| 구분 | 내용 |
|------|------|
| 런타임 | Node.js 22 (ESM, `"type": "module"`) |
| 웹 프레임워크 | Express 5 |
| 데이터 처리 | xlsx (SheetJS) — CSV/엑셀 파싱·기록 |
| 프론트엔드 | 순수 HTML/CSS/JS, Socket.IO 클라이언트, reveal.js 계열 슬라이드(`main.html`) |
| 컨테이너 | Docker (`node:22-alpine`) |
| 포트 | **3000** |

---

## 디렉터리 구조

```
V2/
├── index.js                # Express 서버 (진입점)
├── api/
│   └── data.js             # 데이터 조회/주문 기록 라우터 (/api)
├── package.json
├── Dockerfile
├── .dockerignore
├── public/
│   ├── main.html           # 메인 발표 슬라이드 화면
│   ├── index.html          # 게임 입장 화면
│   ├── test.html           # 주식 주문(거래) 센터 화면
│   ├── modal.html
│   ├── barchart.html / doughnutchart.html  # 차트 화면
│   ├── main.js             # 4초 주기로 /api/data 폴링 → 차트 갱신
│   ├── chart.js
│   ├── event_handler.js    # ManagerDashboard(3003)와 Socket.IO 통신
│   ├── style.css / globals.css
│   └── img/                # 기업 로고/도형 에셋
└── data/                   # ⚠️ git 미포함(.gitignore). 공유 CSV 데이터 폴더
    ├── Teams.csv.csv
    ├── Holdings.csv.csv
    ├── Subsidiarys.csv.csv
    └── BP_TradeOrder.csv   # 주문이 기록되는 파일
```

---

## 동작 방식

- **데이터 표시:** `public/main.js`가 4초마다 `/api/data`를 호출해 `data/` 폴더의 CSV를 읽어와 차트를 갱신합니다.
- **주문 처리:** 참가자가 `/trade_order` 화면에서 주문을 넣으면 `/api/order`로 전달되어 `data/BP_TradeOrder.csv`에 한 줄씩 기록됩니다. 이 파일은 ManagerDashboard(빅게임 엔진)가 실시간 감시하며 정산합니다.
- **실시간 이벤트:** `event_handler.js`는 ManagerDashboard 서버(포트 3003)에 직접 Socket.IO로 연결되어 강제 거래·사보타주 등의 이벤트를 주고받습니다. (V2 서버 자체는 Socket.IO를 띄우지 않음)

```
[참가자 trade_order] --/api/order--> [V2 서버] --기록--> data/BP_TradeOrder.csv
                                                              │ (감시)
[메인 화면 main.js] --4초 폴링 /api/data--> [V2 서버]          ▼
                                                     [ManagerDashboard 정산]
```

---

## 라우트 / API

### HTTP 페이지
| 경로 | 설명 |
|------|------|
| `/main` | 메인 발표 슬라이드 (`public/main.html`) |
| `/trade_order` | 주식 주문 센터 (`public/test.html`) |
| `/` | 게임 입장 화면 (`public/index.html`, 정적 제공) |

### API (`/api`, `api/data.js`)
| 경로 | 메서드 | 설명 |
|------|--------|------|
| `/api/data` | GET | `Teams / Holdings / Subsidiarys` CSV를 읽어 차트용 데이터로 가공·반환 |
| `/api/order` | GET | 쿼리스트링(`securityKey`, `orderType`, `team`, `quantity`)을 받아 `BP_TradeOrder.csv`에 기록 |
| `/api/status` | GET | 헬스 체크용 샘플 응답 |

---

## 실행 방법

### 로컬 실행
```bash
cd V2
npm install
npm start          # node index.js → http://localhost:3000
```
> `data/` 폴더와 CSV 파일들이 있어야 정상 동작합니다. (git에 없으므로 별도 확보 필요)

### Docker / compose
```bash
./build.sh v2                  # jasgo/sfc_v2:latest 빌드·푸시
docker compose up -d server1   # compose의 server1 서비스
```
compose에서는 `./V2/data`가 컨테이너 `/app/data`로 마운트됩니다.

---

## ⚠️ 인계 시 확인 / 주의 사항

- **`data/` 폴더가 git에 없습니다.** `.gitignore`로 제외되어 있어 실제 CSV(`Teams.csv.csv`, `Holdings.csv.csv`, `Subsidiarys.csv.csv`)는 별도로 받아야 합니다. 파일명에 `.csv.csv`처럼 확장자가 중복돼 있으니 그대로 유지해야 다른 모듈(StockGame, ManagerDashboard)과 경로가 맞습니다.
- **하드코딩된 서버 주소.** `public/event_handler.js`와 `public/test.html`이 ManagerDashboard 서버를 특정 EC2 주소(`ec2-15-165-202-145.ap-northeast-2.compute.amazonaws.com:3003`)로 직접 호출합니다. 서버가 바뀌면 이 파일들을 수정해야 합니다.
- **여러 모듈이 같은 파일을 동시에 읽고 씁니다.** `BP_TradeOrder.csv`(V2 기록 ↔ ManagerDashboard 감시)와 `Teams.csv.csv`(V2 읽기 ↔ StockGame 읽기·쓰기 ↔ ManagerDashboard 읽기·쓰기)에 동시 접근이 발생하므로, 경합·인코딩(BOM) 문제에 유의해야 합니다. 인코딩은 `utf-8-sig`(BOM) 기준으로 맞춰져 있습니다.
- **파일 쓰기 권한.** `XLSX.writeFile`로 CSV를 덮어쓰므로, 컨테이너/호스트의 `data/` 폴더 쓰기 권한이 필요합니다(코드 주석에도 macOS 권한 주의가 적혀 있음).
