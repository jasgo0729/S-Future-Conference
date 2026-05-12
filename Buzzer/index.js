import express from 'express';
import path from 'path';
import { Server } from 'socket.io';

const app = express();
const port = 3001;
const server = app.listen(port, () => {
  console.log(`서버가 http://localhost:${port} 에서 실행 중입니다.`);
});

const io = new Server(server, {
  cors: {
      origin: `http://localhost:${port}`, // 클라이언트 도메인 주소
      methods: ["GET", "POST"]
  }
});

app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(express.static(path.join(process.cwd(), 'public')));

app.get('/buzzer', (req, res) => {
  const filePath = path.join(process.cwd(), 'public', 'buzzer.html');
  res.sendFile(filePath);
});

app.get('/dashboard', (req, res) => {
  const filePath = path.join(process.cwd(), 'public', 'dashboard.html');
  res.sendFile(filePath);
})

// 404 에러 처리 미들웨어
app.use((req, res, next) => {
  res.status(404).send('페이지를 찾을 수 없습니다.');
});

const socketMananger = new Map();
const buzzerClickOrder = [];

io.on('connection', (socket) => {
  socket.on('disconnect', () => {
    console.log('클라이언트 접속 해제', socket.id);
    clearInterval(socket.interval);
  });

  socket.on('error', (error) => {
    console.error(error);
  });

  socket.on('user_join', (data) => {
    let id = Number(data);
    if (id == NaN) return;
    socketMananger.set(socket.id, id);
    console.log(`${id}: ${socket.id}`);
  });

  socket.on('buzzer', (data) => {
    // console.log(socketMananger.get(socket.id));
    // buzzerClickOrder.push(socketMananger.get(socket.id));
    io.emit('dashboard', socketMananger.get(socket.id));
  });
});
