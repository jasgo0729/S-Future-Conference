# ManagerDashboard 유지보수 통합 매뉴얼

이 문서는 `ManagerDashboard`의 핵심 파일인 `server.py`, `game_engine.py`, `index.html`을 다음 작업자가 한 번에 이해하고 수정할 수 있도록 정리한 인계 문서입니다.

대상 파일:

- `server.py`: FastAPI, Socket.IO, 파일 감시, 프론트엔드 이벤트 연결
- `game_engine.py`: CSV 기반 게임 상태, 정산 규칙, 주문 검증/체결, 특수 이벤트 처리
- `index.html`: 관리자 대시보드 UI, Socket.IO 클라이언트, 운영 버튼과 테이블 렌더링

## 1. 전체 구조 요약

ManagerDashboard는 관리자용 웹 대시보드이면서 메인 게임 정산 서버입니다.

큰 책임 분리는 다음과 같습니다.

- `index.html`: 관리자가 버튼을 누르고 현재 팀 상태를 확인하는 화면
- `server.py`: HTTP/Socket.IO 요청을 받고 엔진을 호출하는 전송 계층
- `game_engine.py`: 실제 게임 규칙과 CSV 상태를 변경하는 비즈니스 로직
- `../V2/data/*.csv`: V2, StockGame 등 sibling 서비스와 공유하는 운영 데이터

기본 실행 흐름:

1. `python server.py` 실행
2. `server.py`가 `BPGameEngine`을 생성
3. `game_engine.py`가 `../V2/data/`의 CSV 파일을 로드
4. `server.py`가 `BP_TradeOrder.csv` 파일 감시 시작
5. 관리자가 `index.html` 대시보드에 접속
6. Socket.IO 연결 후 서버가 현재 스코어보드를 전송
7. 관리자가 빅게임/미니게임/롤백/수동 조정/강매 등을 실행
8. 서버가 엔진 메서드를 호출하고 결과를 Socket.IO로 다시 브로드캐스트

## 2. 책임 경계

### `index.html`이 담당할 일

- 버튼, 입력창, 모달 등 관리자 조작 UI 제공
- Socket.IO 이벤트 emit
- 서버가 보내는 `SYSTEM_LOG`, `STATUS_UPDATE`, `SCOREBOARD_REFRESH` 반영
- 화면 테이블 렌더링
- 사용자가 입력한 값에 대한 1차적인 UI 검증

`index.html`에서 직접 게임 규칙을 계산하지 마세요.
금액, 지분율, 자회사 여부, 정산 성공 여부는 서버/엔진이 최종 판단해야 합니다.

### `server.py`가 담당할 일

- HTTP 라우트 제공
- Socket.IO 이벤트 수신/응답
- 파일 워처 관리
- payload 형식 검증
- 연결된 참가자 sid 관리
- 엔진 호출 후 로그/스코어보드 송출

`server.py`는 transport/controller 계층입니다.
DataFrame을 직접 많이 조작하는 로직이 늘어나면 `game_engine.py`로 옮기는 것이 좋습니다.

### `game_engine.py`가 담당할 일

- CSV 로드/저장
- 주문 검증과 체결
- 라운드 마감 주가 계산
- 미니게임 보상 정산
- 자회사 편입/해방
- 사보타지
- 강제거래
- 라운드 백업/롤백
- 대시보드용 데이터 패킷 생성

게임 규칙이 바뀌면 우선 `game_engine.py`를 수정하세요.
`server.py`와 `index.html`은 새 규칙을 호출하거나 보여주는 역할만 맡는 편이 안전합니다.

## 3. 외부 데이터 계약

엔진은 기본적으로 `../V2/data/` 아래 CSV를 사용합니다.

필수 파일:

- `Teams.csv.csv`
- `Holdings.csv.csv`
- `Subsidiarys.csv.csv`
- `BP_TradeOrder.csv`

