const express = require('express');
const path = require('path');
const fs = require('fs');
const XLSX = require('xlsx'); // SheetJS 라이브러리 로드
const iconv = require('iconv-lite'); // 💡 인코딩 트러블 원천 차단용 라이브러리
const app = express();
const PORT = 3005;

// 파이썬 메인 엔진의 Teams.csv.csv 실제 파일 경로
const CSV_PATH = path.join(__dirname, '../V2/data/Teams.csv.csv');

app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// 🎬 [고정 시나리오] 종목별 수익률 배당표
const STOCK_SCENARIO = {
    "A": 1.5, "B": 0.3, "C": 0.5, "D": 0.7,
    "E": 1.3, "F": 1.7
};

// 🔐 실시간 팀 매칭용 마스터 보안키 설정
const SECRET_KEYS = {
    "1588": "OpenAI", "2424": "Tesla", "3693": "삼성전자", "4885": "Palantir",
    "5959": "Instagram", "6256": "Amazon", "7749": "Google", "8881": "NVIDIA"
};

// 📋 팀 이름 문자열을 CSV 파일 내부의 'Team' 알파벳 ID로 전환하기 위한 매핑 매퍼
const TEAM_NAME_TO_ID = {
    "OpenAI": "A", "Tesla": "B", "삼성전자": "C", "Palantir": "D",
    "Instagram": "E", "Amazon": "F", "Google": "G", "NVIDIA": "H"
};

/**
 * 🛠️ [XLSX 버퍼 버전] Teams.csv.csv 안전하게 로드하고 파싱하기 (한글 깨짐 원천 차단)
 */
function readTeamsCSV() {
    if (!fs.existsSync(CSV_PATH)) {
        console.error(`❌ 파일을 찾을 수 없습니다: ${CSV_PATH}`);
        return { headers: [], dataList: [] };
    }

    // 💡 fs로 가공되지 않은 순수 버퍼 바이트를 가져와 SheetJS에 바인딩
    const fileBuffer = fs.readFileSync(CSV_PATH);
    const workbook = XLSX.read(fileBuffer, { type: 'buffer' });
    const sheetName = workbook.SheetNames[0];
    const sheet = workbook.Sheets[sheetName];

    const rawRows = XLSX.utils.sheet_to_json(sheet, { header: 1, defval: "" });
    
    if (rawRows.length === 0) return { headers: [], dataList: [] };

    const headers = rawRows[0];
    const dataList = rawRows.slice(1);

    return { headers, dataList };
}

/**
 * 🛠️ [XLSX 버퍼 버전] UTF-8-BOM 포맷을 강제 주입하여 안전하게 덮어쓰기
 */
function writeTeamsCSV(headers, dataList) {
    const outputRows = [headers, ...dataList];

    const newSheet = XLSX.utils.aoa_to_sheet(outputRows);
    const newWorkbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(newWorkbook, newSheet, "Teams");

    // 메모리 상에서 순수 CSV 문자열로 추출
    const csvOutput = XLSX.write(newWorkbook, { bookType: 'csv', type: 'string', FS: ',' });
    
    // 문자열 정중앙 맨 앞에 BOM 마커('\ufeff')를 밀어넣고 바이너리로 변경 (파이썬 pandas sig 매칭)
    const encodedBuffer = iconv.encode('\ufeff' + csvOutput, 'utf-8');
    
    fs.writeFileSync(CSV_PATH, encodedBuffer);
}

// =========================================================================
// 📡 REST API 엔드포인트 라우팅 규격 정의
// =========================================================================

// 💡 [신규 추가] 1. 프론트엔드 실시간 키 대조 및 자산 리턴 API (GET)
app.get('/api/verify-key', (req, res) => {
    const { key } = req.query;
    
    if (!key) return res.status(400).json({ valid: false, message: "키가 제공되지 않았습니다." });

    // 보안키에 해당하는 팀 이름(예: 'OpenAI') 획득
    const teamName = SECRET_KEYS[key];
    if (!teamName) {
        return res.json({ valid: false, message: "유효하지 않은 보안키입니다." });
    }

    // 팀 이름을 기반으로 알파벳 ID 매핑 (예: 'A')
    const teamId = TEAM_NAME_TO_ID[teamName];
    
    // CSV 로드하여 현재 실시간 가용 자산 추적
    const { headers, dataList } = readTeamsCSV();
    const teamIdx = headers.indexOf('Team');
    const capitalIdx = headers.indexOf('capital');

    const teamRow = dataList.find(row => row[teamIdx]?.toString().trim().toUpperCase() === teamId);

    if (teamRow) {
        const cashValue = parseInt(teamRow[capitalIdx]) || 0;
        return res.json({
            valid: true,
            teamId: teamId,
            teamName: teamName,
            cash: cashValue
        });
    } else {
        return res.status(404).json({ valid: false, message: "CSV 파일 내에서 팀 매핑 정보를 찾을 수 없습니다." });
    }
});


// 💡 [수정] 2. [정산 코어] 보안키 2중 검증 기반 주식 베팅 및 파일 정산
app.post('/api/invest', (req, res) => {
    const { secretKey, teamId, stockId, amount } = req.body;
    
    const upperTeam = teamId.toUpperCase();
    const upperStock = stockId.toUpperCase();
    const betAmount = parseInt(amount);

    // 🚨 [보안 추가] 백엔드 단에서 변조 방지를 위한 보안키 유효성 2차 크로스 체크
    const expectedTeamName = SECRET_KEYS[secretKey];
    if (!expectedTeamName || TEAM_NAME_TO_ID[expectedTeamName] !== upperTeam) {
        return res.status(401).json({ message: "❌ [인증 오류] 보안키와 요청된 팀 정보가 일치하지 않습니다." });
    }

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
    teamRow[capitalIdx] = nextCash; 

    // 안전하게 덮어쓰기 가동
    writeTeamsCSV(headers, dataList);

    console.log(`💾 [XLSX 미니게임 자동 매칭 완결] 인증조: ${expectedTeamName}(${upperTeam}팀) -> ${upperStock}종목 정산 반영.`);

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