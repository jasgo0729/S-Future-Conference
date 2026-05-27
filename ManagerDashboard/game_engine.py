import pandas as pd
import numpy as np
import os
from typing import List, Dict, Any, Optional


class BPGameEngine:
    def __init__(self, data_dir: str = "../V2/data", log_callback=None):
        self.data_dir = data_dir
        self.round_num = 0
        self.last_order_idx = 0  # 기존 주피터의 LastOrder 변수 역할
        self.no_no_my_stock = [{team: 0 for team in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']} for _ in range(2)]
        self.log_callback = log_callback

        # 백업용 데이터 구조
        self.teams_history: Dict[int, pd.DataFrame] = {}
        self.holdings_history: Dict[int, pd.DataFrame] = {}
        self.last_order_history: List[int] = []

        # 시스템 내부 매핑 데이터 상수 [주피터 노트북 로직 기반]
        self.SECRET_KEYS = {
            "1588": "OpenAI", "2424": "Tesla", "3693": "삼성전자", "4885": "Palantir",
            "5959": "Instagram", "6256": "Amazon", "7749": "Google", "8881": "NVIDIA"
        }
        self.TEAMS_MAP = {
            "OpenAI": "A", "Tesla": "B", "삼성전자": "C", "Palantir": "D",
            "Instagram": "E", "Amazon": "F", "Google": "G", "NVIDIA": "H"
        }
        self.BUY_SELL_MAP = {"매수": "Buy", "매도": "Sell"}
        self.ALL_TEAMS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']

        self.load_data()

    def log(self, message: str):
        print(message)

        if self.log_callback:
            self.log_callback(message)

    def load_data(self):
        """CSV 파일들로부터 핵심 데이터를 메모리에 로드합니다."""
        self.teams_df = pd.read_csv(f"{self.data_dir}/Teams.csv.csv", index_col='Team', encoding='utf-8-sig')
        self.holdings_df = pd.read_csv(f"{self.data_dir}/Holdings.csv.csv", index_col='Team', encoding='utf-8-sig')
        self.subsidiary_df = pd.read_csv(f"{self.data_dir}/Subsidiarys.csv.csv", index_col='Team', encoding='utf-8-sig')

        # subsidiary 컬럼 초기화 및 안전한 리스트 객체화
        self.teams_df['subsidiary'] = self.teams_df['subsidiary'].apply(
            lambda x: [] if pd.isna(x) or str(x).strip() in ['', 'X', '[]', 'nan'] else str(x).split(',')
        )

    def save_to_disk(self):
        """현재 메모리의 상태를 CSV 파일로 저장합니다."""
        teams_copy = self.teams_df.copy()
        teams_copy['subsidiary'] = teams_copy['subsidiary'].apply(
            lambda x: ','.join(x) if isinstance(x, list) else str(x))

        teams_copy.to_csv(f"{self.data_dir}/Teams.csv.csv", encoding='utf-8-sig')
        self.holdings_df.to_csv(f"{self.data_dir}/Holdings.csv.csv", encoding='utf-8-sig')
        self.subsidiary_df.to_csv(f"{self.data_dir}/Subsidiarys.csv.csv", encoding='utf-8-sig')

    def create_backup(self):
        """현재 라운드의 데이터를 백업 아카이빙합니다."""
        self.teams_history[self.round_num] = self.teams_df.copy()
        self.holdings_history[self.round_num] = self.holdings_df.copy()
        self.last_order_history.append(self.last_order_idx)

    def restore_backup(self, round_to_restore: int) -> bool:
        """지정한 과거 라운드 시점으로 데이터를 완벽하게 롤백 복원합니다."""
        if round_to_restore not in self.teams_history:
            self.log(f"❌ {round_to_restore} 라운드의 백업 데이터가 존재하지 않습니다.")
            return False

        self.teams_df = self.teams_history[round_to_restore].copy()
        self.holdings_df = self.holdings_history[round_to_restore].copy()
        self.last_order_idx = self.last_order_history[round_to_restore - 1]

        self.save_to_disk()
        self.log(f"🔄 {round_to_restore} 라운드 마감 시점으로 데이터 롤백 완료.")
        return True

    def update_financial_metrics(self):
        """보유 주식 가치를 계산하여 총자산(Total Asset)과 순위를 일괄 갱신합니다."""
        for team_id in self.teams_df.drop(index=['S']).index:
            stock_asset_sum = 0
            for stock_id in self.holdings_df.drop(index=['S']).index:
                holding_amount = self.holdings_df.at[team_id, f'stock{stock_id}']
                stock_price = self.teams_df.at[stock_id, 'price']

                holding_amount = 0 if pd.isna(holding_amount) else holding_amount
                stock_price = 0 if pd.isna(stock_price) else stock_price
                stock_asset_sum += holding_amount * stock_price

            self.teams_df.at[team_id, 'total asset'] = stock_asset_sum + self.teams_df.at[team_id, 'capital']

        self.teams_df['team rank'] = self.teams_df['total asset'].rank(method='min', ascending=False).astype(int)

    def check_and_update_subsidiaries(self):
        """지분율을 검사하여 자회사 편입 및 해방 규칙을 일괄 연산합니다."""
        # 1. 자회사 해방 검사
        for child_id in self.teams_df.drop(index=['S']).index:
            parent_id = self.teams_df.at[child_id, 'parent']
            if parent_id != 'X':
                if self.holdings_df.at[parent_id, f'stock{child_id}'] < 51:
                    if child_id in self.teams_df.at[parent_id, 'subsidiary']:
                        self.teams_df.at[parent_id, 'subsidiary'].remove(child_id)
                    self.log(f"🕊️ [자회사 해방] {self.teams_df.at[child_id, 'team name']}팀이 {parent_id}팀의 지배에서 벗어났습니다.")
                    self.subsidiary_df.at[self.teams_df.at[child_id, 'parent'], 'Subsidiary' + child_id] = ' '
                    self.teams_df.at[child_id, 'parent'] = 'X'
                    self.teams_df.at[child_id, 'parent name'] = ' '

        # 2. 새로운 자회사 편입 검사
        for child_id in self.holdings_df.drop(index=['S']).index:
            for parent_id in self.holdings_df.drop(index=['S']).index:
                if parent_id == child_id:
                    continue
                if self.holdings_df.at[parent_id, f'stock{child_id}'] >= 51 and self.teams_df.at[
                    child_id, 'parent'] == 'X':
                    if child_id not in self.teams_df.at[parent_id, 'subsidiary']:
                        self.teams_df.at[child_id, 'parent'] = parent_id
                        self.teams_df.at[child_id, 'parent name'] = self.teams_df.at[parent_id, 'team name']
                        self.teams_df.at[parent_id, 'subsidiary'].append(child_id)
                        self.subsidiary_df.at[parent_id, 'Subsidiary' + child_id] = '자회사'
                        self.log(
                            f"👑 [자회사 편입] {self.teams_df.at[child_id, 'team name']}팀이 {self.teams_df.at[parent_id, 'team name']}팀의 계열사가 되었습니다.")

    def process_minigame_reward(self, winners_input: str, current_round: int) -> bool:
        """미니게임 순위를 반영하여 라운드 기본금 및 자회사 배당 보너스를 정산합니다."""
        self.round_num = current_round
        win_list = [w.strip() for w in winners_input.split(',')]

        if len(win_list) != 3 or not set(win_list).issubset(set(self.ALL_TEAMS)):
            self.log("❌ 입력 형식이 잘못되었습니다. 정산을 취소합니다.")
            return False

        rest_teams = list(set(self.ALL_TEAMS) - set(win_list))
        bonus_multiplier = (1.3) ** (self.round_num - 1)

        self.teams_df.at[win_list[0], 'capital'] += round(200000 * bonus_multiplier, -2)
        self.teams_df.at[win_list[1], 'capital'] += round(150000 * bonus_multiplier, -2)
        self.teams_df.at[win_list[2], 'capital'] += round(100000 * bonus_multiplier, -2)
        for t in rest_teams:
            self.teams_df.at[t, 'capital'] += round(50000 * bonus_multiplier, -2)

        self.check_and_update_subsidiaries()

        for team_id in self.teams_df.drop(index=['S']).index:
            subs_count = len(self.teams_df.at[team_id, 'subsidiary'])
            if subs_count > 0:
                dividend = 200000 * subs_count
                self.teams_df.at[team_id, 'capital'] += dividend
                self.log(f"💰 [배당금] {self.teams_df.at[team_id, 'team name']}팀에게 자회사 보너스 {dividend:,}원이 지급되었습니다.")

        self.update_financial_metrics()
        self.save_to_disk()
        return True

    def check_sabotage(self, winners_input: str):
        result = []
        win_list = [w.strip() for w in winners_input.split(',')]

        if len(win_list) != 3 or not set(win_list).issubset(set(self.ALL_TEAMS)):
            self.log("❌ 입력 형식이 잘못되었습니다. 정산을 취소합니다.")
            return False

        for i in range(3):
            if self.teams_df.at[win_list[i], 'parent'] == 'X':
                continue
            result.append((win_list[i], i))
        return result

    def execute_sabotage(self, child_id: str, rank: int) -> bool:
        parent_id = self.teams_df.at[child_id, 'parent']

        bonus_multiplier = (1.3) ** (self.round_num - 1)
        cost = round((4 - rank) * 50000 * bonus_multiplier, -2)

        quantity = 0
        if rank == 0:
            quantity = 10
        elif rank == 1:
            quantity = 5
        elif rank == 2:
            quantity = 3
        self.teams_df.at[child_id, 'capital'] -= cost
        self.holdings_df.at[child_id, f'stock{child_id}'] += quantity
        self.holdings_df.at[parent_id, f'stock{child_id}'] -= quantity

        self.check_and_update_subsidiaries()
        self.update_financial_metrics()
        self.save_to_disk()
        self.log(f"[ADMIN] {child_id}팀의 사보타지가 완료되었습니다.")
        return True

    def execute_forced_trade(self, child_id: str, quantity: int) -> bool:
        """모회사의 자사주 물량을 자회사에게 강제 매각 처리합니다."""
        parent_id = self.teams_df.at[child_id, 'parent']
        if parent_id == 'X':
            return False

        total_cost = round(quantity * self.teams_df.at[child_id, 'price'] * (self.round_num / 2))

        if self.teams_df.at[child_id, 'capital'] < total_cost or self.holdings_df.at[
            parent_id, f'stock{child_id}'] < quantity:
            return False

        self.teams_df.at[child_id, 'capital'] -= total_cost
        self.teams_df.at[parent_id, 'capital'] += total_cost
        self.holdings_df.at[child_id, f'stock{child_id}'] += quantity
        self.holdings_df.at[parent_id, f'stock{child_id}'] -= quantity

        self.check_and_update_subsidiaries()
        self.update_financial_metrics()
        self.save_to_disk()
        self.log(f"[ADMIN] {child_id}팀의 강매가 완료되었습니다.")
        return True

    # =========================================================================
    # 📈 [신규 통합] 빅게임 실시간 주문 파싱 연산 전용 메서드 (ImportTradeOrder 완전 대체)
    # =========================================================================
    def parse_and_execute_orders(self) -> List[str]:
        """
        주문 CSV 파일을 읽어 들여 아직 처리하지 않은 새로운 주문(LastOrder 이후)을
        순차적으로 파싱하고 금융 연산을 수행합니다.
        처리된 로그 메시지 리스트를 반환하여 웹소켓 콘솔로 쏠 수 있게 합니다.
        """
        logs = []
        csv_path = f"{self.data_dir}/BP_TradeOrder.csv"

        if not os.path.exists(csv_path):
            return logs

        trade_order_df = pd.read_csv(csv_path)
        if trade_order_df.empty:
            return logs

        # 처리할 새로운 주문이 있는지 인덱스 검사
        while trade_order_df.index[-1] >= self.last_order_idx:
            order_series = trade_order_df.iloc[self.last_order_idx]
            self.last_order_idx += 1  # 처리 인덱스 1 증가

            # 결측치 예외 처리
            if order_series[1:].isnull().any():
                logs.append(f"⚠️ [주문 패스] 빈 주문이 감지되어 건너뜁니다. (인덱스: {self.last_order_idx - 1})")
                continue

            order_list = order_series.tolist()
            order_list.pop(0)  # 첫 번째 요소(인덱스) 제거

            # 수량 정수 변환 및 예외 검증
            try:
                quantity = int(float(order_list[3]))
            except (ValueError, TypeError):
                logs.append(f"⚠️ [주문 패스] 수량 오류로 건너뜁니다. (값: {order_list[3]})")
                continue

            if quantity <= 0:
                logs.append(f"⚠️ [주문 패스] 수량이 0 이하입니다. (수량: {quantity})")
                continue

            # 🔐 보안키 및 매핑 검증 단계
            secret_key_raw = str(order_list[0])
            buyer_team_name = self.SECRET_KEYS.get(secret_key_raw, 'X')

            if buyer_team_name == 'X':
                logs.append(f"❌ [인증 실패] 올바르지 않은 보안키 입력 인입됨. (입력: {secret_key_raw})")
                continue

            # 빅게임 마감 종료 코드 감지 (A, Buy, A, 20061226)
            if buyer_team_name == "OpenAI" and order_list[1] == "매수" and order_list[
                2] == "OpenAI" and quantity == 20061226:
                logs.append("🛑 [BIG GAME] 빅게임 종료 코드가 수신되었습니다.")

                # 라운드 최종 주가 변동 공식 대입 (빅게임 마감 정산)
                self.teams_df['price before'] = self.teams_df['price']
                self.teams_df['price'] = self.teams_df['price'] + (self.teams_df['capital'] / 100).astype(int)
                self.teams_df['market capital'] = self.teams_df['price'] * 100

                if self.round_num != 3:
                    self.teams_df['price delta'] = self.teams_df['price'] - self.teams_df['price before']
                    self.teams_df['price ROR'] = 0.0
                    mask = self.teams_df['price before'] != 0
                    self.teams_df.loc[mask, 'price ROR'] = round(
                        (self.teams_df.loc[mask, 'price delta'] / self.teams_df.loc[mask, 'price before'] * 100), 1
                    )
                self.update_financial_metrics()
                self.save_to_disk()
                self.create_backup()
                break

            # 영문 식별자 ID 매핑
            buyer_id = self.TEAMS_MAP.get(buyer_team_name, 'X')
            target_id = self.TEAMS_MAP.get(order_list[2], 'X')
            trade_type = self.BUY_SELL_MAP.get(order_list[1], 'X')

            if buyer_id == 'X' or target_id == 'X' or trade_type == 'X':
                logs.append("❌ [매핑 실패] 팀명 또는 매매 타입 매핑 오류로 주문을 건너뜁니다.")
                continue

            # 🛒 매수(Buy) 연산 프로세스
            if trade_type == 'Buy':
                # 1,2라운드 자사주 10주 이상 구매 제한 룰 검증
                if (self.round_num == 1 or self.round_num == 2) and buyer_id == target_id:
                    if self.no_no_my_stock[self.round_num - 1][buyer_id] + quantity >= 10:
                        logs.append(f"🚫 [매수 제한] 1,2R 자사주 10주 이상 보유 금지 규칙 위반 ({buyer_team_name})")
                        continue

                required_cash = quantity * self.teams_df.loc[target_id, 'price']
                if self.teams_df.loc[buyer_id, 'capital'] < required_cash:
                    logs.append(f"❌ [잔고 부족] {buyer_team_name}팀 잔고 부족으로 매수 실패.")
                    continue

                if self.holdings_df.loc['S', f'stock{target_id}'] < quantity:
                    logs.append(f"❌ [매물 부족] 시스템(S)의 {order_list[2]} 주식이 부족합니다.")
                    continue

                # 자사주 카운트 누적 및 최종 차감 정산 실행
                if buyer_id == target_id and (self.round_num == 1 or self.round_num == 2):
                    self.no_no_my_stock[self.round_num - 1][buyer_id] += quantity

                self.teams_df.loc[buyer_id, 'capital'] -= required_cash
                self.holdings_df.loc[buyer_id, f'stock{target_id}'] += quantity
                self.holdings_df.loc['S', f'stock{target_id}'] -= quantity
                logs.append(f"🟩 [매수 체결] {buyer_team_name}팀 -> {order_list[2]} {quantity}주 매수 완료.")

            # 🏷️ 매도(Sell) 연산 프로세스
            elif trade_type == 'Sell':
                if self.holdings_df.loc[buyer_id, f'stock{target_id}'] < quantity:
                    logs.append(f"❌ [매도 실패] {buyer_team_name}팀이 보유한 {order_list[2]} 주식이 부족합니다.")
                    continue

                if buyer_id == target_id and (self.round_num == 1 or self.round_num == 2):
                    self.no_no_my_stock[self.round_num - 1][buyer_id] -= quantity

                gain_cash = quantity * self.teams_df.loc[target_id, 'price']
                self.teams_df.loc[buyer_id, 'capital'] += gain_cash
                self.holdings_df.loc[buyer_id, f'stock{target_id}'] -= quantity
                self.holdings_df.loc['S', f'stock{target_id}'] += quantity
                logs.append(f"🟥 [매도 체결] {buyer_team_name}팀 -> {order_list[2]} {quantity}주 매도 완료.")

            # 관계성 및 자산 총액 실시간 변동 리프레시
            self.check_and_update_subsidaries_and_metrics()

        return logs

    def check_order_validity(self, secret_key_raw: str, trade_type: str, target_id: str,  quantity: int):
        print(secret_key_raw, trade_type, target_id, quantity)
        buyer_team_name = self.SECRET_KEYS.get(secret_key_raw, 'X')
        target_id = self.TEAMS_MAP.get(target_id, 'X')
        trade_type = self.BUY_SELL_MAP.get(trade_type, 'X')

        if buyer_team_name == 'X':
            return False, f"❌ [인증 실패] 올바르지 않은 보안키 입력 인입됨. (입력: {secret_key_raw})"
        buyer_id = self.TEAMS_MAP.get(buyer_team_name, 'X')
        if buyer_id == 'X' or target_id == 'X' or trade_type == 'X':
            return False, "❌ [매핑 실패] 팀명 또는 매매 타입 매핑 오류."

        if trade_type == 'Buy':
            print(buyer_id, trade_type, target_id, quantity)
            if buyer_id == "A" and target_id == "A" and quantity == 20061226:
                return True, "success"
            # 1,2라운드 자사주 10주 이상 구매 제한 룰 검증
            if (self.round_num == 1 or self.round_num == 2) and buyer_id == target_id:
                if self.no_no_my_stock[self.round_num - 1][buyer_id] + quantity >= 10:
                    return False, f"🚫 [매수 제한] 1,2R 자사주 10주 이상 보유 금지 규칙 위반 ({buyer_team_name})"

            required_cash = quantity * self.teams_df.loc[target_id, 'price']
            if self.teams_df.loc[buyer_id, 'capital'] < required_cash:
                return False, f"❌ [잔고 부족] {buyer_team_name}팀 잔고 부족으로 매수 실패."

            if self.holdings_df.loc['S', f'stock{target_id}'] < quantity:
                return False, f"❌ [매물 부족] 시스템(S)의 주식이 부족합니다."
        elif trade_type == 'Sell':
            if self.holdings_df.loc[buyer_id, f'stock{target_id}'] < quantity:
                return False, f"❌ [매도 실패] {buyer_team_name}팀이 보유한 주식이 부족합니다."
        return True, "success"

    def check_and_update_subsidaries_and_metrics(self):
        """주문 체결 직후 자회사 여부와 재무 지표를 한 번에 갱신하고 스냅샷을 저장합니다."""
        self.check_and_update_subsidiaries()
        self.update_financial_metrics()
        self.save_to_disk()

    def get_dashboard_data(self) -> List[Dict[str, Any]]:
        """현재 팀 자산 상태를 프론트엔드 대시보드(Socket.IO)용 구조로 변환합니다."""
        df_copy = self.teams_df.copy().reset_index()
        return df_copy.to_dict(orient='records')[:len(df_copy.to_dict(orient='records')) - 1]

    # =========================================================================
    # 🔍 [신규 추가] 특정 팀의 데이터만 필터링하여 조회하는 인터페이스
    # =========================================================================
    def get_team_status(self, team_id: str) -> Optional[Dict[str, Any]]:
        """
        특정 팀의 자본금, 주가, 자회사 리스트 등 기본 재무 상태를 딕셔너리로 반환합니다.
        존재하지 않는 팀 ID일 경우 None을 반환합니다.
        """
        upper_team_id = team_id.upper()
        if upper_team_id not in self.teams_df.index:
            self.log(f"⚠️ [조회 실패] 존재하지 않는 팀 ID입니다: {upper_team_id}")
            return None

        # 해당 팀의 행(Row)만 추출하여 딕셔너리로 변환
        team_data = self.teams_df.loc[upper_team_id].to_dict()
        team_data['team_id'] = upper_team_id  # 딕셔너리 내부에 ID key도 포함시켜주면 프론트에서 쓰기 좋습니다.
        return team_data

    def get_team_holdings(self, team_id: str) -> Optional[Dict[str, int]]:
        """
        특정 팀이 보유한 타사 주식 현황(지분율)을 딕셔너리 형태로 반환합니다.
        예: {'stockA': 10, 'stockB': 55, ...}
        """
        upper_team_id = team_id.upper()
        if upper_team_id not in self.holdings_df.index:
            return None

        return self.holdings_df.loc[upper_team_id].to_dict()

    def get_single_team_dashboard_packet(self, team_id: str) -> Optional[Dict[str, Any]]:
        """
        재무 정보와 주식 보유 현황을 하나로 합쳐서 소켓 패킷 규격으로 만들어줍니다.
        """
        status = self.get_team_status(team_id)
        holdings = self.get_team_holdings(team_id)

        if not status or not holdings:
            return None

        # 두 딕셔ner리를 하나로 병합 (Merge)
        return {**status, "holdings": holdings}