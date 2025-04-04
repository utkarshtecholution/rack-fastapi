import os
import json
import base64
from typing import Dict, Any, Optional
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from google.cloud import pubsub_v1
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI(title="Pub/Sub Service")

# Environment variables
PROJECT_ID = os.getenv("PROJECT_ID", "proj-qsight-asmlab")
SUBSCRIPTION_TOPIC = os.getenv("SUBSCRIPTION_TOPIC", "projects/proj-qsight-asmlab/topics/dummy-topic")
PUBLISHING_TOPIC = os.getenv("PUBLISHING_TOPIC", "projects/proj-qsight-asmlab/topics/dummy-topic-output")
SUBSCRIPTION_ID = os.getenv("SUBSCRIPTION_ID", "fastapi-subscription")

# Initialize Pub/Sub clients
publisher = pubsub_v1.PublisherClient()
subscriber = pubsub_v1.SubscriberClient()

# Create a fully qualified subscription path
subscription_path = subscriber.subscription_path(PROJECT_ID, SUBSCRIPTION_ID)

# Create publishing topic path
publishing_topic_path = publisher.topic_path(PROJECT_ID, PUBLISHING_TOPIC.split('/')[-1])

class PublishMessage(BaseModel):
    message: str
    attributes: Optional[Dict[str, str]] = None

@app.on_event("startup")
async def startup_event():
    """
    Create subscription if it doesn't exist on startup
    """
    try:
        # Check if subscription exists, if not create it
        try:
            subscriber.get_subscription(subscription=subscription_path)
            print(f"Subscription {SUBSCRIPTION_ID} already exists.")
        except Exception:
            # Create subscription
            subscription_topic_path = SUBSCRIPTION_TOPIC
            # Fix the topic format - make sure it's the full path
            if not subscription_topic_path.startswith("projects/"):
                subscription_topic_path = f"projects/{PROJECT_ID}/topics/{subscription_topic_path.split('/')[-1]}"
                
            subscriber.create_subscription(
                request={"name": subscription_path, "topic": subscription_topic_path}
            )
            print(f"Subscription {SUBSCRIPTION_ID} created for topic {SUBSCRIPTION_TOPIC}")
    except Exception as e:
        print(f"Error setting up subscription: {e}. The application will continue but may not receive messages properly.")

@app.on_event("shutdown")
async def shutdown_event():
    """
    Close Pub/Sub clients on shutdown
    """
    subscriber.close()
    publisher.close()

def handle_message(message):
    """
    Process incoming Pub/Sub message
    """
    try:
        data = base64.b64decode(message.data).decode("utf-8")
        print(f"Received message: {data}")
        message.ack()
        return {"success": True, "message": data}
    except Exception as e:
        print(f"Error processing message: {e}")
        message.nack()
        return {"success": False, "error": str(e)}

# This function is replaced by start_subscriber_thread

@app.post("/publish")
async def publish(message_data: PublishMessage):
    """
    Publish a message to the Pub/Sub topic
    """
    try:
        # Encode message data
        data = message_data.message.encode("utf-8")
        
        # Publish message
        future = publisher.publish(
            publishing_topic_path, 
            data=data,
            **message_data.attributes if message_data.attributes else {}
        )
        
        # Get the message ID
        message_id = future.result()
        
        return {"success": True, "message_id": message_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to publish message: {str(e)}")

@app.post("/hello")
async def hello_world():
    """
    Publish a hello world message to the Pub/Sub topic
    """
    try:
        # Create hello message
        message = "Hello, World!"
        data = message.encode("utf-8")
        
        # Publish message
        future = publisher.publish(
            publishing_topic_path, 
            data=data,
            origin="fastapi-app",
            type="greeting"
        )
        
        # Get the message ID
        message_id = future.result()
        
        return {"success": True, "message": message, "message_id": message_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to publish hello message: {str(e)}")

@app.post("/webhook", status_code=200)
async def pubsub_push(request: Request, background_tasks: BackgroundTasks):
    """
    Webhook endpoint for Pub/Sub push subscriptions
    """
    # Get the message data
    request_json = await request.json()
    message = request_json.get("message", {})
    
    if not message:
        raise HTTPException(status_code=400, detail="Invalid Pub/Sub message format")
    
    # Process the message
    try:
        data = base64.b64decode(message.get("data", "")).decode("utf-8")
        attributes = message.get("attributes", {})
        message_id = message.get("messageId")
        
        print(f"Received message {message_id}: {data}")
        print(f"Attributes: {attributes}")
        
        # Process the message in the background
        # Here you could add your business logic
        
        return {"success": True, "messageId": message_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing message: {str(e)}")

@app.get("/")
async def root():
    """
    Root endpoint to check if the API is running
    """
    return {"status": "healthy", "service": "Pub/Sub Service"}

@app.on_event("startup")
async def start_background_tasks():
    """
    Start background tasks when the app starts
    """
    # Create a separate thread for the subscriber
    import threading
    threading.Thread(target=start_subscriber_thread, daemon=True).start()

def start_subscriber_thread():
    """
    Start the Pub/Sub subscriber in a separate thread
    """
    try:
        # Create a callback for handling messages
        def callback(message):
            handle_message(message)
        
        # Subscribe to the topic
        future = subscriber.subscribe(subscription_path, callback)
        print(f"Listening for messages on {subscription_path}")
        
        # Block the thread and wait for messages
        future.result()
    except Exception as e:
        print(f"Subscriber error: {e}")

if __name__ == "__main__":
    import uvicorn
    
    # Default port for Cloud Run
    port = int(os.getenv("PORT", "8080"))
    
    # Start the application
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)