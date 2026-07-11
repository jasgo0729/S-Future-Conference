import socketio
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import os
from pathlib import Path
from typing import Optional

from starlette.responses import FileResponse
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from pydantic import BaseModel, Field

from game_engine import BPGameEngine

DATA_DIR = Path("../V2/data")
TRADE_ORDER_FILENAME = "BP_TradeOrder.csv"
INDEX_HTML_PATH = Path(__file__).with_name("index.html")
EDITABLE_TEAM_FIELDS = {"capital", "price"}
WATCHER_DEBOUNCE_SECONDS = 0.5

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')
asgi_app = socketio.ASGIApp(sio, other_asgi_app=app)
is_biggame_running = False  # 대시보드 제어용 플래그
loop = None  # 워처 스레드와 비동기 루프를 연결할 통로
userlist = {}


def send_socket_log_to_dashboard(message: str):
    if loop:
        asyncio.run_coroutine_threadsafe(
            sio.emit('SYSTEM_LOG', {'message': message}),
            loop
        )


async def emit_system_log(message: str, room: Optional[str] = None):
    await sio.emit('SYSTEM_LOG', {'message': message}, room=room)


async def emit_scoreboard(room: Optional[str] = None):
    await sio.emit('SCOREBOARD_REFRESH', {'data': engine.get_dashboard_data()}, room=room)


def get_participant_room(team_id: str) -> Optional[str]:
    participant_id = str(engine.ALL_TEAMS.index(team_id) + 1) if team_id in engine.ALL_TEAMS else None
    return userlist.get(participant_id) if participant_id else None


def parse_socket_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def team_id_from_participant_id(participant_id) -> Optional[str]:
    try:
        team_index = int(participant_id) - 1
    except (TypeError, ValueError):
        return None

    if team_index < 0 or team_index >= len(engine.ALL_TEAMS):
        return None
    return engine.ALL_TEAMS[team_index]


engine = BPGameEngine(log_callback=send_socket_log_to_dashboard)


@app.on_event("startup")
async def startup_event():
    global loop
    loop = asyncio.get_running_loop()

    watch_dir = DATA_DIR.resolve()
    os.makedirs(watch_dir, exist_ok=True)

    handler = OrderFileWatcherHandler(TRADE_ORDER_FILENAME)
    observer = Observer()
    observer.schedule(handler, path=str(watch_dir), recursive=False)
    observer.start()

    app.state.file_observer = observer
    print(f"📢 [시스템 백그라운드] {TRADE_ORDER_FILENAME} 파일 감시 워처 가동 완료. (대기 상태)")


@app.on_event("shutdown")
def shutdown_event():
    if hasattr(app.state, "file_observer"):
        app.state.file_observer.stop()
        app.state.file_observer.join()
        print("📢 파일 워처 자원 반환 및 안전 종료 완료.")


@app.get("/")
async def root():
    return FileResponse(INDEX_HTML_PATH)


class OrderForm(BaseModel):
    secret_key: str
    trade_type: str
    target_id: str
    quantity: int = Field(gt=0)


@app.post("/check_order")
async def place_order(order: OrderForm):
    if not is_biggame_running:
        raise HTTPException(status_code=400, detail="현재 빅게임 진행중이 아닙니다.")

    is_valid, reason = engine.check_order_validity(order.secret_key, order.trade_type, order.target_id, order.quantity)
    if not is_valid:
        raise HTTPException(status_code=400, detail=reason)

    return {
        "status": "SUCCESS",
        "message": "주문 검증 통과 및 정상 접수 완결"
    }


@sio.event
async def connect(sid, environ):
    print('⚡ 클라이언트 연결됨:', sid)
    await emit_scoreboard(room=sid)


@sio.event
async def control_biggame(sid, data):
    global is_biggame_running
    data = data or {}
    action = data.get("action")

    if action == 'start':
        is_biggame_running = True
        await sio.emit('STATUS_UPDATE', {'status': 'RUNNING'})
        await emit_system_log("📈 [ADMIN] 빅게임 주문 수집 파이프라인이 가동되었습니다.")
    elif action == 'stop':
        is_biggame_running = False
        await sio.emit('STATUS_UPDATE', {'status': 'STOPPED'})
        await emit_system_log("⏸️ [ADMIN] 빅게임 주문 수집이 일시정지되었습니다.")
    else:
        await emit_system_log(f"⚠️ [ADMIN] 알 수 없는 빅게임 제어 액션입니다: {action}", room=sid)


@sio.event
async def process_minigame(sid, data):
    data = data or {}
    try:
        winners = data.get('winners', '')
        round_num = int(data.get('round', 0))
    except (TypeError, ValueError):
        await emit_system_log("❌ [ADMIN] 미니게임 정산 요청 형식이 올바르지 않습니다.", room=sid)
        return

    if engine.process_minigame_reward(winners, round_num):
        await emit_system_log("📈 [ADMIN] 미니게임 정산이 완료되었습니다.")
        await emit_scoreboard()
    else:
        await emit_system_log("❌ [ADMIN] 미니게임 정산이 취소되었습니다.", room=sid)


