# Hướng Dẫn Cài Đặt ArgoCD Trên Amazon EKS

Tài liệu này hướng dẫn cài đặt và thiết lập ArgoCD cho dự án AI-Powered Root Cause Analysis.

---

## 1. Yêu cầu tiên quyết

- `kubectl` đã kết nối tới EKS cluster:
  ```bash
  aws eks update-kubeconfig --region ap-southeast-1 --name ai-rca-dev-cluster
  kubectl get nodes
  ```

---

## 2. Các bước cài đặt ArgoCD

### Bước 2.1 — Tạo namespace và cài đặt ArgoCD manifests
```bash
# Tạo namespace argocd
kubectl apply -f argocd/install/argocd-namespace.yaml

# Cài đặt ArgoCD bản stable
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Kiểm tra trạng thái pods (chờ ~2-3 phút để tất cả pods Ready)
kubectl wait pods -n argocd --all --for=condition=Ready --timeout=300s
```

### Bước 2.2 — Lấy mật khẩu đăng nhập ban đầu của tài khoản `admin`
```bash
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d
echo ""
```

---

## 3. Truy cập ArgoCD Web UI

### Phương án A: Port-forward nội bộ (Khuyến nghị cho Lab/Dev)
```bash
kubectl port-forward svc/argocd-server -n argocd 8080:443
```
- Mở trình duyệt truy cập: `https://localhost:8080`
- **Username:** `admin`
- **Password:** `<chuỗi_mật_khẩu_lấy_ở_bước_2.2>`

### Phương án B: Sử dụng AWS Load Balancer
```bash
kubectl patch svc argocd-server -n argocd -p '{"spec": {"type": "LoadBalancer"}}'
kubectl get svc argocd-server -n argocd -w
```

---

## 4. Đăng ký Repository với ArgoCD

Dùng ArgoCD CLI hoặc qua UI để thêm Git repo:
```bash
# Đăng nhập ArgoCD CLI
argocd login localhost:8080 --username admin --password <INITIAL_PASSWORD> --insecure

# Thêm private/public repo
argocd repo add https://github.com/NhutKhanh24520782/k8s-ai-root-cause-analysis.git \
  --username NhutKhanh24520782 \
  --password <GITHUB_PERSONAL_ACCESS_TOKEN>
```

---

## 5. Bootstrap App-of-Apps

Khởi tạo mô hình quản lý ứng dụng tập trung (chỉ cần chạy duy nhất 1 lần):
```bash
kubectl apply -f argocd/apps/app-of-apps.yaml

# Kiểm tra danh sách ứng dụng ArgoCD tự động tạo ra
argocd app list
```
Sau lệnh trên, ArgoCD sẽ tự động đăng ký và quản lý các Application:
- `microservices-dev`
- `microservices-staging`
- `microservices-prod`

