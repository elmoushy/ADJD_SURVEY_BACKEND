"""
URL configuration for adjd_survey project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from django.conf import settings


def api_root(request):
    """
    API root endpoint providing information about available endpoints.
    """
    return JsonResponse({
        'message': 'ADJD Survey Backend API',
        'version': '1.0.0',
        'authentication': 'Azure AD JWT',
        'endpoints': {
            'authentication': '/api/auth/',
            'surveys': '/api/surveys/',
            'notifications': '/api/notifications/',
            'email': '/api/email/',
            'admin': '/admin/',
            'api_docs': '/api/' if settings.DEBUG else None,
        },
        'status': 'online'
    })


urlpatterns = [
    # Admin interface
    path('admin/', admin.site.urls),
    
    # API root
    path('api/', api_root, name='api-root'),
    
    # Authentication endpoints
    path('api/auth/', include('authentication.urls')),
    
    # Survey service endpoints
    path('api/surveys/', include('surveys.urls')),
    
    # Notifications endpoints
    path('api/notifications/', include('notifications.urls')),
    
    # Email Communication System endpoints
    path('api/email/', include('email_communication.urls')),
    
    # Add your other app URLs here
    # path('api/weapons/', include('weapons.urls')),
    # path('api/inventory/', include('inventory.urls')),
]

# Note: API docs disabled due to coreapi compatibility issues with Python 3.13
# You can use the DRF browsable API by visiting the endpoints directly
