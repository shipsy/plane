import time
import logging
import json
from django.utils import timezone
from plane.utils.logginglogging import setup_api_logging
class APILoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        # We'll initialize the logger after creating the logging setup
        self.logger = setup_api_logging(logging.getLogger('plane.app'), 'plane-api-logs')
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
        error_stack = None
        try:
            # Process the request and get the response
            response = self.get_response(request)

            # Extract response data
            response_data = None
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

            # Check if response indicates an error
            if response.status_code >= 400:
                error_message = str(response_data) if response_data else f"HTTP {response.status_code}"
                print("error message",error_message)
                error_reason = f"HTTP Error {response.status_code}"
                print("error_reason",error_reason)
            
            status_code = response.status_code

        except Exception as e:
            # Capture exceptions that occur during processing
            error_message = str(e)
            error_reason = e.__class__.__name__
            error_stack = traceback.format_exc()
            status_code = 500
            # Create a response for the exception
            from django.http import JsonResponse
            response = JsonResponse({"error": str(e)}, status=500)



        duration = time.time() - start_time

        if request.path.startswith('/api/'):
            username = 'anonymous'
            if hasattr(request, 'user') and request.user.is_authenticated:
                username = request.user.username

            log_data = {
                'timestamp': timezone.now().isoformat(),
                'username': username,
                'request_method': request.method,
                'request_path': request.path,
                'request_query': dict(request.GET),
                'request_body': request_body,
                'response_body': response_data,
                'status_code': response.status_code,
                'duration': round(duration * 1000, 2),
                'client_ip': self._get_client_ip(request),
                'user_agent': request.META.get('HTTP_USER_AGENT', ''),
            }
            if error_message:
                log_data['error'] = {
                    'message': error_message,
                    'reason': error_reason
                }

            print("\n=== API REQUEST LOG ===")
            print(json.dumps(log_data, indent=2, default=str))
            print("======================\n")
            self.logger.info(json.dumps(log_data, default=str))

        return response

    
    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip