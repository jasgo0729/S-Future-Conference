import express from 'express';
import path from 'path';
import * as fs from 'fs';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const XLSX = require('xlsx');

const router = express.Router();

// 헬퍼 함수들은 기존 로직을 유지하되, 데이터가 없을 경우를 대비해 보강합니다.
function extractChartDataByColumn(sheetData, labelCol, valueCol) {
    if (!sheetData || sheetData.length === 0) return { labels: [], values: [] };
    const labels = [];
    const values = [];
    for (let i = 1; i < sheetData.length; i++) {
        const row = sheetData[i];
        if (row && row[labelCol] !== undefined) {
            labels.push(row[labelCol]);
            values.push(Number(row[valueCol]) || 0);
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

router.get('/data', async (req, res) => {
    try {
        // 1. 파일 경로 설정 (프로젝트 루트의 data 폴더)
        const dataPath = path.join(process.cwd(), 'data');
        
        // 2. 각 파일 읽기 함수 (xlsx, csv 모두 XLSX.readFile로 읽을 수 있습니다)
        const readSheet = (fileName) => {
            const filePath = path.join(dataPath, fileName);
            if (!fs.existsSync(filePath)) {
                console.warn(`${fileName} 파일이 없습니다.`);
                return [];
            }
            const workbook = XLSX.readFile(filePath);
            const sheetName = workbook.SheetNames[0]; // 첫 번째 시트 선택
            const sheet = workbook.Sheets[sheetName];
            // header: 1 옵션은 데이터를 이중 배열( [ [], [] ] ) 형태로 반환합니다.
            return XLSX.utils.sheet_to_json(sheet, { header: 1 });
        };

        // 3. 로컬 파일들 읽기
        const allData = {
            teams: readSheet('Teams.xlsx'),
            holdings: readSheet('Holdings.xlsx'), // 또는 'holdings.csv'
            subsidiarys: readSheet('Subsidiarys.xlsx')
        };

        // 4. 데이터 가공 (기존 로직 동일)
        const chartsData = [
            ...Array.from({ length: 8 }, (_, i) => extractChartDataByColumn(allData.holdings, 0, i + 1)),
            // 행(Row) 추출 함수(extractChartDataByRow)는 기존 코드를 그대로 사용하세요.
            ...Array.from({ length: 8 }, (_, i) => extractChartDataByRow(allData.holdings, i + 1))
        ];

        res.status(200).json({
            ...allData,
            chartsData,
        });

    } catch (error) {
        console.error('파일 읽기 에러:', error);
        res.status(500).json({ error: '로컬 데이터를 읽는 중 오류가 발생했습니다.' });
    }
});

// 기존 import 문 아래에 추가
router.get('/order', async (req, res) => {
    try {
        const { securityKey, orderType, team, quantity } = req.query;

        // 필수 데이터 체크
        if (!securityKey || !orderType || !team || !quantity) {
            return res.status(400).json({ error: '모든 필드(securityKey, orderType, team, quantity)를 입력해주세요.' });
        }

        // 2. 파일 경로 설정
        const dataPath = path.join(process.cwd(), 'data');
        const fileName = 'BP_TradeOrder.xlsx'; // 저장할 파일 이름
        const filePath = path.join(dataPath, fileName);

        let workbook;
        let worksheet;
        let sheetData = [];

        // 3. 기존 파일이 있으면 읽어오고, 없으면 새로 생성
        if (fs.existsSync(filePath)) {
            workbook = XLSX.readFile(filePath);
            const sheetName = workbook.SheetNames[0];
            worksheet = workbook.Sheets[sheetName];
            // 기존 데이터를 이중 배열로 변환
            sheetData = XLSX.utils.sheet_to_json(worksheet, { header: 1 });
        } else {
            workbook = XLSX.utils.book_new();
            // 파일이 처음 생성될 경우 헤더 추가
            sheetData = [['Timestamp', 'SecretKey', 'Type', 'Target Team', 'Quantity']];
        }

        // 4. 새로운 행 데이터 생성 (첫 번째 열은 현재 시간)
        const newRow = [
            new Date().toLocaleString(), // 타임스탬프
            securityKey,
            orderType,
            team,
            Number(quantity)
        ];

        // 5. 데이터 배열에 추가
        sheetData.push(newRow);

        // 6. 배열을 다시 시트로 변환하여 워크북에 업데이트
        const newWorksheet = XLSX.utils.aoa_to_sheet(sheetData);
        
        if (workbook.SheetNames.length > 0) {
            workbook.Sheets[workbook.SheetNames[0]] = newWorksheet;
        } else {
            XLSX.utils.book_append_sheet(workbook, newWorksheet, 'Orders');
        }

        // 7. 파일 쓰기 (맥 권한 문제가 발생할 수 있으니 주의)
        XLSX.writeFile(workbook, filePath);

        res.status(200).json({
            message: '주문이 성공적으로 기록되었습니다.',
            data: newRow
        });

    } catch (error) {
        console.error('엑셀 기록 에러:', error);
        res.status(500).json({ error: '엑셀 파일을 수정하는 중 오류가 발생했습니다.' });
    }
});

export default router;