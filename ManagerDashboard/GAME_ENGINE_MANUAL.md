# GAME_ENGINE_MANUAL.md

`game_engine.py` 유지보수 및 기능 추가 매뉴얼입니다.

이 문서는 다음 작업자가 `BPGameEngine`의 구조, 데이터 흐름, 주요 함수 책임, 수정 시 주의점을 빠르게 파악하도록 작성되었습니다.

## 1. 엔진의 역할

`game_engine.py`는 S-Future-Conference 관리자 서버의 핵심 게임 정산 엔진입니다.

주요 책임은 다음과 같습니다.

- V2 모듈과 공유하는 CSV 파일 로드/저장
- 빅게임 주식 주문 검증 및 체결
- 미니게임 보상 정산
- 자회사 편입/해방 규칙 처리
- 사보타지 및 강제거래 처리
- 라운드 백업 및 롤백
- 대시보드와 참가자 화면에 전달할 데이터 패킷 생성

HTTP, Socket.IO, 파일 감시 같은 전송 계층은 `server.py`가 담당합니다.
게임 규칙과 데이터 정산 로직은 가능하면 `game_engine.py` 안에 유지하세요.

## 2. 외부 데이터 계약

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

## 3. 전체 처리 흐름

### 서버 시작

1. `server.py`가 `BPGameEngine`을 생성합니다.
2. 생성자에서 `load_data()`가 호출되어 CSV가 메모리의 DataFrame으로 올라옵니다.
3. `server.py`가 `BP_TradeOrder.csv` 파일 감시를 시작합니다.

### 빅게임 주문 처리

1. V2가 `BP_TradeOrder.csv`에 주문 행을 추가합니다.
2. `server.py`의 파일 워처가 변경을 감지합니다.
3. `engine.parse_and_execute_orders()`가 호출됩니다.
4. 엔진은 `last_order_idx` 이후 신규 주문만 처리합니다.
5. 각 주문은 `TradeOrder`로 파싱됩니다.
6. `validate_trade_order()`에서 인증, 매핑, 잔고, 보유량을 검증합니다.
7. 유효한 주문은 `_execute_buy_order()` 또는 `_execute_sell_order()`로 체결됩니다.
8. 체결 후 `refresh_state_after_settlement()`가 자회사/자산/CSV 저장을 일괄 처리합니다.

### 빅게임 종료 코드

종료 코드는 다음 주문입니다.

- 보안키: `1588`
- 매매 타입: `매수`
- 대상 팀: `OpenAI`
- 수량: `20061226`

이 주문이 들어오면 `_finalize_big_game_round()`가 호출되어 라운드 마감 주가 계산, 총자산 갱신, CSV 저장, 백업 생성을 수행합니다.

## 4. 주요 데이터 구조

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

- `buyer_team_name`: 인증키로 찾은 구매/판매 주체 이름
- `buyer_team_id`: 내부 팀 ID, 예: `A`
- `trade_action`: 내부 매매 타입, `Buy` 또는 `Sell`
- `target_team_name`: 대상 팀 이름
- `target_team_id`: 대상 팀 ID
- `quantity`: 수량
- `row_index`: CSV 행 번호

### `TradeValidationResult`

주문 검증 결과입니다.

필드:

- `is_valid`: 검증 성공 여부
- `message`: 성공 또는 실패 메시지
- `order`: 검증 성공 시 `ResolvedTradeOrder`
- `is_end_game_signal`: 빅게임 종료 코드 여부

## 5. `BPGameEngine` 섹션별 설명

### 5.1 상수와 매핑

클래스 상단의 매핑 값은 외부 서비스와 맞아야 합니다.

- `SECRET_KEY_TO_TEAM_NAME`: 보안키를 팀 이름으로 변환
- `TEAM_NAME_TO_ID`: 팀 이름을 내부 팀 ID로 변환
- `TRADE_TYPE_TO_ACTION`: `매수`/`매도`를 `Buy`/`Sell`로 변환
- `MINIGAME_BASE_REWARDS`: 미니게임 1~3위 기본 보상
- `SABOTAGE_STOCK_REWARDS`: 사보타지 순위별 회수 주식 수

