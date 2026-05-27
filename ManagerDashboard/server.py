import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import HTTPException
import asyncio
import os

from starlette.responses import FileResponse
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from pydantic import BaseModel

from game_engine import BPGameEngine

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
    global loop
    if loop:
        # 비동기 루프에 소켓 발송(emit) 태스크를 안전하게 등록
        asyncio.run_coroutine_threadsafe(
            sio.emit('SYSTEM_LOG', {'message': message}),
            loop
        )
engine = BPGameEngine(log_callback=send_socket_log_to_dashboard)
@app.on_event("startup")
async def startup_event():
    global loop
    loop = asyncio.get_event_loop()

    watch_dir = os.path.abspath("../V2/data")
    target_file = "BP_TradeOrder.csv"
    os.makedirs(watch_dir, exist_ok=True)

    handler = OrderFileWatcherHandler(target_file)
    observer = Observer()
    observer.schedule(handler, path=watch_dir, recursive=False)
    observer.start()

    app.state.file_observer = observer
    print(f"📢 [시스템 백그라운드] {target_file} 파일 감시 워처 가동 완료. (대기 상태)")

@app.on_event("shutdown")
def shutdown_event():
    if hasattr(app.state, "file_observer"):
        app.state.file_observer.stop()
        app.state.file_observer.join()
        print("📢 파일 워처 자원 반환 및 안전 종료 완료.")

@app.get("/")
async def root():
    template_path = "./index.html"
    return FileResponse(template_path)


class OrderForm(BaseModel):
    secret_key: str
    trade_type: str
    target_id: str
    quantity: int


@app.post("/check_order")
async def place_order(order: OrderForm):
    # 💡 [핵심] 기존에 짜둔 engine.py의 검사 함수를 여기서 그대로 호출!
    # 예시: check_order_validity(team_id, stock_id, volume) -> (True/False, "사유")
    is_valid, reason = engine.check_order_validity(order.secret_key, order.trade_type, order.target_id, order.quantity)
    if not is_biggame_running:
        raise HTTPException(status_code=400, detail="현재 빅게임 진행중이 아닙니다.")
    if not is_valid:
        # 올바르지 않은 주문이면 즉시 400 에러와 함께 사유를 리턴 (프론트엔드로 직행)
        raise HTTPException(status_code=400, detail=reason)
    return {
        "status": "SUCCESS",
        "message": "주문 검증 통과 및 정상 접수 완결"
    }

@sio.event
async def connect(sid, environ):
    print('⚡ 클라이언트 연결됨:', sid)
    current_scoreboard = engine.get_dashboard_data()
    await sio.emit('SCOREBOARD_REFRESH', {'data': current_scoreboard})

# 대시보드 이벤트 리스너
@sio.event
async def control_biggame(sid, data):
    global is_biggame_running
    action = data.get("action")  # 'start' 또는 'stop'

    if action == 'start':
        is_biggame_running = True
        await sio.emit('STATUS_UPDATE', {'status': 'RUNNING'})
        await sio.emit('SYSTEM_LOG', {'message': "📈 [ADMIN] 빅게임 주문 수집 파이프라인이 가동되었습니다."})
    else:
        is_biggame_running = False
        await sio.emit('STATUS_UPDATE', {'status': 'STOPPED'})
        await sio.emit('SYSTEM_LOG', {'message': "⏸️ [ADMIN] 빅게임 주문 수집이 일시정지되었습니다."})

@sio.event
async def process_minigame(sid, data):
    engine.process_minigame_reward(data['winners'], int(data['round']))
    await sio.emit('SYSTEM_LOG', {'message': "📈 [ADMIN] 미니게임 정산이 완료되었습니다."})
    current_scoreboard = engine.get_dashboard_data()
    await sio.emit('SCOREBOARD_REFRESH', {'data': current_scoreboard})


