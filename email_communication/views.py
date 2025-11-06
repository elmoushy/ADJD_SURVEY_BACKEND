"""
API Views for Email Communication System
"""
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q
from django.shortcuts import get_object_or_404

from .models import (
    CostCenter,
    EmailTemplate,
    EmailDraft,
    EmailLog,
    EmailRecipientView
)
from .serializers import (
    CostCenterListSerializer,
    CostCenterDetailSerializer,
    EmailTemplateListSerializer,
    EmailTemplateDetailSerializer,
    EmailDraftListSerializer,
    EmailDraftDetailSerializer,
    EmailLogListSerializer,
    EmailLogDetailSerializer,
    EmailRecipientViewListSerializer,
    EmailRecipientViewDetailSerializer,
    SendEmailSerializer,
    SendDraftSerializer,
)
from .permissions import (
    CanSendEmail,
    CanManageCostCenters,
    CanCreateTemplates,
    IsDraftOwner,
    CanViewEmailLog,
    IsRecipient
)
from .services import EmailService


class CostCenterViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Cost Centers
    LIST: GET /api/email/cost-centers/
    CREATE: POST /api/email/cost-centers/
    RETRIEVE: GET /api/email/cost-centers/{id}/
    UPDATE: PUT/PATCH /api/email/cost-centers/{id}/
    DELETE: DELETE /api/email/cost-centers/{id}/
    """
    permission_classes = [IsAuthenticated, CanManageCostCenters]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active']
    search_fields = ['cost_center_code', 'cost_center_name', 'cost_center_name_ar']
    ordering_fields = ['cost_center_code', 'created_at']
    ordering = ['cost_center_code']
    
    def get_queryset(self):
        return CostCenter.objects.all()
    
    def get_serializer_class(self):
        if self.action == 'list':
            return CostCenterListSerializer
        return CostCenterDetailSerializer
    
    @action(detail=True, methods=['get'])
    def users(self, request, pk=None):
        """Get users in a cost center"""
        cost_center = self.get_object()
        users = cost_center.users.all()
        from .serializers import UserMinimalSerializer
        serializer = UserMinimalSerializer(users, many=True)
        return Response({
            'cost_center_id': cost_center.id,
            'cost_center_code': cost_center.cost_center_code,
            'users': serializer.data,
            'total_users': users.count()
        })


class EmailTemplateViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Email Templates
    LIST: GET /api/email/templates/
    CREATE: POST /api/email/templates/
    RETRIEVE: GET /api/email/templates/{id}/
    UPDATE: PUT/PATCH /api/email/templates/{id}/
    DELETE: DELETE /api/email/templates/{id}/
    """
    permission_classes = [IsAuthenticated, CanCreateTemplates]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'category']
    search_fields = ['name', 'name_ar', 'subject']
    ordering_fields = ['name', 'created_at']
    ordering = ['-created_at']
    
    def get_queryset(self):
        queryset = EmailTemplate.objects.all()
        # Non-admins see only active templates
        if not (self.request.user.is_superuser or self.request.user.role in ['admin', 'super_admin']):
            queryset = queryset.filter(is_active=True)
        return queryset
    
    def get_serializer_class(self):
        if self.action == 'list':
            return EmailTemplateListSerializer
        return EmailTemplateDetailSerializer


class EmailDraftViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Email Drafts
    LIST: GET /api/email/drafts/
    CREATE: POST /api/email/drafts/
    RETRIEVE: GET /api/email/drafts/{id}/
    UPDATE: PUT/PATCH /api/email/drafts/{id}/
    DELETE: DELETE /api/email/drafts/{id}/
    """
    permission_classes = [IsAuthenticated, IsDraftOwner]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['send_type']
    search_fields = ['subject', 'draft_name']
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['-updated_at']
    
    def get_queryset(self):
        # Users see only their own drafts
        return EmailDraft.objects.for_user(self.request.user)
    
    def get_serializer_class(self):
        if self.action == 'list':
            return EmailDraftListSerializer
        return EmailDraftDetailSerializer
    
    def perform_destroy(self, instance):
        """Soft delete"""
        instance.is_deleted = True
        instance.save()


class SendEmailView(APIView):
    """
    Send email to cost centers
    POST /api/email/send/
    """
    permission_classes = [IsAuthenticated, CanSendEmail]
    
    def post(self, request):
        serializer = SendEmailSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        result = EmailService.send_email(
            user=request.user,
            send_type=serializer.validated_data['send_type'],
            subject=serializer.validated_data['subject'],
            body_html=serializer.validated_data['body_html'],
            cost_center_ids=serializer.validated_data.get('cost_center_ids'),
            template_id=serializer.validated_data.get('template_id')
        )
        
        if result['success']:
            return Response(result, status=status.HTTP_200_OK)
        else:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)


class SendDraftView(APIView):
    """
    Send email from saved draft
    POST /api/email/send-draft/{draft_id}/
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, draft_id):
        serializer = SendDraftSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        result = EmailService.send_from_draft(
            user=request.user,
            draft_id=draft_id,
            overrides=serializer.validated_data
        )
        
        if result['success']:
            return Response(result, status=status.HTTP_200_OK)
        else:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)