CSV 저장 인코딩은 `utf-8-sig`입니다.
다른 서비스도 같은 CSV를 읽고 쓰므로, 인코딩과 컬럼명을 임의로 변경하지 마세요.

중요 컬럼:

- `Team`
- `capital`
- `price`
- `price before`
- `price delta`
- `price ROR`
- `market capital`
- `total asset`
- `subsidiary`
- `parent`
- `parent name`
- `team rank`
- `team name`

`Holdings.csv.csv`는 `stockA`부터 `stockH`까지의 컬럼을 사용합니다.
`Team == "S"` 행은 시스템 보유 물량입니다.

`BP_TradeOrder.csv`는 append-style 누적 파일입니다.
무작정 초기화하거나 중간 행을 삭제하면 `last_order_idx`와 실제 주문 행이 어긋날 수 있습니다.

## 4. 서버 시작과 파일 감시

`server.py`의 주요 상수:

- `DATA_DIR`: 공유 데이터 폴더, 기본값 `../V2/data`
- `TRADE_ORDER_FILENAME`: 감시할 주문 파일, 기본값 `BP_TradeOrder.csv`
- `INDEX_HTML_PATH`: 관리자 화면 HTML 경로
- `EDITABLE_TEAM_FIELDS`: 수동 수정 허용 필드, 현재 `capital`, `price`
- `WATCHER_DEBOUNCE_SECONDS`: 파일 변경 중복 이벤트 방지 시간

서버 시작 흐름:

1. 전역에서 `engine = BPGameEngine(...)` 생성
2. FastAPI startup 이벤트에서 `asyncio` loop 저장
3. `../V2/data` 폴더 생성
4. watchdog `Observer` 시작
5. `OrderFileWatcherHandler`가 `BP_TradeOrder.csv` 변경을 감시

파일 변경 감지 흐름:

1. `OrderFileWatcherHandler.on_modified()` 호출
2. 빅게임 수집 중인지 확인
3. 감시 대상 파일인지 확인
4. debounce 검사
5. `trigger_order_pipeline()`을 asyncio loop에 등록
6. `engine.parse_and_execute_orders()` 호출
7. 처리 로그를 `SYSTEM_LOG`로 송출
8. 스코어보드를 `SCOREBOARD_REFRESH`로 송출

## 5. HTTP 라우트

### `GET /`

관리자 대시보드 HTML을 반환합니다.

관련 코드:

- `root()`
- `INDEX_HTML_PATH`

### `POST /check_order`

V2 주문 화면 등이 주문을 실제 CSV에 쓰기 전에 유효성을 확인하는 API입니다.

요청 모델:

- `secret_key`
- `trade_type`
- `target_id`
- `quantity`

처리 흐름:

1. 빅게임 진행 중인지 확인
2. `engine.check_order_validity(...)` 호출
3. 실패 시 HTTP 400 반환
4. 성공 시 `SUCCESS` 반환

주의:

- `quantity`는 Pydantic `Field(gt=0)`로 1 이상만 허용합니다.
- 최종 게임 규칙 검증은 `game_engine.py`의 `validate_trade_order()`가 담당합니다.

## 6. Socket.IO 이벤트 맵

### 클라이언트 연결

이벤트:

- `connect`
- `disconnect`

`connect` 처리:

1. 연결 로그 출력
2. 접속한 클라이언트에게만 현재 스코어보드 전송

`disconnect` 처리:

1. sid로 참가자 ID 조회
2. `userlist`에서 제거

관련 함수:

- `emit_scoreboard(room=sid)`
- `get_team_id_from_sid(sid)`

### 빅게임 제어

클라이언트 emit:

- `control_biggame`

payload:

```json
{ "action": "start" }
```

또는

```json
{ "action": "stop" }
```

서버 처리:

- `start`: `is_biggame_running = True`
- `stop`: `is_biggame_running = False`
- 상태는 `STATUS_UPDATE`로 송출
- 로그는 `SYSTEM_LOG`로 송출

