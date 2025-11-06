"""
Custom pagination classes for the surveys app.
"""

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class SurveyPagination(PageNumberPagination):
    """
    Custom pagination for surveys with configurable page size.
    Default per_page is 10, can be customized via 'per_page' query parameter.
    """
    page_size = 10
    page_size_query_param = 'per_page'
    max_page_size = 100
    
    def get_paginated_response(self, data):
        return Response({
            'status': 'success',
            'message': '',
            'data': {
                'count': self.page.paginator.count,
                'total_pages': self.page.paginator.num_pages,
                'current_page': self.page.number,
                'per_page': self.get_page_size(self.request),
                'next': self.get_next_link(),
                'previous': self.get_previous_link(),
                'results': data,
                'available_filters': {
                    'sort_options': [
                        {'value': 'newest', 'label': 'الأحدث', 'label_en': 'Newest'},
                        {'value': 'oldest', 'label': 'الأقدم', 'label_en': 'Oldest'},
                        {'value': 'title_asc', 'label': 'العنوان أ-ي', 'label_en': 'Title A-Z'},
                        {'value': 'title_desc', 'label': 'العنوان ي-أ', 'label_en': 'Title Z-A'},
                        {'value': 'most_responses', 'label': 'الأكثر رداً', 'label_en': 'Most Responses'}
                    ],
                    'status_options': [
                        {'value': 'all', 'label': 'جميع الاستطلاعات', 'label_en': 'All Surveys'},
                        {'value': 'active', 'label': 'النشطة', 'label_en': 'Active'},
                        {'value': 'inactive', 'label': 'غير النشطة', 'label_en': 'Inactive'},
                        {'value': 'private', 'label': 'الخاصة', 'label_en': 'Private'},
                        {'value': 'auth_required', 'label': 'تتطلب تسجيل دخول', 'label_en': 'Require Login'},
                        {'value': 'public', 'label': 'العامة', 'label_en': 'Public'}
                    ]
                }
            }
        })


class ResponsePagination(PageNumberPagination):
    """
    Custom pagination for survey responses with configurable page size.
    Default per_page is 10, can be customized via 'per_page' query parameter.
    """
    page_size = 10
    page_size_query_param = 'per_page'
    max_page_size = 100
    
    def get_paginated_response(self, data):
        response_data = {
            'status': 'success',
            'message': 'Survey responses retrieved successfully',
            'data': {
                'count': self.page.paginator.count,
                'total_pages': self.page.paginator.num_pages,
                'current_page': self.page.number,
                'per_page': self.get_page_size(self.request),
                'next': self.get_next_link(),
                'previous': self.get_previous_link(),
                'results': data
            }
        }
        
        # Add survey context if available in the view's list method
        return Response(response_data)
