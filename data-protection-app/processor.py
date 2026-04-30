"""
Event Processor (BUGGY VERSION) - Consumes events from RabbitMQ and writes to PostgreSQL

THIS VERSION CONTAINS BUGS THAT CAUSE THE ISSUE:
- Queue length grows but no records appear in database
- No errors are logged
- Service appears to be running normally

The bugs are:
1. Auto-acknowledgment is enabled, so messages are acked before processing
2. Database connection issues cause silent failures
3. Acknowledgment happens BEFORE database commit completes
4. No proper error handling or transaction management
"""

import json
import time
import logging
import psycopg2
from psycopg2 import sql
from psycopg2.extras import Json
import pika

# Configure logging (notice: level is INFO, so DEBUG details are hidden)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
RABBITMQ_HOST = 'localhost'
RABBITMQ_PORT = 5672
RABBITMQ_USER = 'dataprotection'
RABBITMQ_PASS = 'dataprotection'
QUEUE_NAME = 'data_protection_events'

DB_HOST = 'localhost'
DB_PORT = 5432
DB_NAME = 'dataprotection'
DB_USER = 'dataprotection'
DB_PASS = 'dataprotection'

# Global counters (for monitoring)
processed_count = 0
failed_count = 0

def get_db_connection():
    """Create a database connection."""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )

def process_event(event_data):
    """
    Process an event and store it in the database.
    
    BUG: This function has several issues:
    1. Connection is created fresh each time (inefficient, can fail silently)
    2. No proper transaction management
    3. Exceptions are caught but not properly handled
    4. Returns success even when DB operations fail
    """
    global processed_count
    
    try:
        # BUG: Creating new connection for each message
        conn = get_db_connection()
        cur = conn.cursor()
        
        # BUG: No explicit transaction start
        insert_query = sql.SQL("""
            INSERT INTO events (event_type, payload, source_ip, user_id, timestamp, processed)
            VALUES (%s, %s, %s, %s, %s, %s)
        """)
        
        event = json.loads(event_data)
        
        # BUG: Using string concatenation instead of proper parameterization for timestamp
        timestamp = event.get('timestamp', time.strftime('%Y-%m-%d %H:%M:%S'))
        
        cur.execute(insert_query, (
            event.get('event_type', 'unknown'),
            Json(event.get('payload', {})),
            event.get('source_ip'),
            event.get('user_id'),
            timestamp,
            True
        ))
        
        # BUG: Commit might fail but we don't check
        conn.commit()
        
        cur.close()
        conn.close()
        
        processed_count += 1
        
        # BUG: Logging at DEBUG level, which is not visible with INFO config
        logger.debug(f"Successfully processed event {event.get('event_id', 'unknown')}")
        
        return True
        
    except Exception as e:
        # BUG: Catching all exceptions but only logging at DEBUG level
        # This makes it look like "no errors in logs"
        logger.debug(f"Error processing event: {str(e)}")
        
        # BUG: Returning True even on failure, so message gets acknowledged
        return True

def callback(ch, method, properties, body):
    """
    Message callback handler.
    
    BUG: This is the main source of the problem:
    - The channel is configured with auto_ack=True (see below)
    - Messages are acknowledged BEFORE processing completes
    - If processing fails, the message is already lost
    """
    global failed_count
    
    # BUG: Processing happens, but acknowledgment was already done by pika
    # because auto_ack=True is set in basic_consume
    success = process_event(body)
    
    if not success:
        failed_count += 1
        # BUG: Even if processing fails, we can't nack because auto_ack
        # The message is already gone from the queue

def main():
    """Main consumer loop."""
    logger.info(f"Starting event processor, connecting to RabbitMQ at {RABBITMQ_HOST}:{RABBITMQ_PORT}")
    
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
    parameters = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PORT,
        credentials=credentials,
        heartbeat=600,
        blocked_connection_timeout=300
    )
    
    try:
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        
        # Declare queue
        channel.queue_declare(queue=QUEUE_NAME, durable=True)
        
        # BUG: auto_ack=True means messages are acknowledged immediately
        # upon delivery, BEFORE the callback processes them
        # This is the ROOT CAUSE of the issue
        channel.basic_consume(
            queue=QUEUE_NAME,
            on_message_callback=callback,
            auto_ack=True  # <-- THIS IS THE BUG!
        )
        
        logger.info(f"[*] Waiting for messages from queue '{QUEUE_NAME}'. To exit press CTRL+C")
        channel.start_consuming()
        
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")
    except Exception as e:
        # BUG: Connection errors are logged but service keeps "running"
        # appearing healthy while doing nothing useful
        logger.error(f"Fatal error: {str(e)}")
        logger.info("Service is still running but may not be processing messages")
        
        # BUG: Keep the process alive even after fatal error
        # This makes it look like the service is running
        while True:
            time.sleep(60)
            logger.info("Service heartbeat - still alive (but not processing)")

if __name__ == '__main__':
    main()