### 미니게임 정산

클라이언트 emit:

- `process_minigame`

payload:

```json
{
  "winners": "A,D,E",
  "round": 1
}
```

서버 처리:

1. payload 형식 검증
2. `engine.process_minigame_reward(winners, round_num)` 호출
3. 성공 시 `SYSTEM_LOG`, `SCOREBOARD_REFRESH` 송출

UI는 미니게임 정산 직후 `check_sabotage_users`도 함께 emit합니다.

### 사보타지 후보 확인

클라이언트 emit:

- `check_sabotage_users`

payload:

```json
{ "winners": "A,D,E" }
```

서버 처리:

1. `engine.check_sabotage(...)` 호출
2. 모회사가 있는 우승팀만 추림
3. 참가자 sid를 찾아 해당 참가자에게만 `sabotage` 이벤트 전송

참가자가 연결되어 있지 않거나 모회사 holdings 정보가 없으면 로그를 남기고 건너뜁니다.

### 사보타지 응답 처리

클라이언트 emit:

- `process_sabotage`

payload 예:

```json
{
  "result": true,
  "id": "B",
  "rank": 0
}
```

서버 처리:

1. `result`를 안전하게 bool로 변환
2. 거절이면 로그만 송출
3. 팀 ID와 rank 검증
4. `engine.execute_sabotage(team_id, rank)` 호출
5. 성공 시 스코어보드 송출

주의:

- 문자열 `"false"`가 truthy로 처리되지 않도록 `parse_socket_bool()`을 사용합니다.
- rank는 `engine.SABOTAGE_STOCK_REWARDS` 범위 안이어야 합니다.

### 강제거래 요청

클라이언트 emit:

- `send_force_trade_request`

payload:

```json
{ "id": "B" }
```

서버 처리:

1. 대상 팀 상태 조회
2. 모회사 존재 여부 확인
3. 모회사 holdings 조회
4. 대상 참가자 sid 조회
5. 해당 참가자에게만 `check_force_trade` 이벤트 전송

payload로 보내는 값:

- `round_num`
- `parentName`
- `maxStock`
- `price`
- `capital`

### 강제거래 응답 처리

클라이언트 emit:

- `force_trade_response`

payload 예:

```json
{
  "result": true,
  "id": "2",
  "amount": 5
}
```

서버 처리:

1. 참가자 ID를 팀 ID로 변환
2. `result`를 안전하게 bool로 변환
3. 수량이 1 이상인지 검증
4. `engine.execute_forced_trade(team_id, amount)` 호출
5. 성공 시 스코어보드 송출

### 스코어보드 새로고침

클라이언트 emit:

- `request_scoreboard_refresh`

서버 처리:

1. `engine.load_data()`
2. `engine.update_financial_metrics()`
3. `engine.save_to_disk()`
4. `SCOREBOARD_REFRESH` 송출

주의:

- 이 이벤트는 CSV를 다시 읽고 저장합니다.
- 수동 CSV 편집 직후 화면을 맞추는 용도입니다.

### 수동 팀 데이터 수정

클라이언트 emit:

- `manual_team_data_adjustment`

payload:

```json
{
  "team_id": "A",
  "field": "capital",
  "value": 3000000
}
```

허용 필드:

- `capital`
- `price`

서버 처리:

1. 팀 ID, 필드, 값 검증
2. `engine.teams_df` 수정
3. `price` 변경 시 `market capital`도 갱신
4. `engine.update_financial_metrics()`
5. `engine.save_to_disk()`
6. 로그와 스코어보드 송출

주의:

- 수동 수정은 운영자 emergency override 성격입니다.
- 허용 필드를 추가하려면 `EDITABLE_TEAM_FIELDS`와 UI 모달 로직을 함께 수정하세요.

### 라운드 롤백

클라이언트 emit:

- `rollback_previous_round`

payload:

```json
{ "current_round": 2 }
```

