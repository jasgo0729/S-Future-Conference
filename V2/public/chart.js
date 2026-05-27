// public/chart.js
document.getElementById("team_number").innerText = localStorage.getItem("user_number");
const chartStyle = document.createElement('style');
chartStyle.innerHTML = `

.chart-slot, #chartWrap {
    width: 380px;
    height: 390px;
    margin: 0 auto;
}
.chart-slot canvas, #chartWrap canvas {
    display: block;
    width: 100% !important;
    height: 100% !important;
}
body { margin: 0; font-family: Pretendard; }
`;
document.head.appendChild(chartStyle);

// [2] 바 차트 바깥쪽 라벨 플러그인: 바의 오른쪽에 값 표시
const outsideValueLabels = {
    id: 'outsideValueLabels',
    afterDatasetsDraw(chart, args, opts) {
        const { ctx, chartArea, data } = chart;
        const meta = chart.getDatasetMeta(0);
        const ds = data.datasets[0];
        if (!meta || !meta.data) return;
        const pad = opts?.padding ?? 5;
        const color = opts?.color ?? '#FFFFFF';
        const font = opts?.font ?? { size: 12, weight: '600', family: 'Pretendard' };
        const formatter = opts?.formatter ?? ((v) => String(v));
        ctx.save();
        ctx.fillStyle = color;
        ctx.textAlign = 'left';
        ctx.textBaseline = 'middle';
        ctx.font = `${font.weight} ${font.size}px ${font.family}`;
        ds.data.forEach((v, i) => {
            const y = meta.data[i].y;
            ctx.fillText(formatter(v, i, data.labels), chartArea.right + pad, y);
        });
        ctx.restore();
    }
};

// [3] 바 차트 그리기 함수: 데이터와 옵션을 받아 가로 바 차트 생성
function drawBarChart(canvas, originalLabels, originalValues) {
    if (!canvas) return;
    const labels = originalLabels;
    const values = originalValues.map(v => parseFloat(v) || 0);

    if (labels.length === 0 || values.length === 0) return;

    if (!canvas._chartInstance) {
        const ctx = canvas.getContext('2d');
        const remainders = values.map(v => Math.max(0, 100 - v));
        const data = {
            labels,
            datasets: [
                {
                    label: '달성',
                    axis: 'y',
                    data: values,
                    backgroundColor: (context) => {
                        const chart = context.chart;
                        const { ctx, chartArea } = chart;

                        if (!chartArea) {
                            return 'rgba(27, 83, 155, 1)';
                        }

                        const gradient = ctx.createLinearGradient(chartArea.left, 0, chartArea.right, 0);
                        gradient.addColorStop(0, 'rgba(27, 83, 155, 1)');
                        gradient.addColorStop(0.5, 'rgba(100, 180, 255, 1)');
                        gradient.addColorStop(1, 'rgba(27, 83, 155, 1)');
                        return gradient;
                    },
                    borderSkipped: false,
                    borderRadius: { topRight: 0, bottomRight: 0 },
                    barThickness: 20,
                    stack: 'progress'
                },
                {
                    label: '남음',
                    axis: 'y',
                    data: remainders,
                    backgroundColor: '#e6e6e6',
                    borderSkipped: false,
                    borderRadius: { topRight: 20, bottomRight: 20 },
                    barThickness: 20,
                    stack: 'progress'
                }
            ]
        };
        const config = {
            type: 'bar',
            data,
            options: {
                indexAxis: 'y', responsive: true, maintainAspectRatio: false,
                layout: { padding: { right: 35, left: 0 } },
                scales: {
                    x: { max: 100, stacked: true, grid: { display: false }, border: { display: false }, ticks: { display: false } },
                    y: { stacked: true, grid: { display: false }, border: { display: false }, ticks: { display: true, font: { size: 13, family: 'Pretendard'} , color: '#fff'}}
                },
                plugins: {
                    datalabels: {
                        display: false // 내부 라벨 끄기
                    },
                    legend: { display: false }, tooltip: { enabled: false },
                    outsideValueLabels: { padding: 5, color: '#fff', font: { size: 13, weight: '600' }, formatter: (v) => v }
                }
            }
        };
        canvas._chartInstance = new Chart(ctx, config);
    } else {
        const chart = canvas._chartInstance;
        chart.data.labels = labels;
        chart.data.datasets[0].data = values;
        chart.data.datasets[1].data = values.map(v => Math.max(0, 100 - v));
        chart.update();
    }
}

// [4] 도넛 차트 그리기 함수: 데이터와 옵션을 받아 도넛 차트 생성
function drawDoughnutChart(canvas, labels, values) {
    if (!canvas) return;
    const numericValues = values.map(v => {
        const num = parseFloat(v);
        return (isNaN(num) || num < 0) ? 0 : (num === 0 ? 0.01 : num);
    });
    const colorArr = ['#ABF2E0', '#F2ABAB', '#AFDFFF', '#FFFFFF', '#FFC8E8', '#F9C696', '#FFEF80', '#C2F2AB', '#39394B'];
    const bgColors = Array.isArray(numericValues) ? colorArr.slice(0, numericValues.length) : colorArr;

    if (labels.length === 0 || values.length === 0) return;

    if (!canvas._chartInstance) {
        const ctx = canvas.getContext('2d');
        const data = {
            labels,
            datasets: [{ data: numericValues, backgroundColor: bgColors, borderColor: '#1B2431', borderWidth: 1, hoverOffset: 4 }]
        };
        const config = {
            type: 'doughnut',
            data,
            options: {
                responsive: true, maintainAspectRatio: false, cutout: '50%', radius: '95%',
                layout: { padding: 25 },
                plugins: {
                    outsideValueLabels: false,
                    legend: { display: false }, tooltip: { enabled: false },
                    datalabels: {
                        formatter: (value, context) => {
                            if (value === 0.01) return '';
                            const label = context.chart.data.labels[context.dataIndex];
                            return `${label} ${value}주`;
                        },
                        font: { size: 9, weight: 'bold',family: 'Pretendard' },
                        color: '#fff',
                        strokeColor: '#fff',
                        strokeWidth: 2,
                        anchor: 'end',
                        align: 'end',
                        offset: 8,
                        clamp: true
                    }
                }
            }
        };
        canvas._chartInstance = new Chart(ctx, config);
    } else {
        const chart = canvas._chartInstance;
        chart.data.labels = labels;
        chart.data.datasets[0].data = numericValues;
        chart.data.datasets[0].backgroundColor = bgColors;
        chart.update();
    }
}

if (window.Chart) {
    Chart.register(outsideValueLabels);
    if (window.ChartDataLabels) Chart.register(window.ChartDataLabels);
} else {
    document.addEventListener('DOMContentLoaded', () => {
        if (window.Chart) Chart.register(outsideValueLabels);
        if (window.ChartDataLabels) Chart.register(window.ChartDataLabels);
    });
}
// 페이지가 로드되면 차트 관련 스타일과 함수, 플러그인을 등록합니다.
document.addEventListener('DOMContentLoaded', () => {
    // [1] 공통 차트 CSS: 차트 영역 및 폰트 스타일 지정

    // [5] Chart.js 및 datalabels 플러그인 등록: 커스텀 플러그인과 datalabels 플러그인 Chart.js에 등록
    

    // [6] 차트 그리기 함수를 window 객체에 등록하여 외부에서 호출 가능하게 함
    window.drawBarChart = drawBarChart;
    window.drawDoughnutChart = drawDoughnutChart;
});