class InboxView(APIView):
    """
    Get user's inbox (received emails)
    GET /api/email/inbox/
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        queryset = EmailRecipientView.objects.inbox_for_user(request.user)
        
        # Apply filters
        is_read = request.query_params.get('is_read')
        if is_read is not None:
            queryset = queryset.filter(is_read=is_read.lower() == 'true')
        
        is_starred = request.query_params.get('is_starred')
        if is_starred is not None:
            queryset = queryset.filter(is_starred=is_starred.lower() == 'true')
        
        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(email_log__subject__icontains=search) |
                Q(email_log__body_html__icontains=search)
            )
        
        # Pagination (simple)
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 6))
        start = (page - 1) * page_size
        end = start + page_size
        
        total_count = queryset.count()
        results = queryset[start:end]
        
        serializer = EmailRecipientViewListSerializer(results, many=True)
        return Response({
            'count': total_count,
            'page': page,
            'page_size': page_size,
            'results': serializer.data
        })


class InboxDetailView(APIView):
    """
    Get inbox email detail (automatically marks as read)
    GET /api/email/inbox/{id}/
    """
    permission_classes = [IsAuthenticated, IsRecipient]
    
    def get(self, request, pk):
        recipient_view = get_object_or_404(
            EmailRecipientView,
            pk=pk,
            recipient_user=request.user
        )
        
        # Mark as read
        recipient_view.mark_as_read()
        
        serializer = EmailRecipientViewDetailSerializer(recipient_view)
        return Response(serializer.data)


class OutboxView(APIView):
    """
    Get user's outbox (sent emails)
    GET /api/email/outbox/
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        queryset = EmailLog.objects.sent_by_user(request.user)
        
        # Apply filters
        email_status = request.query_params.get('email_status')
        if email_status:
            queryset = queryset.filter(email_status=email_status)
        
        send_type = request.query_params.get('send_type')
        if send_type:
            queryset = queryset.filter(send_type=send_type)
        
        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(subject__icontains=search) |
                Q(body_html__icontains=search)
            )
        
        # Pagination
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 6))
        start = (page - 1) * page_size
        end = start + page_size
        
        total_count = queryset.count()
        results = queryset[start:end]
        
        serializer = EmailLogListSerializer(results, many=True)
        return Response({
            'count': total_count,
            'page': page,
            'page_size': page_size,
            'results': serializer.data
        })


class OutboxDetailView(APIView):
    """
    Get outbox email detail by ID
    GET /api/email/outbox/{id}/
    """
    permission_classes = [IsAuthenticated, CanViewEmailLog]
    
    def get(self, request, pk):
        email_log = get_object_or_404(
            EmailLog,
            pk=pk,
            user=request.user
        )
        
        serializer = EmailLogDetailSerializer(email_log)
        return Response(serializer.data)


class TransactionsView(APIView):
    """
    Get email transactions log (all email activity)
    GET /api/email/transactions/
    Admins see all, users see only their own
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        # Admins see all, users see only their own
        if request.user.is_superuser or request.user.role in ['admin', 'super_admin']:
            queryset = EmailLog.objects.all()
        else:
            queryset = EmailLog.objects.filter(user=request.user)
        
        # Apply filters
        email_status = request.query_params.get('email_status')
        if email_status:
            queryset = queryset.filter(email_status=email_status)
        
        email_type = request.query_params.get('email_type')
        if email_type:
            queryset = queryset.filter(email_type=email_type)
        
        send_type = request.query_params.get('send_type')
        if send_type:
            queryset = queryset.filter(send_type=send_type)
        
        cost_center_id = request.query_params.get('cost_center_id')
        if cost_center_id:
            queryset = queryset.filter(cost_center_id=cost_center_id)
        
        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(subject__icontains=search) |
                Q(body_html__icontains=search)
            )
        
        # Pagination
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 6))
        start = (page - 1) * page_size
        end = start + page_size
        
        total_count = queryset.count()
        results = queryset[start:end]
        
        serializer = EmailLogListSerializer(results, many=True)
        return Response({
            'count': total_count,
            'page': page,
            'page_size': page_size,
            'results': serializer.data
        })


class MarkEmailReadView(APIView):
    """
    Mark inbox email as read
    POST /api/email/inbox/{id}/mark-read/
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, pk):
        recipient_view = get_object_or_404(
            EmailRecipientView,
            pk=pk,
            recipient_user=request.user
        )
        recipient_view.mark_as_read()
        return Response({'success': True, 'message': 'Email marked as read'})


class ToggleStarView(APIView):
    """
    Toggle star status for inbox email
    POST /api/email/inbox/{id}/star/
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, pk):
        recipient_view = get_object_or_404(
            EmailRecipientView,
            pk=pk,
            recipient_user=request.user
        )
        recipient_view.toggle_starred()
        return Response({
            'success': True,
            'is_starred': recipient_view.is_starred
        })


class ToggleArchiveView(APIView):
    """
    Toggle archive status for inbox email
    POST /api/email/inbox/{id}/archive/
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, pk):
        recipient_view = get_object_or_404(
            EmailRecipientView,
            pk=pk,
            recipient_user=request.user
        )
        recipient_view.toggle_archived()
        return Response({
            'success': True,
            'is_archived': recipient_view.is_archived
        })
