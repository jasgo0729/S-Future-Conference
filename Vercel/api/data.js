// ✨ googleapis 라이브러리를 더 이상 사용하지 않습니다.

// 헬퍼 함수 1, 2는 기존과 동일합니다.
function extractChartDataByColumn(sheetData, labelCol, valueCol) {
    const labels = [];
    const values = [];
    for (let i = 1; i < sheetData.length; i++) {
        const row = sheetData[i];
        if (row && row[labelCol] && row[valueCol]) {
            labels.push(row[labelCol]);
            values.push(Number(row[valueCol]));
        }
    }
    return { labels, values };
}

function extractChartDataByRow(sheetData, dataRowIndex) {
    if (!sheetData || sheetData.length <= dataRowIndex) {
        return { labels: [], values: [] };
    }
    const labels = sheetData[0].slice(1);
    const values = sheetData[dataRowIndex].slice(1).map(Number);
    return { labels, values };
}

export default async function handler(req, res) {
    try {
        // --- 1. 환경 변수에서 ID와 새로 추가한 API 키를 가져옵니다 ---
        // 수정 후
        const apiKey = process.env.GOOGLE_API_KEY;;
        const spreadsheetId_teams = process.env.SPREADSHEET_ID_TEAMS;
        const spreadsheetId_holdings = process.env.SPREADSHEET_ID_HOLDINGS;
        const spreadsheetId_subsidiarys = process.env.SPREADSHEET_ID_SUBSIDIARYS;

        // --- 2. Vercel Data Cache를 적용하여 fetch로 API를 호출합니다 ---
        const fetchOptions = {
            next: {
                revalidate: 4 // ✨ 이 옵션 하나로 4초간의 캐싱이 완벽하게 동작합니다.
            }
        };

        const [teamsRes, holdingsRes, subsidiarysRes] = await Promise.all([
            fetch(`https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId_teams}/values/A:Z?key=${apiKey}`, fetchOptions),
            fetch(`https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId_holdings}/values/A:Z?key=${apiKey}`, fetchOptions),
            fetch(`https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId_subsidiarys}/values/A:Z?key=${apiKey}`, fetchOptions)
        ]);

        // --- 3. 각 응답을 JSON 형태로 파싱합니다 ---
        const teamsJson = await teamsRes.json();
        const holdingsJson = await holdingsRes.json();
        const subsidiarysJson = await subsidiarysRes.json();

        // API 호출 중 발생한 에러를 확인합니다.
        if (teamsJson.error || holdingsJson.error || subsidiarysJson.error) {
            console.error('Google Sheets API Error:', teamsJson.error || holdingsJson.error || subsidiarysJson.error);
            throw new Error('Google Sheets API에서 데이터를 가져오는 데 실패했습니다.');
        }

        const allData = {
            teams: teamsJson.values || [],
            holdings: holdingsJson.values || [],
            subsidiarys: subsidiarysJson.values || [],
        };

        // --- 4. 데이터 가공 로직은 기존과 동일합니다 ---
        const chartsData = [
            extractChartDataByColumn(allData.holdings, 0, 1),
            extractChartDataByColumn(allData.holdings, 0, 2),
            extractChartDataByColumn(allData.holdings, 0, 3),
            extractChartDataByColumn(allData.holdings, 0, 4),
            extractChartDataByColumn(allData.holdings, 0, 5),
            extractChartDataByColumn(allData.holdings, 0, 6),
            extractChartDataByColumn(allData.holdings, 0, 7),
            extractChartDataByColumn(allData.holdings, 0, 8),
            extractChartDataByRow(allData.holdings, 1),
            extractChartDataByRow(allData.holdings, 2),
            extractChartDataByRow(allData.holdings, 3),
            extractChartDataByRow(allData.holdings, 4),
            extractChartDataByRow(allData.holdings, 5),
            extractChartDataByRow(allData.holdings, 6),
            extractChartDataByRow(allData.holdings, 7),
            extractChartDataByRow(allData.holdings, 8),
        ];

        const responseData = {
            ...allData,
            chartsData,
        };

        res.status(200).json(responseData);

    } catch (error) {
        console.error('핸들러 에러:', error);
        res.status(500).json({ error: error.message || '스프레드시트 데이터를 가져오는 데 실패했습니다.' });
    }
}