@sio.event
async def rollback_previous_round(sid, data):
    data = data or {}
    try:
        current_round = int(data.get("current_round", 1))
        round_to_restore = current_round - 1

        await sio.emit("SYSTEM_LOG", {
            "message": f"⏪ [롤백 시그널] 관리자({sid})가 {current_round}R에서 {round_to_restore}R 상태로 복구를 요청했습니다."
        })

        if round_to_restore < 0:
            await emit_system_log("❌ [롤백 실패] 0라운드 이전의 과거 데이터는 존재하지 않습니다.")
            return

        is_success = engine.restore_backup(round_to_restore)

        if is_success:
            engine.round_num = round_to_restore
            await emit_scoreboard()
            await sio.emit("SYSTEM_LOG", {
                "message": f"✅ [롤백 성공] 전역 데이터가 제 {round_to_restore}라운드 마감 상태로 복원되었으며, 엔진 라운드가 {round_to_restore}R로 정정되었습니다."
            })
        else:
            await sio.emit("SYSTEM_LOG", {
                "message": f"❌ [롤백 거부] 백엔드 엔진에 {round_to_restore}R 백업본이 마크되어 있지 않습니다."
            })
    except Exception as e:
        print(f"❌ 롤백 핸들러 내부 크래시: {str(e)}")
        await sio.emit("SYSTEM_LOG", {"message": f"⚠️ [시스템 오류] 롤백 연산 처리 중 런타임 버그 발생: {str(e)}"})


@sio.event
async def check_sabotage_users(sid, data):
    data = data or {}
    sabotage_list = engine.check_sabotage(data.get('winners', ''))
    if not sabotage_list:
        return
    for team_id, rank in sabotage_list:
        team = engine.get_team_status(team_id)
        if not team:
            continue

        holdings = engine.get_team_holdings(team['parent'])
        target_room = get_participant_room(team_id)
        if not holdings or not target_room:
            await emit_system_log(f"⚠️ [사보타지] {team_id}팀 참가자 연결 또는 모회사 보유 정보가 없어 요청을 건너뜁니다.")
            continue

        req = {
            "id": team_id,
            "rank": rank,
            "parent_name": team['parent name'],
            "available_stock": holdings[f'stock{team_id}']
        }
        await sio.emit('sabotage', req, room=target_room)


@sio.event
async def request_scoreboard_refresh(sid, data):
    engine.load_data()
    engine.update_financial_metrics()
    engine.save_to_disk()
    await emit_scoreboard()

@sio.event
async def manual_team_data_adjustment(sid, data):
    data = data or {}
    team_id = data.get("team_id", "").upper()
    field = data.get("field")
    new_value = data.get("value")

    if not team_id or not field or new_value is None:
        await emit_system_log("❌ [수동 조정 에러] 필수 입력값이 누락되었습니다.", room=sid)
        return

    if team_id not in engine.ALL_TEAMS or field not in EDITABLE_TEAM_FIELDS:
        await emit_system_log(f"❌ [수동 조정 에러] 허용되지 않은 수정 대상입니다. team={team_id}, field={field}", room=sid)
        return

    try:
        parsed_value = int(new_value)
        if parsed_value < 0:
            raise ValueError("negative value")
    except (TypeError, ValueError):
        await emit_system_log(f"❌ [수동 조정 에러] 0 이상의 정수만 입력할 수 있습니다. 입력값: {new_value}", room=sid)
        return

    try:
        engine.teams_df.at[team_id, field] = parsed_value
        if field == "price":
            engine.teams_df.at[team_id, "market capital"] = parsed_value * 100

        engine.update_financial_metrics()
        engine.save_to_disk()

        log_msg = f"⚙️ [ADMIN HARD MOD] {team_id}팀의 {field} 수치가 관리자에 의해 {parsed_value:,}원으로 수동 갱신되었습니다."
        print(log_msg)
        await emit_system_log(log_msg)
        await emit_scoreboard()
    except Exception as exc:
        error_msg = f"❌ [수동 조정 에러] {team_id} 데이터 정정 연산 실패: {exc}"
        print(error_msg)
        await emit_system_log(error_msg)


@sio.event
async def user_join(sid, data):
    data = data or {}
    user_id = str(data.get('id', ''))
    if not user_id:
        return
    userlist[user_id] = sid
    print(userlist)


