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
            'request_method': message_dict.get('request_method'),
            'request_path': message_dict.get('request_path'),
            'request_query': json.dumps(message_dict.get('request_query', {})),  # Convert to string
            'request_body': json.dumps(message_dict.get('request_body')) if message_dict.get('request_body') else None,
            'response_summary': json.dumps(message_dict.get('response_body')) if message_dict.get('response_body') else None,
            'status_code': message_dict.get('status_code'),
            'duration': message_dict.get('duration'),
            'client_ip': message_dict.get('client_ip'),
            'user_agent': message_dict.get('user_agent')
        }
        print(f"Log Record 100: {log_record}")
        
        # Add hostname or other common fields
        log_record['hostname'] = socket.gethostname()
        
        return json.dumps(log_record)