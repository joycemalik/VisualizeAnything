from django.utils.deprecation import MiddlewareMixin
from django.http import JsonResponse
import time
from datetime import datetime, timezone, timedelta


class SessionCleanupMiddleware(MiddlewareMixin):
    """
    Middleware to track session activity (cleanup disabled for manual control)
    """
    
    def process_request(self, request):
        """Track session start time without automatic cleanup"""
        try:
            # Check if session has a start time
            if 'session_start_time' not in request.session:
                request.session['session_start_time'] = time.time()
                request.session.modified = True
            
            # Note: Automatic cleanup has been disabled
            # Users can manually clean session from the home page
                
        except Exception as e:
            print(f"❌ Error in SessionCleanupMiddleware: {e}")
        
        return None
    
    def process_response(self, request, response):
        """Update session activity on each request"""
        try:
            # Update last activity time
            request.session['last_activity'] = time.time()
            request.session.modified = True
            
        except Exception as e:
            print(f"❌ Error updating session activity: {e}")
        
        return response


class SessionExpiryMiddleware(MiddlewareMixin):
    """
    Middleware to handle session expiry detection
    """
    
    def process_request(self, request):
        """Check if session has expired due to inactivity"""
        try:
            from .views import complete_session_cleanup
            
            current_time = time.time()
            last_activity = request.session.get('last_activity')
            
            if last_activity:
                # Check for inactivity timeout (30 minutes)
                inactivity_timeout = 30 * 60  # 30 minutes in seconds
                
                if current_time - last_activity > inactivity_timeout:
                    print(f"💤 Session expired due to inactivity, cleaning up...")
                    complete_session_cleanup(request.session)
                    
        except Exception as e:
            print(f"❌ Error in SessionExpiryMiddleware: {e}")
        
        return None