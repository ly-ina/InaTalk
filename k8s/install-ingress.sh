#!/bin/bash
# ============================================
# 安装 nginx-ingress（兼容旧版 k8s）
# 在 k8s-master 上执行
# ============================================
set -e

K8S_MINOR=$(kubectl version --short 2>/dev/null | grep Server | grep -oP 'v\d+\.\d+' | cut -d. -f2 || echo "0")
echo "检测到 k8s 版本: 1.${K8S_MINOR}"

if [ "$K8S_MINOR" -lt 20 ]; then
    echo "→ k8s 版本低于 1.20，使用兼容的 nginx-ingress v1.0.5"
    INGRESS_VER="controller-v1.0.5"
elif [ "$K8S_MINOR" -lt 22 ]; then
    echo "→ 使用 nginx-ingress v1.1.3"
    INGRESS_VER="controller-v1.1.3"
elif [ "$K8S_MINOR" -lt 25 ]; then
    echo "→ 使用 nginx-ingress v1.4.0"
    INGRESS_VER="controller-v1.4.0"
else
    echo "→ 使用最新 nginx-ingress v1.10.1"
    INGRESS_VER="controller-v1.10.1"
fi

URL="https://raw.githubusercontent.com/kubernetes/ingress-nginx/${INGRESS_VER}/deploy/static/provider/baremetal/deploy.yaml"
echo "→ 下载: $URL"
kubectl apply -f "$URL" --validate=false

echo ""
echo "等待 ingress-nginx 启动..."
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=120s

echo ""
echo "安装完成！查看状态:"
kubectl get pods -n ingress-nginx
kubectl get svc -n ingress-nginx
