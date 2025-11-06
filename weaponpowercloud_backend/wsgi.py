"""
WSGI config for weaponpowercloud_backend project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

# CRITICAL: Apply Oracle compatibility fixes BEFORE Django loads
# This must happen before get_wsgi_application() is called
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'weaponpowercloud_backend.settings')

# Apply Oracle driver compatibility patches for Python 3.12
try:
    from weaponpowercloud_backend.oracle_fix import apply_oracle_fixes
    apply_oracle_fixes()
except Exception as e:
    import logging
    logging.warning(f"Could not apply Oracle fixes in wsgi.py: {e}")

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
