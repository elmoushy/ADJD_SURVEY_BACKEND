"""
URL Configuration for Email Communication System
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'email_communication'

router = DefaultRouter()
router.register(r'cost-centers', views.CostCenterViewSet, basename='costcenter')
router.register(r'templates', views.EmailTemplateViewSet, basename='emailtemplate')
router.register(r'drafts', views.EmailDraftViewSet, basename='emaildraft')

urlpatterns = [
    # Router URLs
    path('', include(router.urls)),
    
    # Email sending
    path('send/', views.SendEmailView.as_view(), name='send-email'),
    path('send-draft/<int:draft_id>/', views.SendDraftView.as_view(), name='send-draft'),
    
    # Inbox
    path('inbox/', views.InboxView.as_view(), name='inbox-list'),
    path('inbox/<int:pk>/', views.InboxDetailView.as_view(), name='inbox-detail'),
    path('inbox/<int:pk>/mark-read/', views.MarkEmailReadView.as_view(), name='inbox-mark-read'),
    path('inbox/<int:pk>/star/', views.ToggleStarView.as_view(), name='inbox-toggle-star'),
    path('inbox/<int:pk>/archive/', views.ToggleArchiveView.as_view(), name='inbox-toggle-archive'),
    
    # Outbox
    path('outbox/', views.OutboxView.as_view(), name='outbox-list'),
    path('outbox/<int:pk>/', views.OutboxDetailView.as_view(), name='outbox-detail'),
    
    # Transactions log
    path('transactions/', views.TransactionsView.as_view(), name='transactions-list'),
]