@sio.event
async def rollback_previous_round(sid, data):
    try:
        current_round = data.get("current_round", 1)
        round_to_restore = current_round - 1

        await sio.emit("SYSTEM_LOG", {
            "message": f"⏪ [롤백 시그널] 관리자({sid})가 {current_round}R에서 {round_to_restore}R 상태로 복구를 요청했습니다."
        })

        if round_to_restore < 0:
            await sio.emit("SYSTEM_LOG", {"message": "❌ [롤백 실패] 0라운드 이전의 과거 데이터는 존재하지 않습니다."})
            return

        is_success = engine.restore_backup(round_to_restore)

        if is_success:
            engine.round_num = round_to_restore
            await sio.emit("SCOREBOARD_REFRESH", {"data": engine.get_dashboard_data()})
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
    sabotage_list = engine.check_sabotage(data['winners'])
    if len(sabotage_list) == 0:
        return
    for sabotage in sabotage_list:
        team = engine.get_team_status(sabotage[0])
        holdings = engine.get_team_holdings(team['parent'])
        req = {
            "id": sabotage[0],
            "rank": sabotage[1],
            "parent_name": team['parent name'],
            "available_stock": holdings[f'stock{sabotage[0]}']
        }
        await sio.emit('sabotage', req, userlist[str(engine.ALL_TEAMS.index(sabotage[0]) + 1)])

@sio.event
async def request_scoreboard_refresh(sid, data):
    engine.load_data()
    current_scoreboard = engine.get_dashboard_data()
    await sio.emit('SCOREBOARD_REFRESH', {'data': current_scoreboard})

# 📄 server.py 에 추가할 수동 정정 소켓 이벤트 핸들러 명세

@sio.event
async def manual_team_data_adjustment(sid, data):
    """
    관리자가 프론트엔드 테이블 셀을 클릭해 자산이나 주가를 수동 강제 수정한 경우 처리
    data 예시: {"team_id": "A", "field": "capital", "value": 3000000}
    """
    team_id = data.get("team_id", "").upper()
    field = data.get("field")  # 'capital' 또는 'price' 가 매핑되어 넘어옵니다.
    new_value = data.get("value")

    if not team_id or not field or new_value is None:
        return

    try:
        # 1. engine.py 내부의 판다스 데이터프레임 직접 접근 후 정정 타겟 인덱스 덮어쓰기
        if team_id in engine.teams_df.index:
            # 주가나 자산 컬럼명에 매칭 (CSV 파일 내 컬럼명이 대문자나 공백이 있다면
            # 그에 맞춰 engine 내부 데이터 구조 컬럼 룰에 맞게 포워딩됩니다)
            engine.teams_df.at[team_id, field] = int(new_value)
            engine.save_to_disk()
            # 2. 콘솔 메시지 백엔드 내부 및 대시보드 로거로 브로드캐스트
            log_msg = f"⚙️ [ADMIN HARD MOD] {team_id}팀의 {field} 수치가 관리자에 의해 {new_value:,}원으로 수동 갱신되었습니다."
            print(log_msg)
            await sio.emit('SYSTEM_LOG', {'message': log_msg})

            # 3. 변경 사항이 전산실과 메인 전광판 화면에 즉각 전파되도록 Refresh 신호 전파
            await sio.emit('SCOREBOARD_REFRESH', {'data': engine.get_dashboard_data()})

    except Exception as e:
        error_msg = f"❌ [수동 조정 에러] {team_id} 데이터 정정 연산 실패: {e}"
        print(error_msg)
        await sio.emit('SYSTEM_LOG', {'message': error_msg})

# @sio.event
# async def reset_orders(sid, data):
#     """대시보드에서 주문 내역 리셋 버튼을 눌렀을 때 감지"""
#     engine.last_order_idx = 0
#     engine.no_no_my_stock = {team: 0 for team in engine.ALL_TEAMS}
#     await sio.emit('SYSTEM_LOG', {'message': "🔄 [RESET] 누적 주문 인덱스가 0으로 초기화되었습니다."})


# 클라이언트 이벤트 리스너
@sio.event
async def user_join(sid, data):
    userlist[data['id']] = sid
    print(userlist)