값을 바꾸면 StockGame/V2 등 sibling 서비스의 동일 매핑도 함께 확인해야 합니다.

### 5.2 CSV 로드/저장

주요 함수:

- `load_data()`
- `save_to_disk()`
- `_csv_path()`
- `_parse_subsidiary_cell()`
- `_serialize_subsidiary_cell()`

`subsidiary` 컬럼은 CSV에서는 문자열이지만, 메모리에서는 리스트로 다룹니다.
따라서 CSV를 읽을 때는 `_parse_subsidiary_cell()`, 저장할 때는 `_serialize_subsidiary_cell()`을 거칩니다.

새 CSV 파일을 추가해야 한다면 다음 순서로 작업하세요.

1. 파일 경로 헬퍼를 `_csv_path()`로 구성합니다.
2. `load_data()`에서 DataFrame을 로드합니다.
3. 필요한 경우 저장 로직을 `save_to_disk()`에 추가합니다.
4. 인코딩은 기본적으로 `CSV_ENCODING`을 사용합니다.

### 5.3 라운드 백업과 롤백

주요 함수:

- `create_backup()`
- `restore_backup()`

백업은 메모리에만 저장됩니다.
서버가 재시작되면 백업 히스토리는 사라집니다.

`restore_backup()`은 저장된 DataFrame 복사본과 `last_order_idx`를 복원합니다.
주문 CSV 자체를 되돌리지는 않습니다.

### 5.4 재무 지표와 자회사 갱신

주요 함수:

- `update_financial_metrics()`
- `update_subsidiary_relationships()`
- `refresh_state_after_settlement()`
- `_release_uncontrolled_subsidiaries()`
- `_acquire_new_subsidiaries()`

`refresh_state_after_settlement()`는 상태 변경 후 호출하는 표준 후처리 함수입니다.
주문 체결, 사보타지, 강제거래처럼 holdings나 capital이 바뀌는 기능을 추가한다면 대부분 이 함수를 마지막에 호출해야 합니다.

처리 내용:

1. 자회사 편입/해방 규칙 갱신
2. 총자산 및 순위 재계산
3. CSV 저장

자회사 기준 지분율은 `SUBSIDIARY_CONTROL_THRESHOLD` 상수로 관리합니다.
현재 기준은 51입니다.

### 5.5 미니게임 보상

주요 함수:

- `process_minigame_reward()`
- `_parse_winning_team_ids()`
- `_grant_minigame_rank_rewards()`
- `_grant_minigame_participation_rewards()`
- `_grant_subsidiary_dividends()`

미니게임 정산 흐름:

1. 입력 문자열을 팀 ID 리스트로 변환합니다.
2. 1~3위 보상을 지급합니다.
3. 나머지 팀에 참가 보상을 지급합니다.
4. 자회사 관계를 갱신합니다.
5. 자회사 보너스 배당을 지급합니다.
6. 총자산 갱신 후 CSV에 저장합니다.

보상 공식이나 금액을 바꿀 때는 클래스 상단 상수를 먼저 확인하세요.

### 5.6 사보타지

주요 함수:

- `find_sabotage_candidates()`
- `execute_sabotage()`

`find_sabotage_candidates()`는 미니게임 우승팀 중 모회사가 있는 팀을 찾아 `(team_id, rank)` 리스트로 반환합니다.

`execute_sabotage()`는 자회사가 모회사로부터 자기 주식을 일부 회수하고 비용을 차감합니다.
순위별 회수량은 `SABOTAGE_STOCK_REWARDS`를 사용합니다.

### 5.7 강제거래

주요 함수:

- `execute_forced_trade()`

강제거래는 모회사가 보유한 자회사 주식을 자회사에게 강제로 매각하는 처리입니다.

검증 조건:

- 해당 팀에 모회사가 있어야 합니다.
- 자회사 자본금이 거래 비용보다 충분해야 합니다.
- 모회사가 해당 주식을 충분히 보유해야 합니다.

성공 시 양쪽 자본금과 주식 보유량을 갱신한 뒤 `refresh_state_after_settlement()`를 호출합니다.

### 5.8 주문 검증과 체결

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

