#!/bin/bash
# 一键部署：同步代码 → 三台重建镜像 → 重启 Pod
# 用法：在 master 上执行 sh deploy.sh

set -e
NODES="192.168.20.143 192.168.20.144"
SRC_DIR="/root/ruanks"

echo "📦 同步文件到所有节点..."
for ip in $NODES; do
    scp -r $SRC_DIR/src/* root@$ip:$SRC_DIR/src/
    scp $SRC_DIR/Dockerfile $SRC_DIR/.dockerignore $SRC_DIR/requirements.txt root@$ip:$SRC_DIR/ 2>/dev/null
    echo "   ✅ $ip"
done

echo "🐳 三台重建镜像..."
docker rmi ruanks:latest 2>/dev/null; docker build --no-cache -t ruanks:latest $SRC_DIR/ && echo "   ✅ master"
for ip in $NODES; do
    ssh root@$ip "docker rmi ruanks:latest 2>/dev/null; docker build --no-cache -t ruanks:latest $SRC_DIR/" && echo "   ✅ $ip"
done

echo "🔄 重启 Pod..."
kubectl delete pods -n ruanks --all

echo "⏳ 等待 Pod 就绪..."
kubectl -n ruanks wait --for=condition=ready pod -l app=ruanks --timeout=120s 2>/dev/null
kubectl -n ruanks get pods

echo "✅ 部署完成！"
