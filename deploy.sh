#!/bin/bash
# deploy.sh
#
# Builds the Docker image, pushes it to Google Artifact Registry,
# and deploys it to Cloud Run — all in one command.
#
# USAGE:
#   chmod +x deploy.sh
#   ./deploy.sh
#
# PREREQUISITES:
#   1. gcloud CLI installed  →  https://cloud.google.com/sdk/docs/install
#   2. Logged in             →  gcloud auth login
#   3. Project set           →  gcloud config set project YOUR_PROJECT_ID
#   4. APIs enabled (script does this automatically)

set -e  # Stop on any error

# ── Configuration — edit these ─────────────────────────────────
PROJECT_ID=$(gcloud config get-value project)
REGION="us-central1"           # Change to your preferred region
SERVICE_NAME="agronet-backend"
IMAGE="gcr.io/$PROJECT_ID/$SERVICE_NAME"

echo "🌱 AgroNet Cloud Run deployment"
echo "   Project : $PROJECT_ID"
echo "   Region  : $REGION"
echo "   Service : $SERVICE_NAME"
echo ""

# ── Enable required APIs ────────────────────────────────────────
echo "→ Enabling Cloud Run and Container Registry APIs..."
gcloud services enable run.googleapis.com containerregistry.googleapis.com --quiet

# ── Build and push the Docker image ────────────────────────────
echo "→ Building Docker image..."
gcloud builds submit --tag "$IMAGE" .

# ── Deploy to Cloud Run ─────────────────────────────────────────
echo "→ Deploying to Cloud Run..."
gcloud run deploy "$SERVICE_NAME" \
  --image "$IMAGE" \
  --platform managed \
  --region "$REGION" \
  --allow-unauthenticated \
  --session-affinity \
  --min-instances 1 \
  --max-instances 3 \
  --memory 512Mi \
  --cpu 1 \
  --timeout 3600 \
  --set-env-vars "FARM_ID=farm-001,FARM_NAME=Field Station Alpha" \
  --set-secrets "ANTHROPIC_API_KEY=agronet-anthropic-key:latest,MQTT_BROKER_HOST=agronet-mqtt-host:latest"

# ── Print the deployed URL ──────────────────────────────────────
URL=$(gcloud run services describe "$SERVICE_NAME" \
  --platform managed \
  --region "$REGION" \
  --format "value(status.url)")

echo ""
echo "✅ Deployed successfully!"
echo "   API URL  : $URL"
echo "   Docs     : $URL/docs"
echo "   Health   : $URL/health"
echo "   WebSocket: wss://$(echo $URL | sed 's|https://||')/ws"
echo ""
echo "Next: set FRONTEND_URL env var to your frontend's domain"
echo "  gcloud run services update $SERVICE_NAME --region $REGION \\"
echo "    --set-env-vars FRONTEND_URL=https://your-frontend-domain.com"
