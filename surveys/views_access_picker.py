"""
Access picker search endpoint for the survey-sharing UI.
Returns matching users and groups in a single response.

GET /api/surveys/access-picker/search/?q=<query>
"""

from django.db.models import Q
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

ADMIN_ROLES = ('admin', 'manager', 'super_admin')


class AccessPickerSearchView(APIView):
    """Search for users and groups to share a survey with."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        role = getattr(request.user, 'role', None)
        if role not in ADMIN_ROLES:
            return Response({'error': 'forbidden'}, status=403)

        q = request.query_params.get('q', '').strip()

        from django.contrib.auth import get_user_model
        from authentication.models import Group

        User = get_user_model()

        if q:
            user_qs = User.objects.filter(
                Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q)
            )
            group_qs = Group.objects.filter(name__icontains=q)
        else:
            user_qs = User.objects.all()
            group_qs = Group.objects.all()

        users = user_qs.exclude(id=request.user.id).values('id', 'email', 'first_name', 'last_name', 'role')[:20]
        groups = group_qs[:20]

        users_data = [
            {
                'id': u['id'],
                'email': u['email'],
                'full_name': f"{u['first_name']} {u['last_name']}".strip() or u['email'],
                'type': 'user',
            }
            for u in users
        ]
        groups_data = []
        for g in groups:
            member_count = getattr(g, 'member_count', None)
            if member_count is None:
                member_count = g.user_groups.count()
            groups_data.append({
                'id': g.id,
                'name': g.name,
                'member_count': member_count,
                'type': 'group',
            })

        return Response({'users': users_data, 'groups': groups_data})
