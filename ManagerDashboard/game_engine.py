from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pandas as pd


CSV_ENCODING = "utf-8-sig"
SYSTEM_TEAM_ID = "S"
ACTIVE_TEAM_IDS = ("A", "B", "C", "D", "E", "F", "G", "H")
SUBSIDIARY_CONTROL_THRESHOLD = 51
END_GAME_QUANTITY = 20061226


@dataclass(frozen=True)
class TradeOrder:
    secret_key: str
    trade_type_label: str
    target_team_name: str
    quantity: int
    row_index: Optional[int] = None


@dataclass(frozen=True)
class ResolvedTradeOrder:
    buyer_team_name: str
    buyer_team_id: str
    trade_action: str
    target_team_name: str
    target_team_id: str
    quantity: int
    row_index: Optional[int] = None


@dataclass(frozen=True)
class TradeValidationResult:
    is_valid: bool
    message: str
    order: Optional[ResolvedTradeOrder] = None
    is_end_game_signal: bool = False


class BPGameEngine:
    """Main settlement engine for S-Future-Conference manager operations."""

    SECRET_KEY_TO_TEAM_NAME = {
        "1588": "OpenAI",
        "2424": "Tesla",
        "3693": "삼성전자",
        "4885": "Palantir",
        "5959": "Instagram",
        "6256": "Amazon",
        "7749": "Google",
        "8881": "NVIDIA",
    }
    TEAM_NAME_TO_ID = {
        "OpenAI": "A",
        "Tesla": "B",
        "삼성전자": "C",
        "Palantir": "D",
        "Instagram": "E",
        "Amazon": "F",
        "Google": "G",
        "NVIDIA": "H",
    }
    TRADE_TYPE_TO_ACTION = {"매수": "Buy", "매도": "Sell"}
    MINIGAME_BASE_REWARDS = (200000, 150000, 100000)
    MINIGAME_PARTICIPATION_REWARD = 50000
    SUBSIDIARY_DIVIDEND_PER_TEAM = 200000
    SABOTAGE_STOCK_REWARDS = (10, 5, 3)

    def __init__(self, data_dir: str = "../V2/data", log_callback: Optional[Callable[[str], None]] = None):
        self.data_dir = Path(data_dir)
        self.round_num = 0
        self.last_order_idx = 0
        self.self_stock_purchase_counts = self._new_self_stock_purchase_counts()
        self.log_callback = log_callback

        self.teams_history: Dict[int, pd.DataFrame] = {}
        self.holdings_history: Dict[int, pd.DataFrame] = {}
        self.last_order_history: List[int] = []

        # Backward-compatible public attributes used by server.py and older scripts.
        self.SECRET_KEYS = self.SECRET_KEY_TO_TEAM_NAME
        self.TEAMS_MAP = self.TEAM_NAME_TO_ID
        self.BUY_SELL_MAP = self.TRADE_TYPE_TO_ACTION
        self.ALL_TEAMS = list(ACTIVE_TEAM_IDS)
        self.no_no_my_stock = self.self_stock_purchase_counts

        self.load_data()

    # ------------------------------------------------------------------
    # Logging and CSV persistence
    # ------------------------------------------------------------------
    def log(self, message: str) -> None:
        print(message)
        if self.log_callback:
            self.log_callback(message)

    def load_data(self) -> None:
        """Load shared CSV files into memory."""
        self.teams_df = pd.read_csv(self._csv_path("Teams.csv.csv"), index_col="Team", encoding=CSV_ENCODING)
        self.holdings_df = pd.read_csv(self._csv_path("Holdings.csv.csv"), index_col="Team", encoding=CSV_ENCODING)
        self.subsidiary_df = pd.read_csv(self._csv_path("Subsidiarys.csv.csv"), index_col="Team", encoding=CSV_ENCODING)
        self.teams_df["subsidiary"] = self.teams_df["subsidiary"].apply(self._parse_subsidiary_cell)

    def save_to_disk(self) -> None:
        """Persist the in-memory state back to the shared CSV files."""
        teams_to_save = self.teams_df.copy()
        teams_to_save["subsidiary"] = teams_to_save["subsidiary"].apply(self._serialize_subsidiary_cell)

        teams_to_save.to_csv(self._csv_path("Teams.csv.csv"), encoding=CSV_ENCODING)
        self.holdings_df.to_csv(self._csv_path("Holdings.csv.csv"), encoding=CSV_ENCODING)
        self.subsidiary_df.to_csv(self._csv_path("Subsidiarys.csv.csv"), encoding=CSV_ENCODING)

    def _csv_path(self, filename: str) -> Path:
        return self.data_dir / filename

    @staticmethod
    def _parse_subsidiary_cell(value: Any) -> List[str]:
        if pd.isna(value) or str(value).strip() in {"", "X", "[]", "nan"}:
            return []
        return [team_id.strip() for team_id in str(value).split(",") if team_id.strip()]

    @staticmethod
    def _serialize_subsidiary_cell(value: Any) -> str:
        if isinstance(value, list):
            return ",".join(value)
        return "" if pd.isna(value) else str(value)

    @staticmethod
    def _new_self_stock_purchase_counts() -> List[Dict[str, int]]:
        return [{team_id: 0 for team_id in ACTIVE_TEAM_IDS} for _ in range(2)]

    def _active_team_index(self, frame: pd.DataFrame) -> pd.Index:
        return frame.index.drop(SYSTEM_TEAM_ID, errors="ignore")

    # ------------------------------------------------------------------
    # Round snapshots and financial settlement
    # ------------------------------------------------------------------
    def create_backup(self) -> None:
        """Store the current round state for in-process rollback."""
        self.teams_history[self.round_num] = self.teams_df.copy()
        self.holdings_history[self.round_num] = self.holdings_df.copy()
        self.last_order_history.append(self.last_order_idx)

    def restore_backup(self, round_to_restore: int) -> bool:
        """Restore a previously archived round state."""
        if round_to_restore not in self.teams_history:
            self.log(f"❌ {round_to_restore} 라운드의 백업 데이터가 존재하지 않습니다.")
            return False

        self.teams_df = self.teams_history[round_to_restore].copy()
        self.holdings_df = self.holdings_history[round_to_restore].copy()
        self.last_order_idx = self.last_order_history[round_to_restore - 1]

        self.save_to_disk()
        self.log(f"🔄 {round_to_restore} 라운드 마감 시점으로 데이터 롤백 완료.")
        return True

    def update_financial_metrics(self) -> None:
        """Recalculate total assets and ranking from current cash, prices, and holdings."""
        team_ids = self._active_team_index(self.teams_df)
        stock_ids = self._active_team_index(self.holdings_df)

        for team_id in team_ids:
            stock_asset_sum = 0
            for stock_id in stock_ids:
                holding_amount = self._safe_number(self.holdings_df.at[team_id, f"stock{stock_id}"])
                stock_price = self._safe_number(self.teams_df.at[stock_id, "price"])
                stock_asset_sum += holding_amount * stock_price

            self.teams_df.at[team_id, "total asset"] = stock_asset_sum + self.teams_df.at[team_id, "capital"]

        self.teams_df["team rank"] = self.teams_df["total asset"].rank(method="min", ascending=False).astype(int)

    @staticmethod
    def _safe_number(value: Any) -> float:
        return 0 if pd.isna(value) else value

    def update_subsidiary_relationships(self) -> None:
        """Apply subsidiary acquisition and release rules from current holdings."""
        self._release_uncontrolled_subsidiaries()
        self._acquire_new_subsidiaries()

    def refresh_state_after_settlement(self) -> None:
        """Refresh ownership, financial metrics, and shared CSV files after a state change."""
        self.update_subsidiary_relationships()
        self.update_financial_metrics()
        self.save_to_disk()

    def _release_uncontrolled_subsidiaries(self) -> None:
        for child_id in self._active_team_index(self.teams_df):
            parent_id = self.teams_df.at[child_id, "parent"]
            if parent_id == "X":
                continue

            controlled_stock = self.holdings_df.at[parent_id, f"stock{child_id}"]
            if controlled_stock >= SUBSIDIARY_CONTROL_THRESHOLD:
                continue

            if child_id in self.teams_df.at[parent_id, "subsidiary"]:
                self.teams_df.at[parent_id, "subsidiary"].remove(child_id)

            self.log(f"🕊️ [자회사 해방] {self.teams_df.at[child_id, 'team name']}팀이 {parent_id}팀의 지배에서 벗어났습니다.")
            self.subsidiary_df.at[parent_id, "Subsidiary" + child_id] = " "
            self.teams_df.at[child_id, "parent"] = "X"
            self.teams_df.at[child_id, "parent name"] = " "

    def _acquire_new_subsidiaries(self) -> None:
        team_ids = self._active_team_index(self.holdings_df)
        for child_id in team_ids:
            if self.teams_df.at[child_id, "parent"] != "X":
                continue

            for parent_id in team_ids:
                if parent_id == child_id:
                    continue

                controlled_stock = self.holdings_df.at[parent_id, f"stock{child_id}"]
                if controlled_stock < SUBSIDIARY_CONTROL_THRESHOLD:
                    continue

                self.teams_df.at[child_id, "parent"] = parent_id
                self.teams_df.at[child_id, "parent name"] = self.teams_df.at[parent_id, "team name"]
                if child_id not in self.teams_df.at[parent_id, "subsidiary"]:
                    self.teams_df.at[parent_id, "subsidiary"].append(child_id)
                self.subsidiary_df.at[parent_id, "Subsidiary" + child_id] = "자회사"
                self.log(
                    f"👑 [자회사 편입] {self.teams_df.at[child_id, 'team name']}팀이 "
                    f"{self.teams_df.at[parent_id, 'team name']}팀의 계열사가 되었습니다."
                )
                break

    # ------------------------------------------------------------------
    # Mini-game, sabotage, and forced trade rules
    # ------------------------------------------------------------------
    def process_minigame_reward(self, winners_input: str, current_round: int) -> bool:
        """Settle rank rewards, participation rewards, and subsidiary dividends."""
        self.round_num = current_round
        winning_team_ids = self._parse_winning_team_ids(winners_input)
        if winning_team_ids is None:
            return False

        reward_multiplier = 1.3 ** (self.round_num - 1)
        self._grant_minigame_rank_rewards(winning_team_ids, reward_multiplier)
        self._grant_minigame_participation_rewards(winning_team_ids, reward_multiplier)
        self.update_subsidiary_relationships()
        self._grant_subsidiary_dividends()
        self.update_financial_metrics()
        self.save_to_disk()
        return True

    def find_sabotage_candidates(self, winners_input: str) -> List[tuple[str, int]]:
        """Return winning teams that can sabotage their parent company."""
        winning_team_ids = self._parse_winning_team_ids(winners_input)
        if winning_team_ids is None:
            return []

        return [
            (team_id, rank)
            for rank, team_id in enumerate(winning_team_ids)
            if self.teams_df.at[team_id, "parent"] != "X"
        ]

    def execute_sabotage(self, child_id: str, rank: int) -> bool:
        if child_id not in ACTIVE_TEAM_IDS or rank < 0 or rank >= len(self.SABOTAGE_STOCK_REWARDS):
            return False

        parent_id = self.teams_df.at[child_id, "parent"]
        if parent_id == "X":
            return False

        reward_quantity = self.SABOTAGE_STOCK_REWARDS[rank]
        cost = round((4 - rank) * 50000 * (1.3 ** (self.round_num - 1)), -2)

        self.teams_df.at[child_id, "capital"] -= cost
        self.holdings_df.at[child_id, f"stock{child_id}"] += reward_quantity
        self.holdings_df.at[parent_id, f"stock{child_id}"] -= reward_quantity

        self.refresh_state_after_settlement()
        self.log(f"[ADMIN] {child_id}팀의 사보타지가 완료되었습니다.")
        return True

    def execute_forced_trade(self, child_id: str, quantity: int) -> bool:
        """Force a parent company to sell the child's stock back to the child."""
        if quantity <= 0:
            return False

        parent_id = self.teams_df.at[child_id, "parent"]
        if parent_id == "X":
            return False

        total_cost = round(quantity * self.teams_df.at[child_id, "price"] * (self.round_num / 2))
        if self.teams_df.at[child_id, "capital"] < total_cost:
            return False
        if self.holdings_df.at[parent_id, f"stock{child_id}"] < quantity:
            return False

        self.teams_df.at[child_id, "capital"] -= total_cost
        self.teams_df.at[parent_id, "capital"] += total_cost
        self.holdings_df.at[child_id, f"stock{child_id}"] += quantity
        self.holdings_df.at[parent_id, f"stock{child_id}"] -= quantity

        self.refresh_state_after_settlement()
        self.log(f"[ADMIN] {child_id}팀의 강매가 완료되었습니다.")
        return True

    def _parse_winning_team_ids(self, winners_input: str) -> Optional[List[str]]:
        winning_team_ids = [team_id.strip() for team_id in winners_input.split(",")]
        if len(winning_team_ids) != 3 or not set(winning_team_ids).issubset(ACTIVE_TEAM_IDS):
            self.log("❌ 입력 형식이 잘못되었습니다. 정산을 취소합니다.")
            return None
        return winning_team_ids

    def _grant_minigame_rank_rewards(self, winning_team_ids: List[str], reward_multiplier: float) -> None:
        for team_id, base_reward in zip(winning_team_ids, self.MINIGAME_BASE_REWARDS):
            self.teams_df.at[team_id, "capital"] += round(base_reward * reward_multiplier, -2)

    def _grant_minigame_participation_rewards(self, winning_team_ids: List[str], reward_multiplier: float) -> None:
        for team_id in set(ACTIVE_TEAM_IDS) - set(winning_team_ids):
            self.teams_df.at[team_id, "capital"] += round(self.MINIGAME_PARTICIPATION_REWARD * reward_multiplier, -2)

    def _grant_subsidiary_dividends(self) -> None:
        for team_id in self._active_team_index(self.teams_df):
            subsidiary_count = len(self.teams_df.at[team_id, "subsidiary"])
            if subsidiary_count == 0:
                continue

            dividend = self.SUBSIDIARY_DIVIDEND_PER_TEAM * subsidiary_count
            self.teams_df.at[team_id, "capital"] += dividend
            self.log(f"💰 [배당금] {self.teams_df.at[team_id, 'team name']}팀에게 자회사 보너스 {dividend:,}원이 지급되었습니다.")

    # ------------------------------------------------------------------
    # Big-game trade order parsing, validation, and execution
    # ------------------------------------------------------------------
    def parse_and_execute_orders(self) -> List[str]:
        """Process new rows from BP_TradeOrder.csv after last_order_idx."""
        logs: List[str] = []
        trade_order_df = self._load_trade_order_csv()
        if trade_order_df is None or trade_order_df.empty:
            return logs

        while self.last_order_idx < len(trade_order_df):
            row_index = self.last_order_idx
            order_result = self._trade_order_from_csv_row(trade_order_df.iloc[row_index], row_index)
            self.last_order_idx += 1

            if isinstance(order_result, str):
                logs.append(order_result)
                continue

            validation = self.validate_trade_order(order_result)
            if not validation.is_valid:
                logs.append(validation.message)
                continue

            if validation.is_end_game_signal:
                logs.append("🛑 [BIG GAME] 빅게임 종료 코드가 수신되었습니다.")
                self._finalize_big_game_round()
                break

            logs.append(self._execute_trade_order(validation.order))
            self.refresh_state_after_settlement()

        return logs

    def validate_trade_order(self, order: TradeOrder) -> TradeValidationResult:
        """Validate and resolve a raw order without mutating game state."""
        if order.quantity <= 0:
            return TradeValidationResult(False, f"⚠️ [주문 패스] 수량이 0 이하입니다. (수량: {order.quantity})")

        buyer_team_name = self.SECRET_KEY_TO_TEAM_NAME.get(str(order.secret_key), "X")
        if buyer_team_name == "X":
            return TradeValidationResult(False, f"❌ [인증 실패] 올바르지 않은 보안키 입력 인입됨. (입력: {order.secret_key})")

        buyer_team_id = self.TEAM_NAME_TO_ID.get(buyer_team_name, "X")
        target_team_id = self.TEAM_NAME_TO_ID.get(order.target_team_name, "X")
        trade_action = self.TRADE_TYPE_TO_ACTION.get(order.trade_type_label, "X")
        if buyer_team_id == "X" or target_team_id == "X" or trade_action == "X":
            return TradeValidationResult(False, "❌ [매핑 실패] 팀명 또는 매매 타입 매핑 오류.")

        resolved_order = ResolvedTradeOrder(
            buyer_team_name=buyer_team_name,
            buyer_team_id=buyer_team_id,
            trade_action=trade_action,
            target_team_name=order.target_team_name,
            target_team_id=target_team_id,
            quantity=order.quantity,
            row_index=order.row_index,
        )
        if self._is_big_game_end_signal(resolved_order):
            return TradeValidationResult(True, "success", resolved_order, is_end_game_signal=True)

        if trade_action == "Buy":
            return self._validate_buy_order(resolved_order)
        return self._validate_sell_order(resolved_order)

    def check_order_validity(self, secret_key_raw: str, trade_type: str, target_id: str, quantity: int):
        """Compatibility wrapper for the HTTP order validation route."""
        validation = self.validate_trade_order(TradeOrder(str(secret_key_raw), trade_type, target_id, int(quantity)))
        return validation.is_valid, validation.message

    def _load_trade_order_csv(self) -> Optional[pd.DataFrame]:
        trade_order_path = self._csv_path("BP_TradeOrder.csv")
        if not trade_order_path.exists():
            return None
        return pd.read_csv(trade_order_path, encoding=CSV_ENCODING)

    def _trade_order_from_csv_row(self, order_row: pd.Series, row_index: int) -> TradeOrder | str:
        if order_row.iloc[1:].isnull().any():
            return f"⚠️ [주문 패스] 빈 주문이 감지되어 건너뜁니다. (인덱스: {row_index})"

        try:
            quantity = int(float(order_row.iloc[4]))
        except (ValueError, TypeError):
            return f"⚠️ [주문 패스] 수량 오류로 건너뜁니다. (값: {order_row.iloc[4]})"

        return TradeOrder(
            secret_key=str(order_row.iloc[1]),
            trade_type_label=order_row.iloc[2],
            target_team_name=order_row.iloc[3],
            quantity=quantity,
            row_index=row_index,
        )

    def _validate_buy_order(self, order: ResolvedTradeOrder) -> TradeValidationResult:
        if self._violates_self_stock_limit(order):
            return TradeValidationResult(
                False,
                f"🚫 [매수 제한] 1,2R 자사주 10주 이상 보유 금지 규칙 위반 ({order.buyer_team_name})",
            )

        required_cash = order.quantity * self.teams_df.loc[order.target_team_id, "price"]
        if self.teams_df.loc[order.buyer_team_id, "capital"] < required_cash:
            return TradeValidationResult(False, f"❌ [잔고 부족] {order.buyer_team_name}팀 잔고 부족으로 매수 실패.")

        if self.holdings_df.loc[SYSTEM_TEAM_ID, f"stock{order.target_team_id}"] < order.quantity:
            return TradeValidationResult(False, f"❌ [매물 부족] 시스템(S)의 {order.target_team_name} 주식이 부족합니다.")

        return TradeValidationResult(True, "success", order)

    def _validate_sell_order(self, order: ResolvedTradeOrder) -> TradeValidationResult:
        if self.holdings_df.loc[order.buyer_team_id, f"stock{order.target_team_id}"] < order.quantity:
            return TradeValidationResult(False, f"❌ [매도 실패] {order.buyer_team_name}팀이 보유한 {order.target_team_name} 주식이 부족합니다.")
        return TradeValidationResult(True, "success", order)

    def _execute_trade_order(self, order: ResolvedTradeOrder) -> str:
        if order.trade_action == "Buy":
            return self._execute_buy_order(order)
        return self._execute_sell_order(order)

    def _execute_buy_order(self, order: ResolvedTradeOrder) -> str:
        trade_amount = order.quantity * self.teams_df.loc[order.target_team_id, "price"]
        if self._is_round_one_or_two_self_stock_trade(order):
            self.self_stock_purchase_counts[self.round_num - 1][order.buyer_team_id] += order.quantity

        self.teams_df.loc[order.buyer_team_id, "capital"] -= trade_amount
        self.holdings_df.loc[order.buyer_team_id, f"stock{order.target_team_id}"] += order.quantity
        self.holdings_df.loc[SYSTEM_TEAM_ID, f"stock{order.target_team_id}"] -= order.quantity
        return f"🟩 [매수 체결] {order.buyer_team_name}팀 -> {order.target_team_name} {order.quantity}주 매수 완료."

    def _execute_sell_order(self, order: ResolvedTradeOrder) -> str:
        trade_amount = order.quantity * self.teams_df.loc[order.target_team_id, "price"]
        if self._is_round_one_or_two_self_stock_trade(order):
            self.self_stock_purchase_counts[self.round_num - 1][order.buyer_team_id] -= order.quantity

        self.teams_df.loc[order.buyer_team_id, "capital"] += trade_amount
        self.holdings_df.loc[order.buyer_team_id, f"stock{order.target_team_id}"] -= order.quantity
        self.holdings_df.loc[SYSTEM_TEAM_ID, f"stock{order.target_team_id}"] += order.quantity
        return f"🟥 [매도 체결] {order.buyer_team_name}팀 -> {order.target_team_name} {order.quantity}주 매도 완료."

    def _finalize_big_game_round(self) -> None:
        self.teams_df["price before"] = self.teams_df["price"]
        self.teams_df["price"] = self.teams_df["price"] + (self.teams_df["capital"] / 100).astype(int)
        self.teams_df["market capital"] = self.teams_df["price"] * 100

        if self.round_num != 3:
            self.teams_df["price delta"] = self.teams_df["price"] - self.teams_df["price before"]
            self.teams_df["price ROR"] = 0.0
            valid_previous_price = self.teams_df["price before"] != 0
            self.teams_df.loc[valid_previous_price, "price ROR"] = round(
                self.teams_df.loc[valid_previous_price, "price delta"]
                / self.teams_df.loc[valid_previous_price, "price before"]
                * 100,
                1,
            )

        self.update_financial_metrics()
        self.save_to_disk()
        self.create_backup()

    @staticmethod
    def _is_big_game_end_signal(order: ResolvedTradeOrder) -> bool:
        return (
            order.buyer_team_id == "A"
            and order.trade_action == "Buy"
            and order.target_team_id == "A"
            and order.quantity == END_GAME_QUANTITY
        )

    def _violates_self_stock_limit(self, order: ResolvedTradeOrder) -> bool:
        if not self._is_round_one_or_two_self_stock_trade(order):
            return False
        current_count = self.self_stock_purchase_counts[self.round_num - 1][order.buyer_team_id]
        return current_count + order.quantity >= 10

    def _is_round_one_or_two_self_stock_trade(self, order: ResolvedTradeOrder) -> bool:
        return self.round_num in (1, 2) and order.buyer_team_id == order.target_team_id

    # ------------------------------------------------------------------
    # Dashboard query helpers
    # ------------------------------------------------------------------
    def get_dashboard_data(self) -> List[Dict[str, Any]]:
        """Return team rows in Socket.IO dashboard packet format."""
        dashboard_rows = self.teams_df.copy().reset_index().to_dict(orient="records")
        return [row for row in dashboard_rows if row["Team"] != SYSTEM_TEAM_ID]

    def get_team_status(self, team_id: str) -> Optional[Dict[str, Any]]:
        """Return one team's financial status for participant-specific packets."""
        normalized_team_id = team_id.upper()
        if normalized_team_id not in self.teams_df.index:
            self.log(f"⚠️ [조회 실패] 존재하지 않는 팀 ID입니다: {normalized_team_id}")
            return None

        team_data = self.teams_df.loc[normalized_team_id].to_dict()
        team_data["team_id"] = normalized_team_id
        return team_data

    def get_team_holdings(self, team_id: str) -> Optional[Dict[str, int]]:
        """Return one team's stock holdings."""
        normalized_team_id = team_id.upper()
        if normalized_team_id not in self.holdings_df.index:
            return None
        return self.holdings_df.loc[normalized_team_id].to_dict()

    def get_single_team_dashboard_packet(self, team_id: str) -> Optional[Dict[str, Any]]:
        """Return financial status and holdings in one participant packet."""
        status = self.get_team_status(team_id)
        holdings = self.get_team_holdings(team_id)
        if not status or not holdings:
            return None
        return {**status, "holdings": holdings}

    # ------------------------------------------------------------------
    # Backward-compatible method aliases
    # ------------------------------------------------------------------
    def check_and_update_subsidiaries(self) -> None:
        self.update_subsidiary_relationships()

    def check_and_update_subsidaries_and_metrics(self) -> None:
        self.refresh_state_after_settlement()

    def check_sabotage(self, winners_input: str) -> List[tuple[str, int]]:
        return self.find_sabotage_candidates(winners_input)
