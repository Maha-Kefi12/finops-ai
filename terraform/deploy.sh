#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# FinOps AI — EKS Deployment Script
# Usage: ./deploy.sh <environment>   (dev | staging | prod)
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail

ENV="${1:-dev}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TFVARS="$SCRIPT_DIR/environments/${ENV}.tfvars"

if [[ ! -f "$TFVARS" ]]; then
  echo "ERROR: $TFVARS not found. Use: dev, staging, or prod"
  exit 1
fi

echo "═══════════════════════════════════════════════════════════"
echo " FinOps AI — Deploying to: $ENV"
echo "═══════════════════════════════════════════════════════════"

# ── Step 1: Terraform ──────────────────────────────────────────────────
echo ""
echo "▶ Step 1/5: Terraform init + apply"
cd "$SCRIPT_DIR"
terraform init -upgrade
terraform plan -var-file="$TFVARS" -out=tfplan
echo ""
read -p "Apply this plan? (y/N) " confirm
if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
  echo "Aborted."
  exit 0
fi
terraform apply tfplan

# ── Step 2: Configure kubectl ──────────────────────────────────────────
echo ""
echo "▶ Step 2/5: Configure kubectl"
CLUSTER_NAME=$(terraform output -raw eks_cluster_name)
AWS_REGION=$(terraform output -raw aws_region 2>/dev/null || grep 'aws_region' "$TFVARS" | awk -F'"' '{print $2}')
aws eks update-kubeconfig --region "$AWS_REGION" --name "$CLUSTER_NAME"
echo "kubectl configured for $CLUSTER_NAME"

# ── Step 3: Build & push container images ──────────────────────────────
echo ""
echo "▶ Step 3/5: Build and push Docker images to ECR"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REGISTRY="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY"

BACKEND_REPO="${ECR_REGISTRY}/finops-ai-${ENV}/backend"
FRONTEND_REPO="${ECR_REGISTRY}/finops-ai-${ENV}/frontend"

echo "  Building backend..."
docker build -t "$BACKEND_REPO:latest" -f "$PROJECT_ROOT/docker/api/Dockerfile" "$PROJECT_ROOT"
docker push "$BACKEND_REPO:latest"

echo "  Building frontend..."
docker build -t "$FRONTEND_REPO:latest" -f "$PROJECT_ROOT/frontend/Dockerfile.dev" "$PROJECT_ROOT/frontend"
docker push "$FRONTEND_REPO:latest"

# ── Step 4: Patch K8s manifests with real values ───────────────────────
echo ""
echo "▶ Step 4/5: Patch K8s manifests with Terraform outputs"
RDS_ENDPOINT=$(terraform output -raw rds_endpoint)
REDIS_ENDPOINT=$(terraform output -raw redis_endpoint)
RDS_PASSWORD=$(terraform output -raw rds_password 2>/dev/null || echo "CHECK_SSM")
BACKEND_ROLE_ARN=$(terraform output -raw backend_role_arn 2>/dev/null || echo "")

K8S_DIR="$SCRIPT_DIR/k8s"
TMP_DIR=$(mktemp -d)
cp "$K8S_DIR"/*.yaml "$TMP_DIR/"

# Patch image references
sed -i "s|ACCOUNT_ID.dkr.ecr.REGION.amazonaws.com/finops-ai-dev/backend|${BACKEND_REPO}|g" "$TMP_DIR"/*.yaml
sed -i "s|ACCOUNT_ID.dkr.ecr.REGION.amazonaws.com/finops-ai-dev/frontend|${FRONTEND_REPO}|g" "$TMP_DIR"/*.yaml

# Patch configmap values
sed -i "s|REPLACE_WITH_TERRAFORM_OUTPUT|placeholder|g" "$TMP_DIR/configmap.yaml"
cat > "$TMP_DIR/configmap-patch.yaml" <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: finops-config
  namespace: finops
data:
  ENVIRONMENT: "${ENV}"
  PYTHONPATH: "/app"
  DATA_DIR: "/app/data/synthetic"
  REDIS_HOST: "${REDIS_ENDPOINT%%:*}"
  REDIS_PORT: "6379"
  CELERY_BROKER_URL: "redis://${REDIS_ENDPOINT%%:*}:6379/1"
  CELERY_RESULT_BACKEND: "redis://${REDIS_ENDPOINT%%:*}:6379/2"
  NEO4J_URI: "bolt://neo4j:7687"
  NEO4J_USER: "neo4j"
  OLLAMA_URL: "http://ollama:11434"
  FINOPS_MODEL: "qwen2.5:7b"
  DATABASE_URL: "postgresql://finops:${RDS_PASSWORD}@${RDS_ENDPOINT}/finops_db"
EOF

# Patch secrets
cat > "$TMP_DIR/secrets-patch.yaml" <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: finops-secrets
  namespace: finops
type: Opaque
stringData:
  DATABASE_URL: "postgresql://finops:${RDS_PASSWORD}@${RDS_ENDPOINT}/finops_db"
  NEO4J_PASSWORD: "finops_neo4j"
EOF

# Patch service account annotation
if [[ -n "$BACKEND_ROLE_ARN" ]]; then
  sed -i "s|REPLACE_WITH_BACKEND_ROLE_ARN|${BACKEND_ROLE_ARN}|g" "$TMP_DIR"/*.yaml
fi

# ── Step 5: Apply K8s manifests ────────────────────────────────────────
echo ""
echo "▶ Step 5/5: Apply Kubernetes manifests"
kubectl apply -f "$TMP_DIR/namespace.yaml"
kubectl apply -f "$TMP_DIR/configmap-patch.yaml"
kubectl apply -f "$TMP_DIR/secrets-patch.yaml"
kubectl apply -f "$TMP_DIR/neo4j-statefulset.yaml"
kubectl apply -f "$TMP_DIR/backend-deployment.yaml"
kubectl apply -f "$TMP_DIR/celery-worker-deployment.yaml"
kubectl apply -f "$TMP_DIR/celery-beat-deployment.yaml"
kubectl apply -f "$TMP_DIR/frontend-deployment.yaml"
kubectl apply -f "$TMP_DIR/ingress.yaml"
kubectl apply -f "$TMP_DIR/hpa.yaml"

# Ollama — only if GPU nodes enabled
if grep -q 'enable_gpu_nodes.*=.*true' "$TFVARS" 2>/dev/null; then
  echo "  Deploying Ollama (GPU)..."
  kubectl apply -f "$TMP_DIR/ollama-deployment.yaml"
else
  echo "  Skipping Ollama GPU deployment (enable_gpu_nodes=false)"
  echo "  To run Ollama on CPU, uncomment the CPU section in ollama-deployment.yaml"
fi

rm -rf "$TMP_DIR"

echo ""
echo "═══════════════════════════════════════════════════════════"
echo " Deployment complete!"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo " Cluster: $CLUSTER_NAME"
echo " Region:  $AWS_REGION"
echo ""
echo " Useful commands:"
echo "   kubectl get pods -n finops"
echo "   kubectl logs -n finops deployment/backend -f"
echo "   kubectl get ingress -n finops"
echo ""
echo " Get the ALB URL:"
echo "   kubectl get ingress finops-ingress -n finops -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'"
echo ""
