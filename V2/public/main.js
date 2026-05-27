// public/main.js

// 1. 텍스트 UI를 업데이트하는 함수 (기존과 동일)
function updateUI(data) {
  const elements = document.querySelectorAll('[data-sheet]');
  elements.forEach(element => {
    const sheetName = element.dataset.sheet;
    const row = element.dataset.row;
    const col = element.dataset.col;

    if (sheetName && row && col && data[sheetName] && data[sheetName][row - 1] && data[sheetName][row - 1][col - 1] !== undefined) {
      const value = data[sheetName][row - 1][col - 1];
      element.textContent = value;
    } else {
      console.warn(`'${sheetName}' 시트의 [${row}행, ${col}열]에 해당하는 데이터가 없습니다.`);
    }
  });
}

// 2. 차트를 업데이트하는 함수 (새로 추가)
function updateCharts(chartsData) {
  if (!chartsData) {
    console.error('차트 데이터가 존재하지 않습니다.');
    return;
  }
  
  // 모든 차트 라벨을 고정된 라벨로 덮어쓰기
  const fixedLabelsBar = ['OpenAI', 'Tesla', '삼성전자', 'Palantir', 'Instagram', 'Amazon', 'Google', 'NVIDIA'];
  const fixedLabelsDoughnut = ['OpenAI', 'Tesla', '삼성전자', 'Palantir', 'Instagram', 'Amazon', 'Google', 'NVIDIA','System'];
  for (let i = 0; i < 8; i++) {
    // 바 차트 업데이트
    const barCanvas = document.getElementById(`s${i + 2}-bar1`);
    const barChartIdx = i + 8; // chartsData[8]~[15]가 바 차트 데이터
    if (barCanvas && window.drawBarChart && chartsData[barChartIdx] && chartsData[barChartIdx].values) {
      window.drawBarChart(barCanvas, fixedLabelsBar, chartsData[barChartIdx].values);
    }

    // 도넛 차트 업데이트
    const donutCanvas = document.getElementById(`s${i + 2}-donut1`);
    if (donutCanvas && window.drawDoughnutChart && chartsData[i] && chartsData[i].values) {
      window.drawDoughnutChart(donutCanvas, fixedLabelsDoughnut, chartsData[i].values);
    }
  }
}

// 3. 5초마다 서버로부터 데이터를 가져와 모든 것을 업데이트하는 메인 함수
async function fetchAndUpdateAllData() {
  try {
    const response = await fetch('/api/data');
    if (!response.ok) {
      throw new Error(`HTTP Error: ${response.status}`);
    }
    const data = await response.json();

    // 가져온 데이터로 UI와 차트를 모두 업데이트합니다.
    updateUI(data);
    updateCharts(data.chartsData);
    console.log(data);

  } catch (error) {
    console.error('데이터를 가져오는 데 실패했습니다:', error);
    // 에러 발생 시 더미 데이터로 차트를 그리는 로직을 여기에 추가할 수 있습니다.
    // 예: drawDummyCharts();
  }
}

// 4. 페이지 로드가 완료되면 즉시 한 번 실행하고, 그 후 4초마다 반복 실행
document.addEventListener('DOMContentLoaded', () => {
  fetchAndUpdateAllData(); // 페이지 로드 시 즉시 실행
  setInterval(fetchAndUpdateAllData, 4000); // 4초마다 반복 실행
});