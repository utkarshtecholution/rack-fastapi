# FastAPI Pub/Sub Application

This is a FastAPI application that subscribes to a Google Cloud Pub/Sub topic and provides an API to publish messages to another topic. It's designed to be deployed on Google Cloud Run.

## Features

- Subscribes to a Pub/Sub topic (`projects/proj-qsight-asmlab/topics/dummy-topic`)
- REST API to publish messages to another Pub/Sub topic
- `/hello` endpoint to publish a simple "Hello, World!" message
- Automatically creates subscriptions on startup
- Handles push messages via a webhook endpoint
- Containerized for deployment to Google Cloud Run

## Prerequisites

- Google Cloud Platform account
- `gcloud` CLI installed and configured
- Docker installed (for local testing)
- Python 3.8+ (for local development)

## Local Development

1. Install dependencies:

   ```
   pip install -r requirements.txt
   ```

2. Set environment variables:

   ```
   export PROJECT_ID="proj-qsight-asmlab"
   export SUBSCRIPTION_TOPIC="projects/proj-qsight-asmlab/topics/dummy-topic"
   export PUBLISHING_TOPIC="projects/proj-qsight-asmlab/topics/dummy-topic-output"
   export SUBSCRIPTION_ID="fastapi-subscription"
   ```

3. Run the application:

   ```
   python main.py
   ```

4. The API will be available at http://localhost:8080

## Deployment to Cloud Run

1. Make the deployment script executable:

   ```
   chmod +x deploy.sh
   ```

2. Run the deployment script:

   ```
   ./deploy.sh
   ```

3. The script will:
   - Build a container image
   - Deploy to Cloud Run
   - Set up necessary service accounts and permissions
   - Display the service URL

## API Endpoints

- `GET /` - Health check endpoint
- `POST /publish` - Publish a custom message to the output topic
  ```json
  {
    "message": "Your message here",
    "attributes": {
      "key1": "value1",
      "key2": "value2"
    }
  }
  ```
- `POST /hello` - Publish a "Hello, World!" message
- `POST /webhook` - Webhook endpoint for Pub/Sub push subscriptions

## Environment Variables

- `PROJECT_ID` - Google Cloud project ID
- `SUBSCRIPTION_TOPIC` - Topic to subscribe to
- `PUBLISHING_TOPIC` - Topic to publish messages to
- `SUBSCRIPTION_ID` - Subscription ID
- `PORT` - Port for the web server (default: 8080)

## Troubleshooting

- Ensure the service account has the necessary permissions (Pub/Sub Subscriber and Publisher roles)
- Check Cloud Run logs for any startup or runtime errors
- Verify that the Pub/Sub topics exist
