# ManagerDashboard (관리자 마스터 대시보드 / 게임 엔진)

S-Future-Conference의 **운영자용 통합 제어 서버이자 메인 게임 엔진**입니다.
빅게임(실시간 주식 거래 게임)의 주문 정산, 미니게임 보상 정산, 자회사/사보타주/강제거래 같은 특수 이벤트, 라운드 백업·롤백을 총괄합니다. 참가자 주문이 기록되는 CSV를 실시간 감시하다가 새 주문이 들어오면 정산하고, 그 결과를 Socket.IO로 전 화면에 송출합니다.

> 빌드/배포에서는 **`admin`(`jasgo/sfc_admin`)** 이라는 이름으로 다뤄집니다. 폴더명은 `ManagerDashboard`입니다.

---

## 기술 스택

| 구분 | 내용 |
|------|------|
| 런타임 | Python 3.14 |
| 웹 프레임워크 | FastAPI + Starlette |
| ASGI 서버 | Uvicorn |
| 실시간 통신 | python-socketio (ASGI 모드, `socketio.ASGIApp`) |
| 데이터 처리 | pandas, numpy |
| 파일 감시 | watchdog (CSV 변경 실시간 감지) |
| 검증 | pydantic |
| 컨테이너 | Docker (`python:3.14-slim`) |
| 포트 | **3003** |

---

## 디렉터리 구조

```
ManagerDashboard/
├── server.py             # FastAPI + Socket.IO 서버 (진입점, port 3003)
├── game_engine.py        # BPGameEngine — 핵심 게임 로직
├── index.html            # 관리자 대시보드 화면
├── requirements.txt
├── Dockerfile
└── main.py               # (보조 스크립트)
```

데이터 파일은 자체 보관하지 않고 **V2 모듈의 데이터를 공유**합니다(`../V2/data/`):
`Teams.csv.csv`, `Holdings.csv.csv`, `Subsidiarys.csv.csv`, `BP_TradeOrder.csv`

---

## 동작 방식

`server.py`(웹/소켓 계층) + `game_engine.py`(`BPGameEngine`, 게임 로직)의 2층 구조입니다.

1. 서버 시작 시 watchdog가 `../V2/data/BP_TradeOrder.csv`를 감시 시작합니다.
2. 관리자가 대시보드에서 **빅게임 start**를 누르면(`control_biggame`) 주문 수집이 활성화됩니다.
3. 참가자 주문이 V2를 통해 `BP_TradeOrder.csv`에 추가되면, 파일 변경이 감지되어 엔진이 `parse_and_execute_orders()`로 신규 주문만 파싱·정산합니다.
4. 정산 결과 로그(`SYSTEM_LOG`)와 갱신된 스코어보드(`SCOREBOARD_REFRESH`)를 Socket.IO로 전 클라이언트에 송출하고, 변경된 자산을 CSV에 저장합니다.
5. 미니게임 보상, 사보타주, 강제거래, 라운드 롤백 등은 대시보드의 Socket.IO 이벤트로 호출됩니다.

```
[참가자 주문] → V2 → BP_TradeOrder.csv
                          │ (watchdog 감지)
                          ▼
        [BPGameEngine 정산] → CSV 저장 + Socket.IO 송출 → [대시보드/참가자 화면]
```

### BPGameEngine 주요 기능 (game_engine.py)
- `load_data` / `save_to_disk`: 3종 CSV 로드·저장 (`utf-8-sig`, index=`Team`)
- `parse_and_execute_orders`: 빅게임 매수/매도 주문 정산 (가격·시총·현금 갱신, `last_order_idx`로 신규분만 처리)
- `process_minigame_reward`: 미니게임 순위 보상 정산 (1~3위 차등 + 배당)
- `update_financial_metrics`: 총자산(주식가치 + 현금) 재계산
- `check_and_update_subsidiaries` / `execute_sabotage` / `execute_forced_trade`: 자회사·사보타주·강제거래 특수 룰
- `create_backup` / `restore_backup`: 라운드별 백업 및 롤백

---

## 라우트 / 이벤트

### HTTP
| 경로 | 메서드 | 설명 |
|------|--------|------|
| `/` | GET | 관리자 대시보드 (`index.html`) |
| `/check_order` | POST | 주문 유효성 검증 (빅게임 진행 중에만 통과) — V2 주문 화면이 호출 |

### Socket.IO 이벤트 (대시보드 → 서버)
| 이벤트 | 설명 |
|--------|------|
| `control_biggame` | 빅게임 start/stop |
| `process_minigame` | 미니게임 보상 정산 |
| `rollback_previous_round` | 직전 라운드로 롤백 |

### Socket.IO 이벤트 (서버 → 전체)
`SCOREBOARD_REFRESH`(스코어보드 갱신), `SYSTEM_LOG`(로그 콘솔), `STATUS_UPDATE`(진행 상태) 등

---

## 실행 방법

### 로컬 실행
```bash
cd ManagerDashboard
pip install -r requirements.txt   # Python 3.14 기준
python server.py                  # → http://localhost:3003 (host 0.0.0.0)
```
> 상위 경로에 `../V2/data/` 폴더와 CSV들이 있어야 합니다. 폴더가 없으면 startup 시 자동 생성하지만, CSV 내용은 별도로 채워야 정상 동작합니다.

### Docker / compose
```bash
./build.sh admin               # jasgo/sfc_admin:latest 빌드·푸시
```
> **현재 `docker-compose.yml`에서 admin 서비스는 주석 처리되어 비활성** 상태입니다. 통합 실행하려면 compose의 admin 블록 주석을 해제해야 합니다(아래 주의사항 참고).

---

## ⚠️ 인계 시 확인 / 주의 사항

- **compose에서 비활성 상태.** 메인 게임 엔진임에도 `docker-compose.yml`의 admin 서비스가 주석 처리되어 있습니다. 그대로 `docker compose up` 하면 정산 엔진 없이 나머지만 뜹니다.
- **마운트 경로 정합성.** 주석 처리된 compose 블록은 `./V2/data:/app/V2/data`로 마운트하는데, 코드(`server.py`/`game_engine.py`)는 작업 디렉터리 기준 `../V2/data`를 바라봅니다. 활성화 전에 컨테이너 작업경로와 마운트 경로가 실제로 맞는지 반드시 확인하세요.
- **공유 CSV 동시 접근.** `Teams.csv.csv` 등을 V2·StockGame과 함께 읽고 씁니다. 인코딩은 `utf-8-sig`(BOM) 기준이며, 컬럼명(`Team`, `capital`, `price`, `total asset`, `parent`, `subsidiary` 등)에 강하게 의존합니다. CSV 스키마가 바뀌면 정산이 깨집니다.
- **하드코딩된 인증키/팀 매핑.** `SECRET_KEYS`, `TEAMS_MAP`이 엔진에 하드코딩되어 있고 StockGame에도 같은 값이 별도로 박혀 있습니다. 값 변경 시 두 모듈을 함께 수정해야 합니다.
- **상태가 메모리 기반.** 빅게임 진행 플래그(`is_biggame_running`), 라운드 백업 히스토리(`teams_history` 등), `last_order_idx`가 메모리에 보관됩니다. 서버 재시작 시 진행 상태·롤백 히스토리가 초기화되므로, 행사 도중 재시작은 신중해야 합니다.
- **주문 누적 파싱 방식.** `BP_TradeOrder.csv`는 계속 누적되며 `last_order_idx` 이후 행만 신규로 처리합니다. 파일을 수동으로 비우거나 편집하면 인덱스가 어긋날 수 있습니다.
- **로직의 원본은 Jupyter 노트북.** 코드 주석에 따르면 게임 로직은 `GoogleDriveFiles/BP_Conference_MainGame_Auto.ipynb`의 로직을 옮긴 것입니다. 규칙 변경 시 노트북과의 정합성도 확인이 필요할 수 있습니다.