서버 처리:

1. `round_to_restore = current_round - 1`
2. `engine.restore_backup(round_to_restore)` 호출
3. 성공 시 `engine.round_num` 조정
4. 스코어보드와 로그 송출

주의:

- 백업은 서버 프로세스 메모리에만 있습니다.
- 서버 재시작 후에는 이전 라운드 백업이 없습니다.
- 주문 CSV 파일 자체를 과거 상태로 되돌리지는 않습니다.

### 참가자 연결 등록

클라이언트 emit:

- `user_join`

payload:

```json
{ "id": "1" }
```

서버 처리:

- `userlist[user_id] = sid`

참가자 ID는 현재 `engine.ALL_TEAMS` 순서 기반으로 팀에 매핑됩니다.

예:

- `"1"` -> `A`
- `"2"` -> `B`
- `"3"` -> `C`

팀 추가/순서 변경 시 이 매핑 방식도 함께 점검해야 합니다.

## 7. `game_engine.py` 데이터 구조

### `TradeOrder`

CSV 또는 HTTP 요청에서 들어온 원본 주문입니다.

필드:

- `secret_key`: 참가자 인증키
- `trade_type_label`: CSV/프론트에서 들어온 매매 타입, 예: `매수`, `매도`
- `target_team_name`: 대상 팀 이름, 예: `Tesla`
- `quantity`: 주문 수량
- `row_index`: CSV 행 번호, HTTP 검증에서는 보통 `None`

### `ResolvedTradeOrder`

검증 과정에서 팀 이름과 매매 타입이 내부 ID로 변환된 주문입니다.

필드:

- `buyer_team_name`
- `buyer_team_id`
- `trade_action`
- `target_team_name`
- `target_team_id`
- `quantity`
- `row_index`

### `TradeValidationResult`

주문 검증 결과입니다.

필드:

- `is_valid`
- `message`
- `order`
- `is_end_game_signal`

## 8. `game_engine.py` 주요 섹션

### 8.1 상수와 매핑

주요 값:

- `CSV_ENCODING`
- `SYSTEM_TEAM_ID`
- `ACTIVE_TEAM_IDS`
- `SUBSIDIARY_CONTROL_THRESHOLD`
- `END_GAME_QUANTITY`
- `SECRET_KEY_TO_TEAM_NAME`
- `TEAM_NAME_TO_ID`
- `TRADE_TYPE_TO_ACTION`
- `MINIGAME_BASE_REWARDS`
- `SABOTAGE_STOCK_REWARDS`

값을 바꾸면 V2, StockGame 등 sibling 서비스의 동일 매핑도 확인해야 합니다.

### 8.2 CSV 로드/저장

주요 함수:

- `load_data()`
- `save_to_disk()`
- `_csv_path()`
- `_parse_subsidiary_cell()`
- `_serialize_subsidiary_cell()`

`subsidiary` 컬럼은 CSV에서는 문자열이지만, 메모리에서는 리스트로 다룹니다.
CSV를 읽을 때는 리스트로 파싱하고, 저장할 때는 문자열로 직렬화합니다.

### 8.3 라운드 백업과 롤백

주요 함수:

- `create_backup()`
- `restore_backup()`

백업 대상:

- `teams_df`
- `holdings_df`
- `last_order_idx`

백업은 메모리에만 저장됩니다.

### 8.4 재무 지표와 자회사 갱신

주요 함수:

- `update_financial_metrics()`
- `update_subsidiary_relationships()`
- `refresh_state_after_settlement()`
- `_release_uncontrolled_subsidiaries()`
- `_acquire_new_subsidiaries()`

`refresh_state_after_settlement()`는 상태 변경 후 호출하는 표준 후처리 함수입니다.
capital 또는 holdings가 바뀌는 기능을 추가하면 대부분 마지막에 이 함수를 호출해야 합니다.

### 8.5 미니게임 보상

주요 함수:

- `process_minigame_reward()`
- `_parse_winning_team_ids()`
- `_grant_minigame_rank_rewards()`
- `_grant_minigame_participation_rewards()`
- `_grant_subsidiary_dividends()`

미니게임 정산 흐름:

1. 우승팀 문자열 파싱
2. 1~3위 보상 지급
3. 나머지 팀 참가 보상 지급
4. 자회사 관계 갱신
5. 자회사 배당 지급
6. 총자산 갱신 및 CSV 저장

### 8.6 사보타지

주요 함수:

- `find_sabotage_candidates()`
- `execute_sabotage()`

`find_sabotage_candidates()`는 우승팀 중 모회사가 있는 팀을 찾습니다.
`execute_sabotage()`는 자회사가 모회사로부터 자기 주식을 일부 회수하고 비용을 차감합니다.

### 8.7 강제거래

주요 함수:

- `execute_forced_trade()`

검증 조건:

- 수량은 1 이상
- 해당 팀에 모회사가 있어야 함
- 자회사 자본금이 충분해야 함
- 모회사가 해당 주식을 충분히 보유해야 함

### 8.8 주문 검증과 체결

주요 함수:

- `parse_and_execute_orders()`
- `validate_trade_order()`
- `check_order_validity()`
- `_trade_order_from_csv_row()`
- `_validate_buy_order()`
- `_validate_sell_order()`
- `_execute_trade_order()`
- `_execute_buy_order()`
- `_execute_sell_order()`
- `_finalize_big_game_round()`

핵심 원칙:

- `validate_trade_order()`는 상태를 변경하지 않습니다.
- `_execute_*` 계열 함수가 실제 capital/holdings를 변경합니다.
- HTTP 검증과 CSV 주문 정산은 같은 검증 로직을 사용합니다.

빅게임 종료 코드는 다음 주문입니다.

- 보안키: `1588`
- 매매 타입: `매수`
- 대상 팀: `OpenAI`
- 수량: `20061226`

종료 코드가 들어오면 `_finalize_big_game_round()`가 주가, 시총, 수익률, 총자산을 갱신하고 백업을 생성합니다.

### 8.9 대시보드 조회

주요 함수:

- `get_dashboard_data()`
- `get_team_status()`
- `get_team_holdings()`
- `get_single_team_dashboard_packet()`

`get_dashboard_data()`는 `Team == "S"` 시스템 행을 제외합니다.

## 9. `index.html` 구조

`index.html`은 Tailwind CDN과 Socket.IO CDN을 사용하는 단일 HTML 관리자 화면입니다.

주요 UI 영역:

- 헤더와 서버 연결 표시
- 빅게임 start/stop 제어
- 미니게임 결과 입력
- 이전 라운드 롤백 버튼
- 팀 정보 테이블
- 수동 수정 모달
- 실시간 시스템 로그 콘솔

### 9.1 Socket.IO 연결

현재 코드는 다음처럼 현재 접속한 서버 기준으로 연결합니다.

```javascript
const socket = io({
    path: '/socket.io',
    transports: ['websocket']
});
```

하드코딩된 EC2 주소를 사용하지 않습니다.
서버 도메인이나 포트가 바뀌어도 같은 origin에서 열면 동작하도록 하기 위함입니다.

### 9.2 테이블 렌더링

주요 함수:

- `renderTeamTable(teams)`
- `normalizeSubsidiaries(value)`
- `formatMoney(value)`
- `escapeHtml(value)`

`renderTeamTable()`는 서버가 보내는 `SCOREBOARD_REFRESH` 데이터를 받아 팀 목록을 렌더링합니다.
정렬 기준은 `total asset` 내림차순입니다.

주의:

- 화면 표시 전에 `escapeHtml()`을 적용합니다.
- `subsidiary`가 리스트 또는 문자열로 들어와도 `normalizeSubsidiaries()`로 처리합니다.
- 빈 데이터가 오면 안내 행을 보여줍니다.

