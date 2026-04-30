"""
Event Producer - Generates data protection events and publishes to RabbitMQ

This simulates a system generating data protection events (access logs, 
policy violations, data transfers, etc.) that should be processed and stored.
"""

import json
import os
import time
import random
import uuid
from datetime import datetime, timedelta
import pika

# Configuration
RABBITMQ_HOST = os.environ.get('RABBITMQ_HOST', 'localhost')
RABBITMQ_PORT = int(os.environ.get('RABBITMQ_PORT', '5672'))
RABBITMQ_USER = 'dataprotection'
RABBITMQ_PASS = 'dataprotection'
QUEUE_NAME = 'data_protection_events'

EVENT_TYPES = [
    'file_access',
    'data_export',
    'policy_violation',
    'user_login',
    'permission_change',
    'data_deletion',
    'gdpr_request',
    'audit_log'
]

def generate_event():
    """Generate a random data protection event."""
    event_type = random.choice(EVENT_TYPES)
    
    event = {
        'event_id': str(uuid.uuid4()),
        'event_type': event_type,
        'timestamp': datetime.utcnow().isoformat(),
        'source_ip': f"192.168.{random.randint(1, 255)}.{random.randint(1, 255)}",
        'user_id': f"user_{random.randint(1000, 9999)}",
        'payload': {
            'action': random.choice(['read', 'write', 'delete', 'export', 'modify']),
            'resource': f"/data/{random.choice(['documents', 'users', 'settings', 'logs'])}/{random.randint(1, 1000)}",
            'status': random.choice(['success', 'success', 'success', 'failure']),
            'metadata': {
                'session_id': str(uuid.uuid4())[:8],
                'user_agent': 'Mozilla/5.0',
                'location': random.choice(['US', 'EU', 'APAC', 'LATAM'])
            }
        }
    }
    
    return event

def main():
    """Main producer loop."""
    print(f"[*] Connecting to RabbitMQ at {RABBITMQ_HOST}:{RABBITMQ_PORT}")
    
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
    parameters = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PORT,
        credentials=credentials,
        heartbeat=600,
        blocked_connection_timeout=300
    )
    
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()
    
    # Declare queue (durable to survive broker restarts)
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    
    print(f"[*] Publishing events to queue '{QUEUE_NAME}'")
    print("[*] Press Ctrl+C to stop")
    
    count = 0
    start_time = time.time()
    
    try:
        while True:
            event = generate_event()
            message = json.dumps(event)
            
            # Publish with delivery_mode=2 for persistence
            channel.basic_publish(
                exchange='',
                routing_key=QUEUE_NAME,
                body=message,
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Make message persistent
                    content_type='application/json',
                    timestamp=int(time.time())
                )
            )
            
            count += 1
            
            if count % 10 == 0:
                elapsed = time.time() - start_time
                rate = count / elapsed if elapsed > 0 else 0
                print(f"[*] Published {count} events ({rate:.2f} events/sec)")
            
            # Simulate realistic event generation rate
            time.sleep(random.uniform(0.05, 0.2))
            
    except KeyboardInterrupt:
        print(f"\n[*] Stopping producer. Total events published: {count}")
    finally:
        connection.close()

if __name__ == '__main__':
    main()
