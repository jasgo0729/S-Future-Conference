const express = require('express');
const path = require('path');
const fs = require('fs');
const XLSX = require('xlsx'); // 💡 SheetJS 라이브러리 로드
const app = express();
const PORT = 3005;

// 파이썬 메인 엔진의 Teams.csv.csv 실제 파일 경로
const CSV_PATH = path.join(__dirname, '../V2/data/Teams.csv.csv');

app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// 🎬 [고정 시나리오] 종목별 수익률 배당표
const STOCK_SCENARIO = {
    "A": 1.5, "B": 0.6, "C": 1.2, "D": 0.9,
    "E": 1.8, "F": 0.5, "G": 1.0, "H": 1.1
};

/**
 * 🛠️ [XLSX 버전] Teams.csv.csv 안전하게 로드하고 파싱하기
 */
function readTeamsCSV() {
    if (!fs.existsSync(CSV_PATH)) {
        console.error(`❌ 파일을 찾을 수 없습니다: ${CSV_PATH}`);
        return { headers: [], dataList: [] };
    }

    // 💡 xlsx 라이브러리로 파일 읽기 (인코딩 버그 완전 차단)
    const workbook = XLSX.readFile(CSV_PATH);
    const sheetName = workbook.SheetNames[0];
    const sheet = workbook.Sheets[sheetName];

    // 행-열 데이터가 그대로 담긴 2차원 배열로 추출 (예: [['Team', 'team name', 'capital'], ['A', 'OpenAI', '2500000']])
    const rawRows = XLSX.utils.sheet_to_json(sheet, { header: 1, defval: "" });
    
    if (rawRows.length === 0) return { headers: [], dataList: [] };

    const headers = rawRows[0];
    const dataList = rawRows.slice(1); // 헤더를 제외한 순수 팀 데이터 배열 목록

    return { headers, dataList };
}

/**
 * 🛠️ [XLSX 버전] 연산 끝난 데이터를 다시 기존 CSV 포맷에 맞춰 안전하게 저장하기
 */
function writeTeamsCSV(headers, dataList) {
    // 헤더와 데이터를 다시 하나의 2차원 배열로 병합
    const outputRows = [headers, ...dataList];

    // 2차원 배열을 SheetJS의 워크시트 객체로 변환
    const newSheet = XLSX.utils.aoa_to_sheet(outputRows);
    const newWorkbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(newWorkbook, newSheet, "Teams");

    // 💡 파이썬 Pandas와 호환성이 완벽한 UTF-8-BOM(utf-8-sig) 포맷으로 쓰기 처리
    XLSX.writeFile(newWorkbook, CSV_PATH, { bookType: 'csv', FS: ',', writeOptions: { BOM: true } });
}

// =========================================================================
// 📡 REST API 엔드포인트 라우팅 규격 정의
// =========================================================================

// 1. 실시간 가용 현금 조회 API
app.get('/api/team-cash/:teamId', (req, res) => {
    const teamId = req.params.teamId.toUpperCase();
    const { headers, dataList } = readTeamsCSV();

    const teamIdx = headers.indexOf('Team');
    const capitalIdx = headers.indexOf('capital');

    console.log(headers);

    // 리스트 안에서 대상 팀 ID 찾기
    const teamRow = dataList.find(row => row[teamIdx]?.toString().trim().toUpperCase() === teamId);

    if (teamRow) {
        const cashValue = parseInt(teamRow[capitalIdx]) || 0;
        res.json({ cash: cashValue });
    } else {
        res.status(404).json({ error: "존재하지 않는 팀입니다." });
    }
});

// 2. [정산 코어] 주식 미니게임 베팅 및 정산 후 복사본 CSV 영구 저장
app.post('/api/invest', (req, res) => {
    const { teamId, stockId, amount } = req.body;
    const upperTeam = teamId.toUpperCase();
    const upperStock = stockId.toUpperCase();
    const betAmount = parseInt(amount);

    // CSV 데이터 파싱 실행
    const { headers, dataList } = readTeamsCSV();
    const teamIdx = headers.indexOf('Team');
    const capitalIdx = headers.indexOf('capital');

    const teamRow = dataList.find(row => row[teamIdx]?.toString().trim().toUpperCase() === upperTeam);

    if (!teamRow) return res.status(400).json({ message: "존재하지 않는 조 ID입니다." });
    if (!STOCK_SCENARIO[upperStock]) return res.status(400).json({ message: "존재하지 않는 주식 종목입니다." });
    if (isNaN(betAmount) || betAmount <= 0) return res.status(400).json({ message: "올바른 투자 자금을 입력해 주세요." });

    const currentCash = parseInt(teamRow[capitalIdx]) || 0;
    if (currentCash < betAmount) {
        return res.status(400).json({ message: `팀의 보유 현금이 부족합니다. (현재 파일 잔고: ${currentCash.toLocaleString()}원)` });
    }

    // 🧮 시나리오 정산 공식 가동
    const rate = STOCK_SCENARIO[upperStock];
    const finalPayout = Math.round((betAmount * rate) / 10) * 10; // 원단위 절사
    const netProfit = finalPayout - betAmount;

    // 데이터 교체 연산 실행
    const nextCash = currentCash - betAmount + finalPayout;
    teamRow[capitalIdx] = nextCash; // 배열 내부의 현금 데이터 스왑 정정

    // 🔥 [핵심] xlsx 라이브러리를 통해 파이썬 원본 Teams.csv.csv 파일에 즉시 영구 쓰기
    writeTeamsCSV(headers, dataList);

    console.log(`💾 [XLSX 미니게임 완결] ${upperTeam}팀 -> ${upperStock}종목 정산 완료 및 CSV 쓰기 완결.`);

    res.json({
        success: true,
        oldCash: currentCash,
        newCash: nextCash,
        invested: betAmount,
        targetStock: upperStock,
        rate: (rate - 1) * 100,
        finalPayout: finalPayout,
        netProfit: netProfit
    });
});

app.listen(PORT, () => {
    console.log(`🚀 미니게임 서버가 http://localhost:${PORT} 에서 정상 가동 중입니다.`);
});