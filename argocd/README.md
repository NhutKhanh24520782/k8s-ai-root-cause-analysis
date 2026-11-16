# Kiến Trúc GitOps & Hướng Dẫn Vận Hành ArgoCD

Tài liệu mô tả kiến trúc GitOps cho dự án **AI-Powered Root Cause Analysis for Kubernetes Microservices**.

---

## 1. Nguyên Lý Phân Tách CI và CD

Dự án áp dụng triệt để nguyên lý GitOps:

1. **GitHub Actions chỉ làm CI:**
   - Kích hoạt khi Developer push một Git Tag (vd: `v1.0.1`).
   - Kiểm tra syntax, chạy test, build Docker image cho 3 microservices nghiệp vụ (`api-gateway`, `order-service`, `payment-service`). *(Lưu ý: `rca-api` tạm thời được bỏ qua để tập trung hoàn thiện pipeline core services trước).*
   - Push image lên Amazon ECR với tag định danh `v1.0.1` và `latest`.
   - **Tuyệt đối không can thiệp** vào Kubernetes cluster.

2. **GitHub Actions Dispatch phê duyệt (Approve & Promote):**
   - Quản lý / Kỹ sư trưởng kích hoạt bằng tay trên giao diện GitHub Actions (`workflow_dispatch`).
   - Chọn phiên bản tag cần phát hành (vd: `v1.0.1`) và môi trường đích (`dev`, `staging`, `prod`).
   - Workflow kiểm tra xem tag đã có trên ECR chưa, cập nhật file `kustomization.yaml` tương ứng rồi commit vào Git.

3. **ArgoCD đảm nhận toàn bộ CD:**
   - ArgoCD theo dõi Git repository.
   - Khi thấy commit mới thay đổi `newTag` trong thư mục `kubernetes/overlays/<env>/`, ArgoCD tự động thực hiện đồng bộ (Sync) và Rolling Update các pods trên EKS.

---

## 2. Cấu Trúc Thư Mục GitOps

```
k8s-ai-root-cause-analysis/
├── .github/workflows/
│   ├── ci.yml                 # CI: Build & Push ECR theo Git Tag
│   └── cd-approve.yml         # CD: Manual workflow_dispatch approve tag
│
├── kubernetes/
│   ├── base/                  # Manifests gốc (api-gateway, order, payment; rca-api tạm exclude)
│   │   ├── api-gateway/
│   │   ├── order-service/
│   │   ├── payment-service/
│   │   ├── rca-api/           # (Tạm comment trong kustomization.yaml)
│   │   └── kustomization.yaml
│   └── overlays/              # Cấu hình theo môi trường
│       ├── dev/kustomization.yaml     # 1 replica, automated sync
│       ├── staging/kustomization.yaml # 2 replicas, automated sync
│       └── prod/kustomization.yaml    # 2 replicas, manual sync required
│
└── argocd/
    ├── apps/                  # Khai báo ArgoCD Applications
    │   ├── app-of-apps.yaml
    │   ├── microservices-dev.yaml
    │   ├── microservices-staging.yaml
    │   └── microservices-prod.yaml
    ├── install/               # Cài đặt ArgoCD
    │   ├── argocd-namespace.yaml
    │   └── README.md
    └── README.md
```

---

## 3. Các Lệnh Vận Hành Thường Dùng (ArgoCD CLI)

```bash
# Xem danh sách ứng dụng đang chạy
argocd app list

# Kiểm tra chi tiết trạng thái đồng bộ và sức khỏe (Health)
argocd app get microservices-dev

# Đồng bộ ứng dụng thủ công (bắt buộc đối với môi trường prod)
argocd app sync microservices-prod

# Xem lịch sử các lần triển khai
argocd app history microservices-dev

# Rollback nhanh về phiên bản commit trước đó
argocd app rollback microservices-dev <ID_REVISION>

# So sánh sự sai lệch giữa cluster và file cấu hình trên Git
argocd app diff microservices-dev
```