`validate_trade_order()`가 주문 검증의 단일 진입점입니다.
HTTP 주문 검증과 CSV 주문 정산이 같은 검증 로직을 사용하도록 설계되어 있습니다.

새 주문 규칙을 추가할 때는 다음 순서로 수정하세요.

1. 원본 주문 필드가 필요하면 `TradeOrder`에 추가합니다.
2. 내부 변환 필드가 필요하면 `ResolvedTradeOrder`에 추가합니다.
3. 공통 검증이면 `validate_trade_order()`에 추가합니다.
4. 매수 전용 검증이면 `_validate_buy_order()`에 추가합니다.
5. 매도 전용 검증이면 `_validate_sell_order()`에 추가합니다.
6. 실제 상태 변경은 `_execute_buy_order()` 또는 `_execute_sell_order()`에 추가합니다.
7. 상태 변경 후 자산/CSV 갱신이 필요하면 `refresh_state_after_settlement()` 호출 흐름을 유지합니다.

`check_order_validity()`는 `server.py`의 `/check_order` 라우트 호환용 래퍼입니다.
가능하면 새 로직은 `check_order_validity()`가 아니라 `validate_trade_order()`에 추가하세요.

### 5.9 대시보드 조회

주요 함수:

- `get_dashboard_data()`
- `get_team_status()`
- `get_team_holdings()`
- `get_single_team_dashboard_packet()`

`get_dashboard_data()`는 시스템 팀 `S`를 제외하고 대시보드용 팀 목록을 반환합니다.

참가자별 화면에 새 필드를 내려야 한다면 다음 중 한 곳을 수정하세요.

- 팀 기본 정보: `get_team_status()`
- 보유 주식 정보: `get_team_holdings()`
- 둘을 합친 패킷: `get_single_team_dashboard_packet()`

## 6. 기존 이름 호환 래퍼

아래 함수들은 기존 `server.py` 또는 이전 코드와의 호환성을 위해 남겨둔 이름입니다.

- `check_and_update_subsidiaries()`
- `check_and_update_subsidaries_and_metrics()`
- `check_sabotage()`

새 코드를 작성할 때는 가능하면 다음 이름을 사용하세요.

- `update_subsidiary_relationships()`
- `refresh_state_after_settlement()`
- `find_sabotage_candidates()`

주의: `check_and_update_subsidaries_and_metrics()`는 기존 오타가 포함된 함수명입니다.
외부 호출 호환을 위해 유지하고 있으므로, 삭제하려면 `server.py` 호출부를 먼저 바꿔야 합니다.

## 7. 기능 추가 가이드

### 새 정산 이벤트를 추가하는 경우

예: 특별 보너스, 패널티, 이벤트 카드 등

권장 흐름:

1. 공개 메서드를 하나 만듭니다. 예: `execute_special_bonus(...)`
2. 입력값 검증을 먼저 수행합니다.
3. `teams_df` 또는 `holdings_df`를 변경합니다.
4. 자회사/총자산/CSV 저장이 필요하면 `refresh_state_after_settlement()`를 호출합니다.
5. 성공/실패 여부를 `bool` 또는 명확한 결과 객체로 반환합니다.
6. Socket.IO 로그는 가능하면 `server.py`에서 처리하고, 엔진 내부 규칙 로그는 `self.log()`를 사용합니다.

### 새 주문 제한 규칙을 추가하는 경우

예: 특정 라운드 매수 제한, 팀별 한도, 보유 비율 제한

권장 위치:

- 매수 제한: `_validate_buy_order()`
- 매도 제한: `_validate_sell_order()`
- 매수/매도 공통 제한: `validate_trade_order()`

실제 DataFrame을 변경하는 검증 코드를 만들지 마세요.
검증 함수는 상태를 바꾸지 않는 것이 원칙입니다.

### 새 CSV 컬럼을 추가하는 경우

주의할 점:

- V2, StockGame 등 다른 서비스가 같은 파일을 읽는지 확인합니다.
- 컬럼명은 외부 계약입니다.
- 기존 CSV에 없는 컬럼을 코드에서 바로 참조하면 운영 중 예외가 날 수 있습니다.
- 기본값 보정 로직이 필요하면 `load_data()`에 명시적으로 추가하세요.

