import logging
import json
import socket
class APILogStandardFormatter(logging.Formatter):
    def format(self, record):
        message = record.getMessage()
        print(f"Log Record 100: {message}")
        try:
            # Parse the JSON string into a dict
            message_dict = json.loads(message)
        except:
            # Fallback for non-JSON messages
            return message
        
        # Create a standardized structure
        log_record = {
            'timestamp': message_dict.get('timestamp'),
            'request_id': message_dict.get('request_id'),
            'username': message_dict.get('username'),
            'method': message_dict.get('method'),
            'url': message_dict.get('url'),
            'query': json.dumps(message_dict.get('query', {})),  # Convert to string
            'body': json.dumps(message_dict.get('body')) if message_dict.get('body') else None,
            'response': json.dumps(message_dict.get('response')) if message_dict.get('response') else None,
            'status_code': message_dict.get('status_code'),
            'duration': message_dict.get('duration'),
            'client_ip': message_dict.get('client_ip'),
            'user_agent': message_dict.get('user_agent')
        }
        if 'error' in message_dict:
            log_record['error'] = message_dict.get('error')
        print(f"Log Record 100: {log_record}")
        
        # Add hostname or other common fields
        log_record['hostname'] = socket.gethostname()
        
        return json.dumps(log_record)