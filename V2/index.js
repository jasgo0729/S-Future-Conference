import express from 'express';
import path from 'path';
import sheetRouter from './api/data.js';

const app = express();
const port = 3000;

app.use(express.json());
app.use(express.urlencoded({ extended: true }));

app.use(express.static(path.join(process.cwd(), 'public')));

app.use('/api', sheetRouter);

// 샘플 API 엔드포인트
app.get('/api/status', (req, res) => {
  res.json({
    status: 'success',
    message: '서버가 연결되었습니다.'
  });
});

app.get('/trade_order', (req, res) => {
  const filePath = path.join(process.cwd(), 'public', 'test.html');
  res.sendFile(filePath);
});

// 404 에러 처리 미들웨어
app.use((req, res, next) => {
  res.status(404).send('페이지를 찾을 수 없습니다.');
});

// 서버 시작
app.listen(port, () => {
  console.log(`서버가 http://localhost:${port} 에서 실행 중입니다.`);
});