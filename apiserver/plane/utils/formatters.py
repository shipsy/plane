import logging
import json
import socket
class APILogStandardFormatter(logging.Formatter):
    def format(self, record):
        try:
            message = record.getMessage()
            
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
                'method': message_dict.get('request_method'),  # Changed from 'method' to match middleware
                'url': message_dict.get('url'),
                'query': json.dumps(message_dict.get('query', {})) if message_dict.get('query') else "{}",
                'body': json.dumps(message_dict.get('body')) if message_dict.get('body') else None,
                'status_code': message_dict.get('status_code'),
                'duration': message_dict.get('duration'),
                'client_ip': message_dict.get('client_ip'),
                'user_agent': message_dict.get('user_agent')
            }
            
            # Only include full response for error cases
            if message_dict.get('status_code', 0) >= 400:
                log_record['response'] = json.dumps(message_dict.get('response')) if message_dict.get('response') else None
            else:
                log_record['response'] = message_dict.get('response')  # This will be the simple success message
            
            if 'error' in message_dict:
                log_record['error'] = message_dict.get('error')
            
            # Add hostname or other common fields
            try:
                log_record['hostname'] = socket.gethostname()
            except:
                log_record['hostname'] = 'unknown'
            
            return json.dumps(log_record, default=str)  # Added default=str to handle non-serializable objects
            
        except Exception as formatter_error:
            # If formatting fails, return a simple string to avoid breaking the logging chain
            return f"Formatter error: {str(formatter_error)}. Original message: {record.getMessage()}"