# FinOps AI — EKS Terraform Deployment

## Architecture

```
                    ┌─────────────────────────────────────────────┐
                    │              AWS Cloud (VPC)                 │
                    │                                             │
 Internet ──▶ ALB ─┤──▶ Frontend (React)    ← EKS Pod            │
                    │──▶ Backend  (FastAPI)  ← EKS Pod            │
                    │    ├── Celery Worker   ← EKS Pod            │
                    │    ├── Celery Beat     ← EKS Pod            │
                    │    └── Ollama (LLM)    ← EKS Pod (GPU)      │
                    │                                             │
                    │   ┌──────────────┐  ┌──────────────┐        │
                    │   │ RDS Postgres │  │  ElastiCache  │        │
                    │   │  (managed)   │  │ Redis (managed│        │
                    │   └──────────────┘  └──────────────┘        │
                    │   ┌──────────────┐                          │
                    │   │   Neo4j      │  ← EKS StatefulSet       │
                    │   │  (graph DB)  │    with EBS PVC           │
                    │   └──────────────┘                          │
                    └─────────────────────────────────────────────┘
```

### Docker Compose → EKS Mapping

| Docker Compose Service | EKS/AWS Resource |
|------------------------|------------------|
| `postgres`             | **RDS PostgreSQL** (managed, Multi-AZ in prod) |
| `redis`                | **ElastiCache Redis** (managed, failover in prod) |
| `neo4j`                | **EKS StatefulSet** + EBS gp3 PVC |
| `backend`              | **EKS Deployment** (2 replicas + HPA) |
| `celery_worker`        | **EKS Deployment** (2 replicas + HPA) |
| `celery_beat`          | **EKS Deployment** (1 replica, Recreate strategy) |
| `frontend`             | **EKS Deployment** (2 replicas + HPA) |
| Ollama (host)          | **EKS Deployment** on GPU node group (g5.xlarge) |

## Prerequisites

- AWS CLI v2 configured with credentials
- Terraform >= 1.0
- kubectl
- Docker (for building images)
- Helm (for AWS Load Balancer Controller)

## Quick Start

```bash
# 1. Deploy infrastructure + app (interactive)
cd terraform
./deploy.sh dev

# 2. Check pods
kubectl get pods -n finops

# 3. Get the ALB URL
kubectl get ingress finops-ingress -n finops \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'
```

## Step-by-Step Manual Deploy

### 1. Provision Infrastructure

```bash
cd terraform
terraform init -upgrade
terraform plan -var-file=environments/dev.tfvars -out=tfplan
terraform apply tfplan
```

### 2. Configure kubectl

```bash
aws eks update-kubeconfig \
  --region us-east-1 \
  --name $(terraform output -raw eks_cluster_name)
```

### 3. Install AWS Load Balancer Controller

```bash
helm repo add eks https://aws.github.io/eks-charts
helm repo update

helm install aws-load-balancer-controller eks/aws-load-balancer-controller \
  -n kube-system \
  --set clusterName=$(terraform output -raw eks_cluster_name) \
  --set serviceAccount.create=true \
  --set serviceAccount.annotations."eks\.amazonaws\.com/role-arn"=$(terraform output -raw lb_controller_role_arn)
```

### 4. Build & Push Images

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=us-east-1
ECR="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

aws ecr get-login-password --region $REGION | \
  docker login --username AWS --password-stdin $ECR

# Backend
docker build -t $ECR/finops-ai-dev/backend:latest \
  -f docker/api/Dockerfile .
docker push $ECR/finops-ai-dev/backend:latest

# Frontend
docker build -t $ECR/finops-ai-dev/frontend:latest \
  -f frontend/Dockerfile.dev frontend/
docker push $ECR/finops-ai-dev/frontend:latest
```

### 5. Update K8s Manifests

Edit the image references in `k8s/*.yaml` to point to your ECR repos:
```
ACCOUNT_ID.dkr.ecr.REGION.amazonaws.com/finops-ai-dev/backend:latest
```

Update `k8s/configmap.yaml` and `k8s/secrets.yaml` with Terraform outputs:
```bash
terraform output rds_endpoint       # → DATABASE_URL host
terraform output redis_endpoint     # → REDIS_HOST / CELERY_BROKER_URL
```

### 6. Apply K8s Manifests

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secrets.yaml
kubectl apply -f k8s/neo4j-statefulset.yaml
kubectl apply -f k8s/backend-deployment.yaml
kubectl apply -f k8s/celery-worker-deployment.yaml
kubectl apply -f k8s/celery-beat-deployment.yaml
kubectl apply -f k8s/frontend-deployment.yaml
kubectl apply -f k8s/ingress.yaml
kubectl apply -f k8s/hpa.yaml
# GPU nodes only:
kubectl apply -f k8s/ollama-deployment.yaml
```

## Directory Structure

```
terraform/
├── main.tf                 # Root — wires all modules
├── variables.tf            # All configurable inputs
├── outputs.tf              # Key infrastructure outputs
├── providers.tf            # AWS provider config
├── deploy.sh               # One-command deploy script
├── environments/
│   ├── dev.tfvars          # Dev: t3.large, db.t3.micro
│   ├── staging.tfvars
│   └── prod.tfvars         # Prod: m6i.large, db.r6g.large, Multi-AZ, GPU
├── modules/
│   ├── networking/         # VPC, subnets, NAT, subnet groups
│   ├── eks/                # EKS cluster, app + GPU node groups, addons
│   ├── iam_base/           # Cluster + node IAM roles (pre-OIDC)
│   ├── iam/                # OIDC provider, IRSA roles (EBS CSI, LB, backend)
│   ├── rds/                # RDS PostgreSQL + SSM secrets
│   ├── elasticache/        # ElastiCache Redis + SSM secrets
│   └── ecr/                # ECR repositories + lifecycle policies
└── k8s/
    ├── namespace.yaml
    ├── configmap.yaml
    ├── secrets.yaml
    ├── backend-deployment.yaml     # FastAPI (2 replicas)
    ├── celery-worker-deployment.yaml
    ├── celery-beat-deployment.yaml
    ├── frontend-deployment.yaml    # React/Vite (2 replicas)
    ├── neo4j-statefulset.yaml      # Graph DB with EBS PVC
    ├── ollama-deployment.yaml      # LLM on GPU (with init model pull)
    ├── ingress.yaml                # ALB Ingress
    └── hpa.yaml                    # Autoscalers for backend/celery/frontend
```

## Environment Sizing

| Component | Dev | Prod |
|-----------|-----|------|
| EKS Nodes | 2× t3.large | 3× m6i.large |
| GPU Nodes | disabled | 1× g5.xlarge |
| RDS       | db.t3.micro, 20GB | db.r6g.large, 100GB, Multi-AZ |
| Redis     | cache.t3.micro | cache.r6g.large, failover |
| AZs       | 2 | 3 |

## Estimated Monthly Cost (Dev)

| Resource | Cost |
|----------|------|
| EKS Control Plane | ~$73 |
| 2× t3.large nodes | ~$120 |
| RDS db.t3.micro | ~$15 |
| ElastiCache cache.t3.micro | ~$12 |
| NAT Gateway | ~$32 |
| ALB | ~$16 |
| **Total** | **~$268/mo** |

## Teardown

```bash
# Delete K8s resources first (releases ALB)
kubectl delete ingress finops-ingress -n finops
kubectl delete namespace finops

# Then destroy infrastructure
cd terraform
terraform destroy -var-file=environments/dev.tfvars
```