### 9.3 수동 수정 모달

주요 함수:

- `openEditValueModal(teamId, targetType, currentVal)`
- `closeEditModal()`
- `submitValueAdjustment()`

수정 가능 대상:

- `capital`
- `price`

UI는 0 이상의 숫자인지만 1차 검증합니다.
최종 허용 여부는 `server.py`의 `manual_team_data_adjustment` 이벤트에서 다시 검증합니다.

### 9.4 운영 버튼

주요 함수:

- `controlBigGame(action)`
- `submitMiniGame()`
- `rollbackPreviousRound()`
- `refreshTeamData()`
- `requestForcedTrade(childId)`

각 함수는 직접 정산하지 않고 Socket.IO 이벤트만 emit합니다.

### 9.5 로그 출력

주요 함수:

- `printSystemLog(message)`

로그는 `innerHTML += ...` 방식이 아니라 DOM API로 추가합니다.
서버 로그 메시지에 HTML이 섞여 있어도 실행되지 않도록 하기 위함입니다.

## 10. 세 파일을 함께 수정해야 하는 작업 예시

### 새 관리자 버튼을 추가하는 경우

예: 전체 팀 보너스 지급 버튼

수정 순서:

1. `game_engine.py`에 `execute_global_bonus(...)` 같은 공개 메서드 추가
2. 메서드 안에서 입력 검증, DataFrame 변경, `refresh_state_after_settlement()` 호출
3. `server.py`에 Socket.IO 이벤트 핸들러 추가
4. payload 검증 후 엔진 메서드 호출
5. 성공 시 `emit_system_log()`, `emit_scoreboard()` 호출
6. `index.html`에 버튼과 JS emit 함수 추가
7. 문서에 이벤트 payload와 처리 흐름 추가

### 새 주문 제한 규칙을 추가하는 경우

예: 특정 라운드에는 특정 종목 매수 금지

수정 위치:

- `game_engine.py`
  - 공통 제한: `validate_trade_order()`
  - 매수 제한: `_validate_buy_order()`
  - 매도 제한: `_validate_sell_order()`
- `server.py`
  - 일반적으로 수정 불필요
  - 새 에러 메시지를 별도로 매핑해야 할 때만 수정
- `index.html`
  - 일반적으로 수정 불필요
  - UI에서 사전 안내가 필요하면 문구 추가

### 새 수동 수정 필드를 추가하는 경우

예: `price before`를 관리자 화면에서 수정

수정 위치:

1. `server.py`
   - `EDITABLE_TEAM_FIELDS`에 필드 추가
   - 필드 변경 후 연계 갱신이 필요한지 확인
2. `index.html`
   - 테이블 컬럼 추가
   - `openEditValueModal()` 호출 추가
   - 모달 표시 문구 추가
3. `game_engine.py`
   - 직접 수정할 필요가 없는 경우가 많음
   - 해당 필드가 재무 계산에 영향을 주면 계산 함수 확인

### 새 팀을 추가하는 경우

확인할 곳:

- `game_engine.py`
  - `ACTIVE_TEAM_IDS`
  - `SECRET_KEY_TO_TEAM_NAME`
  - `TEAM_NAME_TO_ID`
- CSV
  - `Teams.csv.csv` 행 추가
  - `Holdings.csv.csv` 행과 `stockX` 컬럼 추가
  - `Subsidiarys.csv.csv` 관련 컬럼 추가
- `server.py`
  - 참가자 ID와 팀 ID 매핑 방식 확인
  - `get_participant_room()`, `team_id_from_participant_id()` 영향 확인
- `index.html`
  - 하드코딩된 팀 목록은 현재 없지만, 화면 폭과 테이블 컬럼 확인
- sibling 서비스
  - V2, StockGame의 팀 매핑과 인증키 확인

팀 추가는 단순 상수 변경으로 끝나지 않습니다.
CSV 스키마와 다른 서비스 매핑을 함께 확인해야 합니다.

