const socket = io.connect('http://ec2-15-165-202-145.ap-northeast-2.compute.amazonaws.com:3003', {
    path: '/socket.io',
    transports: ['websocket']
});

socket.on('connect', (data) => {
    socket.emit('user_join', {id: localStorage.getItem("user_number")})
});

socket.on("check_force_trade", (data) => {
    forceTradeListener(data);
});

let currentTradeSession = {
    round: 0,
    parentName: "",
    maxStock: 0,
    price: 0,
    capital: 0
};

const forceTradeListener = (data) => {
    console.log(data);
    currentTradeSession.round = Number(data.round_num);
    currentTradeSession.parentName = String(data.parentName);
    currentTradeSession.maxStock = Number(data.maxStock);
    currentTradeSession.price = Number(data.price);
    currentTradeSession.capital = Number(data.capital);
    triggerStep1(currentTradeSession.parentName, currentTradeSession.maxStock);
}

function triggerStep1(parentName, maxStock) {
    document.getElementById('md1-parent-name').innerText = parentName;
    document.getElementById('md1-stock-qty').innerText = maxStock;
    document.getElementById('modal-step-1').classList.remove('hidden');
}

function handleReject() {
    alert("강매 거절 신호를 서버로 전송합니다 (X)");
    socket.emit("force_trade_response", {
        id: localStorage.getItem('user_number'),
        result: false
    });
    closeAllModals();
}

function goToStep2() {
    document.getElementById('modal-step-1').classList.add('hidden');
    
    document.querySelectorAll('#md2-parent-name').forEach(el => el.innerText = currentTradeSession.parentName + "팀");
    document.getElementById('md2-max-stock').innerText = currentTradeSession.maxStock + "주 보유";
    document.getElementById('trade-quantity').max = currentTradeSession.maxStock;
    document.getElementById('trade-quantity').value = '';
    document.getElementById('md2-stock-price').innerText = currentTradeSession.price + '₩';

    document.getElementById('modal-step-2').classList.remove('hidden');
}

function submitFinalTrade() {
    const qty = document.getElementById('trade-quantity').value;
    
    if (!qty || qty <= 0) {
        return alert("올바른 수량을 입력해 주세요.");
    }
    if (parseInt(qty) > currentTradeSession.maxStock) {
        return alert(`모회사가 보유한 최대 수량(${currentTradeSession.maxStock}주)을 초과할 수 없습니다.`);
    }

    if (parseInt(qty) * currentTradeSession.price > currentTradeSession.capital) {
        return alert(`자금을 초과하여 주문할 수 없습니다.`);
    }

    alert(`정상 처리 완료: ${currentTradeSession.parentName}팀 주식 ${qty}주 강매 체결 요청을 서버로 발송합니다.`);
    // ws.send(JSON.stringify({ "type": "FORCED_TRADE_RESPONSE", "action": "O", "qty": parseInt(qty) }));
    socket.emit("force_trade_response", {
        id: localStorage.getItem('user_number'),
        result: true,
        amount: parseInt(qty)
    })
    closeAllModals();
}

function closeAllModals() {
    document.getElementById('modal-step-1').classList.add('hidden');
    document.getElementById('modal-step-2').classList.add('hidden');
}

// 💡 클라이언트 스크립트 영역에 추가

/**
 * 📡 [소켓 수신] 백엔드 관리자가 미니게임 정산 후 사보타지 대상 팀에게 선택권을 넘겼을 때
 * data 예시: { parent_name: "OpenAI", available_stock: 40 }
 */
let id = '';
let rank = 0;
socket.on("sabotage", (data) => {
    document.getElementById('sabotage-parent-name').innerText = data.parent_name;
    document.getElementById('sabotage-available-stock').innerText = `${data.available_stock}주`;
    id = data.id;
    rank = data.rank;
    
    // 🥷 사보타지 선택 모달 활성화
    const modal = document.getElementById('client-sabotage-modal');
    modal.classList.remove('hidden');
});

/**
 * 팀원이 버튼을 클릭하여 최종 보상을 선택했을 때 실행
 * @param {boolean} isSabotageChosen - true면 사보타지 발동, false면 일반 상금 수령
 */
function selectSabotageReward(isSabotageChosen) {
    const modal = document.getElementById('client-sabotage-modal');
    
    if (isSabotageChosen) {
        const confirmAction = confirm("⚡ 정말로 이번 라운드 상금을 포기하고, 모기업으로부터 지분을 강제 회수하는 [사보타지]를 실행하시겠습니까?");
        if (!confirmAction) return;
        
        // 백엔드 서버로 사보타지 선택 완료 신호 송신 (딕셔너리 구조)
        socket.emit("process_sabotage", {
            result: true,
            id: id,
            rank: rank
        });
    } else {
        // 일반 상금 수령 선택
        socket.emit("process_sabotage", {
            result: false
        });
    }

    // 선택이 끝나면 모달 비활성화
    modal.classList.add('hidden');
}