@sio.event
async def send_force_trade_request(sid, data):
    team = engine.get_team_status(data['id'])
    holdings = engine.get_team_holdings(team['parent'])
    req = {
        'round_num': engine.round_num,
        'parentName': team['parent name'],
        'maxStock': holdings[f'stock{data['id']}'],
        'price': team['price'] * (engine.round_num if engine.round_num >= 2 else 2) / 2,
        'capital': team['capital']
    }
    await sio.emit('check_force_trade', req, room=userlist[str(engine.ALL_TEAMS.index(data['id']) + 1)])

@sio.event
async def force_trade_response(sid, data):
    result = bool(data['result'])
    if not result:
        await sio.emit('SYSTEM_LOG', {'message': f"[ADMIN] {engine.ALL_TEAMS[int(data['id']) - 1]}팀의 강매가 취소되었습니다."})
    else:
        engine.execute_forced_trade(engine.ALL_TEAMS[int(data['id']) - 1], int(data['amount']))
        current_scoreboard = engine.get_dashboard_data()
        await sio.emit('SCOREBOARD_REFRESH', {'data': current_scoreboard})


@sio.event
async def process_sabotage(sid, data):
    result = bool(data['result'])
    if not result:
        return
    rank = data['rank']
    id = data['id']
    engine.execute_sabotage(id, rank)
    current_scoreboard = engine.get_dashboard_data()
    await sio.emit('SCOREBOARD_REFRESH', {'data': current_scoreboard})


@sio.event
async def disconnect(sid):
    print('❌ 클라이언트 연결 해제:', sid)
    if get_team_id_from_sid(sid) is not None:
        userlist.pop(get_team_id_from_sid(sid))


class OrderFileWatcherHandler(FileSystemEventHandler):
    def __init__(self, filename: str):
        self.filename = filename
        self.last_triggered_time = 0  # 중복 이벤트 방어용 디바운스 타임스탬프

    def on_modified(self, event):

        # 빅게임 수집 활성화 상태이고, 대상 CSV 파일이 변경되었을 때만 트리거
        global is_biggame_running, loop
        if is_biggame_running and not event.is_directory and os.path.basename(event.src_path) == self.filename:

            # OS가 파일을 저장할 때 순간적으로 수정을 2~3번 연속 유발하는 'Double Trigger' 버그 방어 (0.5초 디바운스)
            if loop:
                current_time = loop.time()
                if current_time - self.last_triggered_time < 0.5:
                    return
                self.last_triggered_time = current_time

                # 안전하게 메인 비동기 스레드로 파이프라인 태스크를 던집니다.
                asyncio.run_coroutine_threadsafe(self.trigger_order_pipeline(), loop)

            print(f"🔥 [워처 감지] {self.filename} 파일 변경됨. 주문 파싱 시퀀스를 가동합니다.")

    async def trigger_order_pipeline(self):
        """엔진을 돌려 새로운 주문을 정산하고, 결과를 Socket.IO로 브로드캐스트합니다."""
        # 1. 엔진에 파싱 명령 전달 및 발생한 로그 리스트 수집
        execution_logs = engine.parse_and_execute_orders()

        if not execution_logs:
            return

        # 2. 대시보드로 실시간 로그 콘솔 텍스트 발송
        for log in execution_logs:
            await sio.emit('SYSTEM_LOG', {'message': log})
            await sio.emit('')

            # 만약 빅게임 종료 코드가 감지되었다면 수집 플래그 종료
            if "🛑 [BIG GAME] 빅게임 종료" in log:
                global is_biggame_running
                is_biggame_running = False
                await sio.emit('STATUS_UPDATE', {'status': 'STOPPED'})

        # 3. 주문 정산으로 변동된 최신 스코어보드 자산 데이터를 전 대시보드/클라이언트에 일괄 송출
        current_scoreboard = engine.get_dashboard_data()
        await sio.emit('SCOREBOARD_REFRESH', {'data': current_scoreboard})


def get_team_id_from_sid(sid):
    for k, v in userlist.items():
        if v == sid:
            return k
        else:
            return None
    return None


if __name__ == '__main__':
    import uvicorn
    print("🚀 FastAPI + Socket.IO 마스터 서버 가동... 포트: 3003")
    uvicorn.run(asgi_app, host="0.0.0.0", port=3003)