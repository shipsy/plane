# your_logging_module.py
import os
import logging
import boto3
import json
import threading
import time
import queue
from django.conf import settings
from opensearchpy import OpenSearch, helpers
from botocore.config import Config
from logging.handlers import MemoryHandler
from plane.utils.formatters import APILogStandardFormatter
from opensearchpy import RequestsHttpConnection
from requests_aws4auth import AWS4Auth

#Global Settings 
OPENSEARCH_PUSH_METHOD = getattr(settings, 'OPENSEARCH_PUSH_METHOD', 'opensearch')

# OpenSearch settings from Django settings
OPENSEARCH_HOST = getattr(settings, 'OPENSEARCH_HOST', 'opensearch-node1')  # Updated to use container name
OPENSEARCH_PORT = getattr(settings, 'OPENSEARCH_PORT', 9200)
OPENSEARCH_SCHEME = getattr(settings, 'OPENSEARCH_SCHEME', 'http')
OPENSEARCH_USERNAME = getattr(settings, 'OPENSEARCH_USERNAME', '')  # Updated credentials
OPENSEARCH_PASSWORD = getattr(settings, 'OPENSEARCH_PASSWORD', '')  # Updated credentials

OPENSEARCH_AUTH_METHOD = getattr(settings, 'OPENSEARCH_AUTH_METHOD', 'basic')

APP_LOGS_CAPACITY = getattr(settings, 'APP_LOGS_CAPACITY', 5)  # Keep your increased capacity
OPENSEARCH_APPLOG_INDEX = getattr(settings, 'OPENSEARCH_APPLOG_INDEX', 'logs')

#Firehose Settings 
FIREHOSE_REGION_NAME = getattr(settings, 'FIREHOSE_REGION_NAME', 'ap-south-1')
FIREHOSE_ACCESS_KEY_ID = getattr(settings, 'FIREHOSE_ACCESS_KEY_ID', '')
FIREHOSE_SECRET_ACCESS_KEY = getattr(settings, 'FIREHOSE_SECRET_ACCESS_KEY', '')

FIREHOSE_RETRY_COUNT = getattr(settings, 'FIREHOSE_RETRY_COUNT', 3)
FIREHOSE_RETRY_DELAY = getattr(settings, 'FIREHOSE_RETRY_DELAY', 1)

# Queue for log processing
log_routing = {}

def log_routing_insert(actions, index_name):
    if index_name not in log_routing:
        log_routing[index_name] = queue.Queue()
    log_routing[index_name].put(actions)

class FireHoseHandler(logging.Handler):

    def __init__(self, stream_name):
        super().__init__()
        # Initialize the Kinesis Firehose instance
        self.region_name = FIREHOSE_REGION_NAME
        self.aws_access_key_id = FIREHOSE_ACCESS_KEY_ID
        self.aws_secret_access_key = FIREHOSE_SECRET_ACCESS_KEY
        self.stream_name = stream_name
        self.client = self._connected_client()

        # Batch and retry configs for Kinesis Firehose
        self.retry_count = int(FIREHOSE_RETRY_COUNT)
        self.retry_delay = int(FIREHOSE_RETRY_DELAY)  #In seconds

    def _connected_client(self):
        return boto3.client(
            "firehose",
            region_name=self.region_name,
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
            config=Config(
                connect_timeout=10,
                read_timeout=10,
            )
        )

    def bulk_insert(self, actions):
        '''
            Function to insert records in bulk into Firehose stream 

            Max batch size supported by put_records_batch is 500
            Each record in the request can be as large as 1,000 KB (before base64 encoding), up to a limit of 4 MB for the entire request

            Firehose Stream Names = Opensearch Index Names 

        '''

        failed_records = []

        if not actions:
            return
        
        records = actions

        #Pushing logs to Firehose with retry
        for attempt in range(self.retry_count):
            try:
                response = self.client.put_record_batch(
                    DeliveryStreamName=self.stream_name,
                    Records=records
                )
                failed_count = response["FailedPutCount"]
                if failed_count == 0:
                    # All records were successfully sent
                    print(f"[DEBUG] Pushed {len(records)} log records to Firehose Stream.")
                    actions.clear()
                    return
                # Some records failed, retry only the failed ones
                failed_records = [
                    records[i]
                    for i, record in enumerate(response["RequestResponses"])
                    if "ErrorCode" in record
                ]
                records = failed_records
                print(f"[ERROR] Pushing to Firehose Stream failed for {len(failed_records)} records.")

            except Exception as e:
                print(f"[ERROR] Failed to bulk insert logs to Firehose: {str(e)}")
                if attempt < self.retry_count - 1:
                    time.sleep(self.retry_delay)
                else:
                    # If we've exhausted all retries, clear the batch to prevent backlog
                    actions.clear()
    