@sio.event
async def send_force_trade_request(sid, data):
    data = data or {}
    child_id = data.get('id')
    team = engine.get_team_status(child_id) if child_id else None
    if not team or team['parent'] == 'X':
        await emit_system_log(f"❌ [강매 요청 실패] {child_id}팀은 강매 대상이 아닙니다.", room=sid)
        return

    holdings = engine.get_team_holdings(team['parent'])
    target_room = get_participant_room(child_id)
    if not holdings or not target_room:
        await emit_system_log(f"❌ [강매 요청 실패] {child_id}팀 참가자 연결 또는 모회사 보유 정보가 없습니다.", room=sid)
        return

    req = {
        'round_num': engine.round_num,
        'parentName': team['parent name'],
        'maxStock': holdings[f"stock{child_id}"],
        'price': team['price'] * (engine.round_num if engine.round_num >= 2 else 2) / 2,
        'capital': team['capital']
    }
    await sio.emit('check_force_trade', req, room=target_room)


@sio.event
async def force_trade_response(sid, data):
    data = data or {}
    team_id = team_id_from_participant_id(data.get('id'))
    if not team_id:
        await emit_system_log(f"❌ [강매 응답 실패] 알 수 없는 참가자 ID입니다: {data.get('id')}", room=sid)
        return

    result = parse_socket_bool(data.get('result'))
    if not result:
        await emit_system_log(f"[ADMIN] {team_id}팀의 강매가 취소되었습니다.")
        return

    try:
        amount = int(data.get('amount', 0))
    except (TypeError, ValueError):
        await emit_system_log(f"❌ [강매 실패] {team_id}팀의 강매 수량이 올바르지 않습니다.", room=sid)
        return
    if amount <= 0:
        await emit_system_log(f"❌ [강매 실패] {team_id}팀의 강매 수량은 1 이상이어야 합니다.", room=sid)
        return

    if engine.execute_forced_trade(team_id, amount):
        await emit_scoreboard()
    else:
        await emit_system_log(f"❌ [강매 실패] {team_id}팀의 강매 조건을 만족하지 못했습니다.")


@sio.event
async def process_sabotage(sid, data):
    data = data or {}
    result = parse_socket_bool(data.get('result'))
    if not result:
        await emit_system_log(f"[ADMIN] {get_team_id_from_sid(sid)}팀의 사보타지가 취소되었습니다.")
        return

    team_id = data.get('id')
    try:
        rank = int(data.get('rank'))
    except (TypeError, ValueError):
        await emit_system_log(f"❌ [사보타지 실패] {team_id}팀의 순위 정보가 올바르지 않습니다.", room=sid)
        return

    if team_id not in engine.ALL_TEAMS:
        await emit_system_log(f"❌ [사보타지 실패] 알 수 없는 팀 ID입니다: {team_id}", room=sid)
        return
    team = engine.get_team_status(team_id)
    if not team or team["parent"] == "X":
        await emit_system_log(f"❌ [사보타지 실패] {team_id}팀은 현재 사보타지 대상이 아닙니다.", room=sid)
        return
    if rank < 0 or rank >= len(engine.SABOTAGE_STOCK_REWARDS):
        await emit_system_log(f"❌ [사보타지 실패] {team_id}팀의 순위 범위가 올바르지 않습니다: {rank}", room=sid)
        return

    if engine.execute_sabotage(team_id, rank):
        await emit_scoreboard()


@sio.event
async def disconnect(sid):
    print('❌ 클라이언트 연결 해제:', sid)
    user_id = get_team_id_from_sid(sid)
    if user_id is not None:
        userlist.pop(user_id, None)


class OrderFileWatcherHandler(FileSystemEventHandler):
    def __init__(self, filename: str):
        self.filename = filename
        self.last_triggered_time = 0

    def on_modified(self, event):
        global is_biggame_running, loop
        if not is_biggame_running or event.is_directory:
            return
        if os.path.basename(event.src_path) != self.filename or not loop:
            return

        current_time = loop.time()
        if current_time - self.last_triggered_time < WATCHER_DEBOUNCE_SECONDS:
            return

        self.last_triggered_time = current_time
        asyncio.run_coroutine_threadsafe(self.trigger_order_pipeline(), loop)
        print(f"🔥 [워처 감지] {self.filename} 파일 변경됨. 주문 파싱 시퀀스를 가동합니다.")

    async def trigger_order_pipeline(self):
        """엔진을 돌려 새로운 주문을 정산하고, 결과를 Socket.IO로 브로드캐스트합니다."""
        execution_logs = engine.parse_and_execute_orders()
        if not execution_logs:
            return

        for log in execution_logs:
            await emit_system_log(log)

            if "🛑 [BIG GAME] 빅게임 종료" in log:
                global is_biggame_running
                is_biggame_running = False
                await sio.emit('STATUS_UPDATE', {'status': 'STOPPED'})

        await emit_scoreboard()


def get_team_id_from_sid(sid):
    for k, v in userlist.items():
        if v == sid:
            return k
    return None


if __name__ == '__main__':
    import uvicorn
    print("🚀 FastAPI + Socket.IO 마스터 서버 가동... 포트: 3003")
    uvicorn.run(asgi_app, host="0.0.0.0", port=3003)
