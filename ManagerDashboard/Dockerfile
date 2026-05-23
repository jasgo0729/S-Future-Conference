# 1단계: 파이썬 3.14 공식 슬림 이미지로 베이스 변경
FROM python:3.14-slim

# 2단계: 파이썬 최신 빌드에 필요한 리눅스 컴파일러 컴포넌트 설치
# (3.14의 경우 의존성 패키지들이 소스 컴파일로 설치될 확률이 높으므로 git과 필수 빌드 툴을 넉넉히 포함합니다)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    git \
    && rm -rf /var/lib/apt/lists/*

# 3단계: 가상 환경 디렉토리 지정
WORKDIR /app

# 4단계: pip 최신화 및 의존성 캐싱 빌드
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 5단계: 앱 소스 전역 복사
COPY . .

# 8단계: uvicorn 서비스 가동 환경설정
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "3003"]