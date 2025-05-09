import os
import json
import uuid
import base64
import datetime
from typing import Dict, Any, Optional
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, File, UploadFile, Form
from pydantic import BaseModel
from google.cloud import pubsub_v1
from dotenv import load_dotenv
from google.cloud import storage


# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI(title="Pub/Sub Service")
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

# Initialize GCS client
storage_client = storage.Client()
bucket_name = "compartment_images"  # Replace with your bucket name
bucket = storage_client.bucket(bucket_name)

# Environment variables
PROJECT_ID = os.getenv("PROJECT_ID", "proj-qsight-asmlab")
SUBSCRIPTION_TOPIC = os.getenv("SUBSCRIPTION_TOPIC", "projects/proj-qsight-asmlab/topics/trigger-capture-sub")
PUBLISHING_TOPIC = os.getenv("PUBLISHING_TOPIC", "projects/proj-qsight-asmlab/topics/trigger-capture")
SUBSCRIPTION_ID = os.getenv("SUBSCRIPTION_ID", "receive-image-sub")

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
async def publish(
    message: Optional[str] = Form(None),
    attributes: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None)
):
    """
    Publish a message or image reference to the Pub/Sub topic
    """
    try:
        # Handle attributes if provided
        attr_dict = {}
        if attributes:
            try:
                # Only try to parse if attributes is not None or empty
                if attributes.strip():
                    attr_dict = json.loads(attributes)
            except json.JSONDecodeError:
                # If JSON parsing fails, log it but continue with empty attributes
                print(f"Warning: Invalid JSON in attributes: {attributes}")
        
        # Check if this is a file upload
        if file:
            # Generate a unique filename
            file_extension = file.filename.split('.')[-1] if '.' in file.filename else ''
            unique_filename = f"{uuid.uuid4()}.{file_extension}"
            
            # Read file content
            content = await file.read()
            
            # Upload to GCS
            blob = bucket.blob(unique_filename)
            blob.upload_from_string(
                content,
                content_type=file.content_type
            )
            
            # Generate a signed URL (valid for 1 hour)
            signed_url = blob.generate_signed_url(
                version="v4",
                expiration=datetime.timedelta(hours=1),
                method="GET"
            )
            
            # Create a message with the file metadata and signed URL
            message_data = {
                "filename": file.filename,
                "content_type": file.content_type,
                "storage_path": f"gs://{bucket_name}/{unique_filename}",
                "signed_url": signed_url,
                "url_expiry": (datetime.datetime.now() + datetime.timedelta(hours=1)).isoformat()
            }
            
            # Add file metadata to the message attributes
            attr_dict["content_type"] = "application/json"
            attr_dict["message_type"] = "file_reference"
            
            # Encode the message as JSON
            data = json.dumps(message_data).encode("utf-8")
            
        elif message:
            # Encode text message
            data = message.encode("utf-8")
        else:
            raise HTTPException(status_code=400, detail="Either message or file must be provided")
        
        # Publish message to Pub/Sub
        future = publisher.publish(
            publishing_topic_path, 
            data=data,
            **attr_dict
        )
        
        # Get the message ID
        message_id = future.result()
        
        return {"success": True, "message_id": message_id}
    except Exception as e:
        # Include more debugging information in the error
        import traceback
        error_details = traceback.format_exc()
        print(f"Error details: {error_details}")
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