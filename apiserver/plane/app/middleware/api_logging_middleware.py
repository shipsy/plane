import time
import logging
import json
from django.utils import timezone
from django.conf import settings
from plane.utils.logging_handler import setup_api_logging
OPENSEARCH_APPLOG_INDEX = getattr(settings, 'OPENSEARCH_APPLOG_INDEX', 'logs')
class APILoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        # We'll initialize the logger after creating the logging setup
        self.logger = setup_api_logging(logging.getLogger('plane.app'), OPENSEARCH_APPLOG_INDEX)
        # self.logger.handlers[0].flush()
    def __call__(self, request):
        start_time = time.time()
        request_body = None
        if request.body:
            try:
                request_body = json.loads(request.body)
            except:
                request_body = request.body.decode('utf-8', errors='replace')
        
        # Initialize error fields as None
        error_message = None
        error_reason = None
        try:
            # Process the request and get the response
            response = self.get_response(request)
            # Extract response data - only for error responses
            response_data = None
            if response.status_code >= 400:
                try:
                    if hasattr(response, 'data'):
                        response_data = response.data
                    elif hasattr(response, 'content'):
                        content = response.content
                        if content:
                            try:
                                response_data = json.loads(content)
                            except:
                                response_data = content.decode('utf-8', errors='replace')
                except Exception as e:
                    print(f"Error extracting response data: {e}")
                    response_data = "Error extracting response data"
                # Set error message and reason for error responses
                error_message = str(response_data) if response_data else f"HTTP {response.status_code}"
                error_reason = f"HTTP Error {response.status_code}"
            else:
                # For successful responses, just set a simple message
                response_data = "API request successful"
                print("response))datada",response_data)
            
            status_code = response.status_code
        except Exception as e:
            # Capture exceptions that occur during processing
            error_message = str(e)
            error_reason = e.__class__.__name__
            status_code = 500
            response_data = {"error": str(e)}
            # Create a response for the exception
            from django.http import JsonResponse
            response = JsonResponse({"error": str(e)}, status=500)
            
        duration = time.time() - start_time
        
        # Only log API requests and protect logging with try-except
        if request.path.startswith('/api/'):
            try:
                username = 'anonymous'
                if hasattr(request, 'user') and request.user.is_authenticated:
                    username = request.user.username
                    
                log_data = {
                    'timestamp': timezone.now().isoformat(),
                    'username': username,
                    'request_method': request.method,
                    'url': request.path,
                    'query': dict(request.GET),
                    'body': request_body,
                    'response': response_data,
                    'status_code': getattr(response, 'status_code', status_code),  # More explicit fallback
                    'duration': round(duration * 1000, 2),
                    'client_ip': self._get_client_ip(request),
                    'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                }
                
                if error_message:
                    log_data['error'] = {
                        'message': error_message,
                        'reason': error_reason
                    }
                    
                try:
                    self.logger.info(json.dumps(log_data, default=str))
                except Exception as logging_error:
                    print(f"Error during logging: {logging_error}")
                    # Logging error shouldn't affect API response
            except Exception as log_prep_error:
                print(f"Error preparing log data: {log_prep_error}")
                # Error in log preparation shouldn't affect API response
                
        return response

    
    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip