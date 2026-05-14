
#!/bin/bash

# 사용법 안내 함수
usage() {
    echo "Usage: $0 {v2|buzzer|2t1f|all}"
    exit 1
}

# 인자가 없는 경우 안내 출력
if [ -z "$1" ]; then
    usage
fi

# 빌드 실행 함수 (플랫폼 명시)
build_image() {
    local FOLDER=$1
    local TAG=$2
    echo "----------------------------------------------------"
    echo "🚀 Building and Pushing: $TAG (from ./$FOLDER)"
    echo "----------------------------------------------------"
    
    docker buildx build --platform linux/amd64,linux/arm64 \
        -t "jasgo/$TAG:latest" \
        "./$FOLDER" \
        --push
}

# 인자에 따른 분기 처리
case "$1" in
    v2)
        build_image "V2" "sfc_v2"
        ;;
    buzzer)
        build_image "Buzzer" "sfc_buzzer"
        ;;
    2t1f)
        build_image "2t1f" "sfc_2t1f"
        ;;
    all)
        build_image "V2" "sfc_v2"
        build_image "Buzzer" "sfc_buzzer"
        build_image "2t1f" "sfc_2t1f"
        ;;
    *)
        usage
        ;;
esac

echo "✅ All processes completed!"