#!/bin/bash
set -e

# Configuration
PROJECT_ID="proj-qsight-asmlab"
SERVICE_NAME="fastapi-pubsub-service"
REGION="us-central1"  # Change to your preferred region
SUBSCRIPTION_TOPIC="projects/proj-qsight-asmlab/topics/dummy-topic"
PUBLISHING_TOPIC="projects/proj-qsight-asmlab/topics/dummy-topic-output"

# Build the container image
echo "Building container image..."
gcloud builds submit --tag gcr.io/$PROJECT_ID/$SERVICE_NAME

# Deploy to Cloud Run
echo "Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
  --image gcr.io/$PROJECT_ID/$SERVICE_NAME \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --set-env-vars="PROJECT_ID=$PROJECT_ID,SUBSCRIPTION_TOPIC=$SUBSCRIPTION_TOPIC,PUBLISHING_TOPIC=$PUBLISHING_TOPIC" \
  --service-account="$SERVICE_NAME@$PROJECT_ID.iam.gserviceaccount.com"

echo "Creating Pub/Sub service account if it doesn't exist..."
if ! gcloud iam service-accounts describe "$SERVICE_NAME@$PROJECT_ID.iam.gserviceaccount.com" &>/dev/null; then
  gcloud iam service-accounts create $SERVICE_NAME \
    --display-name="Service Account for $SERVICE_NAME"
fi

# Grant permissions to the service account
echo "Granting Pub/Sub subscriber role..."
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_NAME@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/pubsub.subscriber"

echo "Granting Pub/Sub publisher role..."
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_NAME@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/pubsub.publisher"

# Get the URL of the deployed service
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --platform managed --region $REGION --format 'value(status.url)')

echo "Deployment complete!"
echo "Service URL: $SERVICE_URL"
echo ""
echo "You can test the service with:"
echo "curl -X POST $SERVICE_URL/hello"
echo "curl -X POST $SERVICE_URL/publish -H 'Content-Type: application/json' -d '{\"message\":\"Custom message\"}'"