### 새 참가자 대상 이벤트를 추가하는 경우

예: 특정 팀에게만 선택지를 보내야 하는 이벤트

수정 순서:

1. 참가자 화면이 `user_join`으로 ID를 등록하는지 확인
2. `server.py`에서 `get_participant_room(team_id)`로 sid 조회
3. 없으면 실패 로그를 남기고 return
4. `sio.emit(event_name, payload, room=target_room)` 사용
5. 참가자 응답 이벤트를 별도 핸들러로 구현
6. 응답 payload는 `parse_socket_bool()` 같은 헬퍼로 안전하게 해석

## 11. 수정 시 지켜야 할 불변 조건

- `BP_TradeOrder.csv`는 누적 파일로 취급합니다.
- `last_order_idx`는 이미 처리한 주문 수입니다.
- 주문 검증 함수는 상태를 변경하지 않습니다.
- 주문 실행 함수만 capital/holdings를 변경합니다.
- 상태 변경 후에는 필요한 경우 `refresh_state_after_settlement()`를 호출합니다.
- CSV 저장 인코딩은 `utf-8-sig`입니다.
- `Team == "S"`는 시스템 계정입니다.
- 서버 재시작 시 메모리 백업, `last_order_idx`, 빅게임 진행 플래그가 초기화됩니다.
- `index.html`은 게임 규칙을 직접 계산하지 않습니다.
- `server.py`는 payload 검증과 엔진 호출을 담당합니다.
- DataFrame 직접 수정이 늘어나면 엔진 메서드로 옮깁니다.
- 관리자 수동 수정 필드는 whitelist 방식으로 관리합니다.

## 12. 검증 방법

### Python 문법 검사

```bash
python -m py_compile server.py game_engine.py main.py
```

현재 환경에서 `python` 명령이 없으면 다음을 사용하세요.

```bash
python3 -m py_compile server.py game_engine.py main.py
```

### 엔진 읽기 기반 확인

```bash
python3 -c "from game_engine import BPGameEngine; e=BPGameEngine(); print(len(e.get_dashboard_data())); print(e.check_order_validity('1588','매수','Tesla',1))"
```

이 검사는 CSV를 읽고 주문 검증만 수행합니다.
정산 함수는 실제 CSV를 바꿀 수 있으므로 테스트 데이터 복사본에서 실행하세요.

### HTML 인라인 스크립트 문법 확인

Node.js가 있는 환경에서 다음 명령으로 inline script 문법을 확인할 수 있습니다.

```bash
node -e "const fs=require('fs'); const vm=require('vm'); const html=fs.readFileSync('index.html','utf8'); const scripts=[...html.matchAll(/<script(?:\\s[^>]*)?>([\\s\\S]*?)<\\/script>/g)].map(m=>m[1]); for (const script of scripts) { if (script.trim()) new vm.Script(script); } console.log('index inline scripts OK');"
```

### 서버 스모크 테스트

```bash
python server.py
```

확인할 것:

- `http://localhost:3003` 접속 가능 여부
- 접속 직후 스코어보드 표시
- 빅게임 start/stop 상태 변경
- `SYSTEM_LOG` 표시
- `request_scoreboard_refresh` 동작
- 미니게임 정산 후 capital/total asset/rank 갱신
- 수동 capital/price 수정 후 CSV와 테이블 반영

주의:

- 실제 공유 CSV 환경에서 스모크 테스트하면 데이터가 바뀔 수 있습니다.
- 정산 테스트는 가능하면 복사한 `data_dir`로 진행하세요.

## 13. 자주 발생하는 문제

### `ModuleNotFoundError: No module named 'socketio'`

현재 Python 환경에 requirements가 설치되지 않은 상태입니다.

해결:

```bash
pip install -r requirements.txt
```

또는 프로젝트 가상환경이 정상인지 확인하세요.

### `../V2/data/` 파일을 찾을 수 없음