class OpensearchHandler(logging.Handler):
    def __init__(self, index_name='plane-api-logs'):
        super().__init__()
        
        opensearch_params = {
            'hosts': [{'host': OPENSEARCH_HOST, 'port': OPENSEARCH_PORT, 'scheme': OPENSEARCH_SCHEME}],
            'http_compress': True
        }
        if OPENSEARCH_AUTH_METHOD == 'iam':
            aws_auth = AWS4Auth(
                FIREHOSE_ACCESS_KEY_ID,
                FIREHOSE_SECRET_ACCESS_KEY,
                FIREHOSE_REGION_NAME,
                'es'
            )
            opensearch_params['http_auth'] = aws_auth
            opensearch_params['connection_class'] = RequestsHttpConnection
        elif OPENSEARCH_USERNAME and OPENSEARCH_PASSWORD:
            opensearch_params['http_auth'] = (OPENSEARCH_USERNAME, OPENSEARCH_PASSWORD)

        if OPENSEARCH_SCHEME == 'https':
            opensearch_params['use_ssl'] = True
            opensearch_params['verify_certs'] = True
        
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

    def firehose_insert(self, actions):
        log_routing_insert(actions, self.index_name)

class OpensearchMemoryHandler(MemoryHandler):
    def __init__(self, capacity, target_handler, index_name):
        super().__init__(capacity=capacity, target=target_handler)
        self.index_name = index_name
    
    def flush(self):
        self.acquire()
        try:
            if self.target :
                print(f"[DEBUG] Processing {len(self.buffer)} log records for {self.index_name}.")
                actions = []
                for record in self.buffer:
                    log_entry = self.format(record)
                    print(f"[DEBUG] Log entry: {log_entry}")
                    if isinstance(log_entry, dict):
                        log_entry = json.dumps(log_entry)

                    if OPENSEARCH_PUSH_METHOD == 'firehose':
                        action = {
                            "Data": log_entry.encode('utf-8')
                        }
                    else:
                        action = {
                            "_index": self.index_name,
                            "_source": json.loads(log_entry)
                        }

                    actions.append(action)
                
                if actions:
                    if OPENSEARCH_PUSH_METHOD == 'firehose':
                        self.target.firehose_insert(actions)
                    else:
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
        for index_name, log_queue in list(log_routing.items()):
            try:
                queue_size = log_queue.qsize()
                if not log_queue.empty():
                    print("Processing log queue for", index_name)
                    print(f"Queue length for {index_name}: {log_queue.qsize()}")
                    actions = log_queue.get()
                    if OPENSEARCH_PUSH_METHOD == "opensearch":  # OpenSearch
                        # Insert to OpenSearch
                        try:
                            opensearch_client = OpensearchHandler(index_name=index_name)
                            helpers.bulk(opensearch_client.opensearch, actions)
                            print("Flushed logs to OpenSearch")
                        except Exception as e:
                            print(f"[ERROR] Failed to insert log into OpenSearch for {index_name}: {e}")

                    elif OPENSEARCH_PUSH_METHOD == 'firehose':  # Kinesis
                        # Insert to Kinesis
                        try:
                            firehose_handler = FireHoseHandler(stream_name=index_name)
                            firehose_handler.bulk_insert(actions)
                        except Exception as e:
                            print(f"[ERROR] Failed to insert log into Kinesis for {index_name}: {e}")
                    log_queue.task_done()
                    print(f"Queue length after processing for {index_name}: {log_queue.qsize()}")
            except Exception as e:
                print(f"[ERROR] Error processing log queue for {index_name}: {e}")
        time.sleep(1)  # Sleep to prevent CPU hogging
# Start the worker thread
worker_thread = threading.Thread(target=log_worker, daemon=True)
worker_thread.start()


# Global handlers to ensure that the same handler is used across the application
global_opensearch_handler = OpensearchHandler(index_name=OPENSEARCH_APPLOG_INDEX)
global_memory_handler = OpensearchMemoryHandler(capacity=APP_LOGS_CAPACITY, target_handler=global_opensearch_handler, index_name=OPENSEARCH_APPLOG_INDEX)

# Setup function to initialize logging
def setup_api_logging(logger, index_name):
    
    if index_name == OPENSEARCH_APPLOG_INDEX:
        opensearch_handler = global_opensearch_handler
        memory_handler = global_memory_handler
    else:
        opensearch_handler = OpensearchHandler(index_name=index_name)
        memory_handler = OpensearchMemoryHandler(capacity=APP_LOGS_CAPACITY, target_handler=opensearch_handler, index_name=index_name)

    memory_handler.setTarget(opensearch_handler)
    # Set formatters
    api_formatter = APILogStandardFormatter()
    opensearch_handler.setFormatter(api_formatter)
    memory_handler.setFormatter(api_formatter)
    
    # Add handler to logger
    logger.addHandler(memory_handler)
    logger.setLevel(logging.DEBUG)
    return logger