### 새 팀을 추가하는 경우

확인해야 할 곳:

- `ACTIVE_TEAM_IDS`
- `SECRET_KEY_TO_TEAM_NAME`
- `TEAM_NAME_TO_ID`
- `Holdings.csv.csv`의 `stockX` 컬럼
- `Teams.csv.csv` 행
- `Subsidiarys.csv.csv` 컬럼
- `server.py`에서 `ALL_TEAMS.index(...)`를 사용하는 소켓 라우팅
- sibling 서비스의 동일 팀 매핑

팀 추가는 단순 상수 변경만으로 끝나지 않을 가능성이 큽니다.

## 8. 수정 시 주의할 불변 조건

다음 조건은 운영 중 깨지면 장애로 이어질 수 있습니다.

- `BP_TradeOrder.csv`는 append-style 누적 파일로 취급합니다.
- `last_order_idx`는 이미 처리한 주문 수를 의미합니다.
- 주문 검증 함수는 상태를 변경하지 않습니다.
- 주문 실행 함수만 capital/holdings를 변경합니다.
- 상태 변경 후에는 필요한 경우 `refresh_state_after_settlement()`를 호출합니다.
- CSV 저장 인코딩은 `utf-8-sig`를 유지합니다.
- `Team == "S"`는 시스템 계정입니다.
- 서버 재시작 시 메모리 백업과 `last_order_idx` 상태가 초기화됩니다.

## 9. 검증 방법

좁은 Python 변경 후 최소 검증:

```bash
python -m py_compile server.py game_engine.py main.py
```

현재 환경에서 `python` 명령이 없으면 다음을 사용하세요.

```bash
python3 -m py_compile server.py game_engine.py main.py
```

읽기 기반 엔진 확인:

```bash
python3 -c "from game_engine import BPGameEngine; e=BPGameEngine(); print(len(e.get_dashboard_data())); print(e.check_order_validity('1588','매수','Tesla',1))"
```

정산 흐름을 실제로 확인하려면 테스트용 CSV를 준비한 뒤 서버를 실행합니다.

```bash
python server.py
```

서버 실행 후 확인할 것:

- `http://localhost:3003` 접속 가능 여부
- 대시보드 초기 데이터 표시
- 빅게임 start/stop 상태 이벤트
- 주문 CSV 변경 시 `SYSTEM_LOG`와 `SCOREBOARD_REFRESH` 송출
- 미니게임 정산 후 capital/total asset/rank 갱신

주의: 실제 공유 CSV를 사용하는 환경에서 `parse_and_execute_orders()`를 직접 실행하면 데이터가 변경됩니다.
테스트 시에는 반드시 복사본 데이터 디렉터리를 사용하세요.

## 10. 자주 발생하는 문제

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

### 자회사 정보가 문자열/리스트로 섞임

메모리에서는 `subsidiary`를 리스트로 다룹니다.
CSV 저장 전에는 문자열로 변환합니다.

직접 DataFrame을 조작할 때 `subsidiary`에 문자열을 넣지 말고 리스트를 유지하세요.

### 대시보드에 시스템 팀이 보임

`get_dashboard_data()`는 `Team == "S"`를 제외합니다.
시스템 팀이 화면에 나온다면 CSV의 시스템 행 Team 값이 `S`인지 확인하세요.

## 11. 리팩터링 방향성

향후 더 크게 정리한다면 다음 분리가 자연스럽습니다.

- `models.py`: `TradeOrder`, `ResolvedTradeOrder`, `TradeValidationResult`
- `csv_store.py`: CSV 로드/저장과 직렬화
- `trade_service.py`: 주문 검증/체결
- `subsidiary_service.py`: 자회사 편입/해방
- `round_service.py`: 백업/롤백/라운드 마감

다만 현재는 운영 중인 코드와 `server.py` 의존성을 고려해 `game_engine.py` 안에서 섹션별 모듈화만 적용한 상태입니다.
파일 분리는 테스트가 충분히 마련된 뒤 진행하는 것을 권장합니다.
