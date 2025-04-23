# your_logging_module.py
import os
import logging
import json
import threading
import time
import queue
from django.conf import settings
from opensearchpy import OpenSearch, helpers

# OpenSearch settings from Django settings
OPENSEARCH_HOST = getattr(settings, 'OPENSEARCH_HOST', 'opensearch-node1')  # Updated to use container name
OPENSEARCH_PORT = getattr(settings, 'OPENSEARCH_PORT', 9200)
OPENSEARCH_SCHEME = getattr(settings, 'OPENSEARCH_SCHEME', 'http')
OPENSEARCH_USERNAME = getattr(settings, 'OPENSEARCH_USERNAME', 'admin')  # Updated credentials
OPENSEARCH_PASSWORD = getattr(settings, 'OPENSEARCH_PASSWORD', 'admin')  # Updated credentials
APP_LOGS_CAPACITY = getattr(settings, 'APP_LOGS_CAPACITY', 1)  # Keep your increased capacity
OPENSEARCH_APPLOG_INDEX = getattr(settings, 'OPENSEARCH_APPLOG_INDEX', 'plane-api-logs')

# Queue for log processing
log_routing = {}

def log_routing_insert(actions, index_name):
    if index_name not in log_routing:
        log_routing[index_name] = queue.Queue()
    log_routing[index_name].put(actions)

class OpensearchHandler(logging.Handler):
    def __init__(self, index_name='plane-api-logs'):
        super().__init__()
        
        opensearch_params = {
            'hosts': [{'host': OPENSEARCH_HOST, 'port': OPENSEARCH_PORT, 'scheme': OPENSEARCH_SCHEME}],
            'http_compress': True
        }
        if OPENSEARCH_USERNAME and OPENSEARCH_PASSWORD:
            opensearch_params['http_auth'] = (OPENSEARCH_USERNAME, OPENSEARCH_PASSWORD)
        
        self.opensearch = OpenSearch(**opensearch_params)
        self.index_name = index_name
    
    def emit(self, record):
        # This will be overridden to use bulk processing
        pass
    
    def bulk_insert(self, actions):
        try:
            print(f"[DEBUG] Bulk inserting {len(actions)} log actions to OpenSearch.")
            helpers.bulk(self.opensearch, actions)
            print(f"[DEBUG] Successfully bulk inserted logs to OpenSearch.")
        except Exception as e:
            print(f"[ERROR] Failed to bulk insert logs to OpenSearch: {str(e)}")

class APILogFormatter(logging.Formatter):
    def format(self, record):
        # For API logs, we're already passing in formatted JSON
        # Just return the message which should be pre-formatted
        return record.getMessage()

class OpensearchMemoryHandler(logging.handlers.MemoryHandler):
    def __init__(self, capacity, target_handler, index_name):
        super().__init__(capacity=capacity, target=target_handler)
        self.index_name = index_name
    
    def flush(self):
        self.acquire()
        try:
            if self.target and len(self.buffer) > 0:
                print(f"[DEBUG] Processing {len(self.buffer)} log records for {self.index_name}.")
                actions = []
                for record in self.buffer:
                    log_entry = self.format(record)
                    
                    # Parse the JSON string back to a dict if needed
                    try:
                        if isinstance(log_entry, str):
                            log_entry = json.loads(log_entry)
                    except:
                        # If it's not valid JSON, use it as-is
                        pass
                    
                    action = {
                        "_index": self.index_name,
                        "_source": log_entry
                    }
                    actions.append(action)
                
                if actions:
                    # Instead of immediate processing, send to queue for background worker
                    log_routing_insert(actions, self.index_name)
                    print(f"[DEBUG] Added {len(actions)} log entries to queue for {self.index_name}.")
                
                self.buffer.clear()
                print(f"[DEBUG] Flushed logs to Opensearch. Buffer cleared.")
        finally:
            self.release()

# Add to log_worker function
def log_worker():
    print("[INFO] Log worker thread started")
    while True:
        total_queues = len(log_routing)
        print(f"[DEBUG] Checking {total_queues} log queues")
        for index_name, log_queue in list(log_routing.items()):
            try:
                queue_size = log_queue.qsize()
                print(f"[DEBUG] Queue '{index_name}' size: {queue_size}")
                if not log_queue.empty():
                    print(f"[DEBUG] Processing log queue for {index_name}. Queue size: {queue_size}")
                    actions = log_queue.get()
                    print(f"[DEBUG] Got {len(actions)} actions from queue")
                    opensearch_handler = OpensearchHandler(index_name=index_name)
                    try:
                        opensearch_handler.bulk_insert(actions)
                        print(f"[DEBUG] Successfully sent logs to OpenSearch for {index_name}")
                    except Exception as e:
                        print(f"[ERROR] Failed to insert logs to OpenSearch: {e}")
                        print(f"[ERROR] Exception type: {type(e)}")
                        import traceback
                        traceback.print_exc()
                    log_queue.task_done()
            except Exception as e:
                print(f"[ERROR] Error processing log queue for {index_name}: {e}")
                import traceback
                traceback.print_exc()
        time.sleep(1)  # Sleep to prevent CPU hogging
# Start the worker thread
worker_thread = threading.Thread(target=log_worker, daemon=True)
worker_thread.start()

# Setup function to initialize logging
def setup_api_logging(logger, index_name):
    # Remove any existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create handlers
    opensearch_handler = OpensearchHandler(index_name=index_name)
    memory_handler = OpensearchMemoryHandler(
        capacity=APP_LOGS_CAPACITY,
        target_handler=opensearch_handler,
        index_name=index_name
    )
    
    # Set formatters
    api_formatter = APILogFormatter()
    memory_handler.setFormatter(api_formatter)
    
    # Add handler to logger
    logger.addHandler(memory_handler)
    logger.setLevel(logging.INFO)
    
    # Create index if it doesn't exist
    try:
        if not opensearch_handler.opensearch.indices.exists(index=index_name):
            mapping = {
                "mappings": {
                    "properties": {
                        "timestamp": {"type": "date"},
                        "request_id": {"type": "keyword"},
                        "username": {"type": "keyword"},
                        "request_method": {"type": "keyword"},
                        "request_path": {"type": "keyword"},
                        "request_query": {"type": "object"},
                        "request_body": {"type": "object", "enabled": False},
                        "status_code": {"type": "integer"},
                        "duration": {"type": "float"},
                        "client_ip": {"type": "ip"},
                        "user_agent": {"type": "text"}
                    }
                }
            }
            opensearch_handler.opensearch.indices.create(index=index_name, body=mapping)
    except Exception as e:
        print(f"[WARNING] Could not create index: {e}")
    
    return logger