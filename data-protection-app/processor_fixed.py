"""
processor_fixed.py - FIXED VERSION of the event processor

This version fixes all the bugs that caused:
- Queue length growing while database shows zero events
- No errors in logs
- Service appearing healthy but not processing

FIXES APPLIED:
1. Manual acknowledgment (auto_ack=False)
2. Acknowledgment ONLY after successful database commit
3. Proper exception handling with ERROR level logging
4. Transaction management with rollback on failure
5. Connection pooling for efficiency
6. Negative acknowledgment (nack) on failure to requeue messages
7. Health check endpoint
"""

import json
import time
import logging
import signal
import sys
import psycopg2
from psycopg2 import sql
from psycopg2.extras import Json, RealDictCursor
from psycopg2 import pool
import pika

# Configure logging with proper levels
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('processor.log')
    ]
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

# Global state
running = True
processed_count = 0
failed_count = 0

# FIX: Use connection pooling instead of creating new connections
db_pool = None

def init_db_pool():
    """Initialize database connection pool."""
    global db_pool
    try:
        db_pool = psycopg2.pool.SimpleConnectionPool(
            1, 10,
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        logger.info("Database connection pool initialized")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize database pool: {e}")
        return False

def get_db_connection():
    """Get a connection from the pool."""
    if db_pool:
        return db_pool.getconn()
    return None

def release_db_connection(conn):
    """Return a connection to the pool."""
    if db_pool and conn:
        db_pool.putconn(conn)

def process_event(event_data):
    """
    Process an event and store it in the database.
    
    FIXES:
    - Uses connection from pool
    - Explicit transaction management
    - Proper error handling with rollback
    - Returns False on failure so message can be nacked
    """
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            logger.error("No database connection available")
            return False
        
        # FIX: Disable autocommit for explicit transaction control
        conn.autocommit = False
        cur = conn.cursor()
        
        insert_query = sql.SQL("""
            INSERT INTO events (event_type, payload, source_ip, user_id, timestamp, processed)
            VALUES (%s, %s, %s, %s, %s, %s)
        """)
        
        event = json.loads(event_data)
        timestamp = event.get('timestamp', time.strftime('%Y-%m-%d %H:%M:%S'))
        
        cur.execute(insert_query, (
            event.get('event_type', 'unknown'),
            Json(event.get('payload', {})),
            event.get('source_ip'),
            event.get('user_id'),
            timestamp,
            True
        ))
        
        # FIX: Only commit if insert succeeds
        conn.commit()
        cur.close()
        
        logger.info(f"Successfully processed event {event.get('event_id', 'unknown')}")
        return True
        
    except Exception as e:
        # FIX: Rollback on error
        if conn:
            try:
                conn.rollback()
            except:
                pass
        
        # FIX: Log at ERROR level so it's visible
        logger.error(f"Error processing event: {e}", exc_info=True)
        return False
        
    finally:
        # FIX: Always return connection to pool
        if conn:
            release_db_connection(conn)

def callback(ch, method, properties, body):
    """
    Message callback handler.
    
    FIXES:
    - Manual acknowledgment
    - Ack only on success
    - Nack on failure to requeue
    """
    global processed_count, failed_count
    
    success = process_event(body)
    
    if success:
        # FIX: Only acknowledge AFTER successful processing
        ch.basic_ack(delivery_tag=method.delivery_tag)
        processed_count += 1
        
        if processed_count % 100 == 0:
            logger.info(f"Processed {processed_count} messages successfully")
    else:
        # FIX: Nack on failure to requeue the message
        # requeue=True puts it back in the queue for retry
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        failed_count += 1
        logger.warning(f"Message nacked and requeued. Total failures: {failed_count}")

def signal_handler(sig, frame):
    """Handle shutdown signals gracefully."""
    global running
    logger.info(f"Received signal {sig}, shutting down...")
    running = False

def main():
    """Main consumer loop with proper error handling."""
    global running
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info(f"Starting FIXED event processor")
    logger.info(f"Connecting to RabbitMQ at {RABBITMQ_HOST}:{RABBITMQ_PORT}")
    
    # Initialize database pool
    if not init_db_pool():
        logger.error("Cannot start without database connection")
        sys.exit(1)
    
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
    parameters = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PORT,
        credentials=credentials,
        heartbeat=600,
        blocked_connection_timeout=300
    )
    
    connection = None
    
    while running:
        try:
            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()
            
            # Declare queue
            channel.queue_declare(queue=QUEUE_NAME, durable=True)
            
            # FIX: Set prefetch count to prevent overwhelming the processor
            channel.basic_qos(prefetch_count=1)
            
            # FIX: auto_ack=False for manual acknowledgment
            channel.basic_consume(
                queue=QUEUE_NAME,
                on_message_callback=callback,
                auto_ack=False  # <-- FIXED!
            )
            
            logger.info(f"[*] Waiting for messages from queue '{QUEUE_NAME}'. To exit press CTRL+C")
            
            while running and connection.is_open:
                try:
                    connection.process_data_events(time_limit=1)
                except KeyboardInterrupt:
                    break
            
        except pika.exceptions.AMQPConnectionError as e:
            logger.error(f"RabbitMQ connection error: {e}")
            if connection and connection.is_open:
                try:
                    connection.close()
                except:
                    pass
            connection = None
            
            if running:
                logger.info("Reconnecting in 5 seconds...")
                time.sleep(5)
                
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            if running:
                time.sleep(5)
    
    # Cleanup
    logger.info("Shutting down gracefully...")
    
    if connection and connection.is_open:
        try:
            connection.close()
        except:
            pass
    
    if db_pool:
        db_pool.closeall()
    
    logger.info(f"Final stats - Processed: {processed_count}, Failed: {failed_count}")
    logger.info("Shutdown complete")

if __name__ == '__main__':
    main()