엔진은 작업 디렉터리 기준 `../V2/data/`를 기본값으로 사용합니다.
다른 위치의 테스트 데이터를 쓰려면 생성자에 명시적으로 전달하세요.

```python
engine = BPGameEngine(data_dir="/path/to/test/data")
```

### 대시보드가 서버에 연결되지 않음

확인할 것:

- `server.py`가 실제로 실행 중인지
- 브라우저가 `http://localhost:3003` 또는 서버가 제공하는 같은 origin으로 접속했는지
- Socket.IO CDN 로드가 가능한지
- 브라우저 콘솔에 WebSocket 오류가 있는지

현재 `index.html`은 하드코딩된 EC2 주소를 쓰지 않고 같은 origin으로 Socket.IO에 연결합니다.

### 사보타지/강매 요청이 참가자에게 가지 않음

확인할 것:

- 참가자 클라이언트가 `user_join` 이벤트를 보냈는지
- `userlist`에 참가자 ID와 sid가 등록되어 있는지
- 팀 ID와 참가자 ID 매핑이 맞는지
- 대상 팀이 실제로 자회사 상태인지

### 자회사 정보가 문자열/리스트로 섞임

메모리에서는 `subsidiary`를 리스트로 다룹니다.
CSV 저장 전에는 문자열로 변환합니다.

직접 DataFrame을 조작할 때 `subsidiary`에 문자열을 넣지 말고 리스트를 유지하세요.

### 대시보드에 시스템 팀이 보임

`get_dashboard_data()`는 `Team == "S"`를 제외합니다.
시스템 팀이 화면에 나온다면 CSV의 시스템 행 Team 값이 `S`인지 확인하세요.

### 수동 수정이 반영되지 않음

확인할 것:

- 필드가 `EDITABLE_TEAM_FIELDS`에 포함되어 있는지
- `team_id`가 `engine.ALL_TEAMS`에 있는지
- 값이 0 이상의 정수인지
- `SCOREBOARD_REFRESH` 이벤트가 브라우저에 도착하는지

## 14. 리팩터링 방향성

현재는 운영 중인 코드와 `server.py` 의존성을 고려해 한 디렉터리 안에서 정리한 상태입니다.
향후 더 크게 정리한다면 다음 분리가 자연스럽습니다.

엔진 계층:

- `models.py`: `TradeOrder`, `ResolvedTradeOrder`, `TradeValidationResult`
- `csv_store.py`: CSV 로드/저장과 직렬화
- `trade_service.py`: 주문 검증/체결
- `subsidiary_service.py`: 자회사 편입/해방
- `round_service.py`: 백업/롤백/라운드 마감

서버 계층:

- `routes.py`: FastAPI HTTP 라우트
- `socket_handlers.py`: Socket.IO 이벤트 핸들러
- `watcher.py`: watchdog 파일 감시
- `connection_registry.py`: 참가자 sid 등록/조회

프론트엔드 계층:

- `index.html`: 정적 마크업
- `admin-dashboard.js`: Socket.IO와 UI 이벤트
- `admin-dashboard.css`: 별도 스타일

파일 분리는 테스트가 충분히 마련된 뒤 진행하는 것을 권장합니다.

## 15. 작업 전 체크리스트

코드를 수정하기 전에 다음을 확인하세요.

- 어떤 파일이 source of truth인지 정했는가?
- 게임 규칙 변경이면 `game_engine.py`에서 처리하는가?
- payload 또는 연결 문제면 `server.py`에서 처리하는가?
- 화면 표시 문제면 `index.html`에서 처리하는가?
- CSV 컬럼명 또는 인코딩을 바꾸지 않았는가?
- 실제 공유 CSV를 변경하는 테스트인지 인지했는가?
- 변경 후 `py_compile`과 HTML script 문법 검사를 했는가?
- 운영 중 서버 재시작으로 사라지는 메모리 상태가 있는지 확인했는가?
