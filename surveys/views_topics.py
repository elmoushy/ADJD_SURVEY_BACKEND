"""
Views for survey topics ("مواضيع") — the folders that group related surveys.

Follows the conventions used by the rest of the surveys app: uniform_response
envelopes, module-level logger, defensive try/except with logged errors, and
Oracle-safe query construction.

Oracle notes that shaped this module:
- Per-topic counters are built from correlated scalar Subqueries, never
  annotate(Count(join)). A JOIN + Count() forces a GROUP BY over every selected
  column; for admins the survey queryset selects the NCLOB-backed encrypted
  title/description columns and Oracle rejects GROUP BY on LOBs
  (ORA-00932 / ORA-00979). The same reasoning is documented in
  views.SurveyViewSet._apply_custom_ordering for the 'most_responses' sort.
- Stacked Counts over different joins would also multiply rows and return wrong
  numbers; independent scalar subqueries cannot.
- Subtree rollups use path__startswith, i.e. LIKE 'prefix%', which can use
  topic_path_idx (no leading wildcard).
"""

import logging
import uuid as uuid_lib

from django.db import transaction
from django.db.models import Count, IntegerField, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from .models import Survey, SurveyTopic, Response as SurveyResponse
from .pagination import TopicPagination
from .permissions import CanManageTopics
from .serializers import (
    SurveyTopicSerializer,
    SurveyTopicTreeSerializer,
    TopicSurveyNodeSerializer,
)
from .views import uniform_response, can_user_manage_survey, safe_get_query_params

logger = logging.getLogger(__name__)

# Hard caps so a pathological forest can never hang the canvas or the DB
TREE_NODE_LIMIT = 500
NODES_SURVEY_LIMIT = 200
MAX_BULK_SURVEYS = 500


def _live_surveys():
    """Every survey that has not been soft deleted."""
    return Survey.objects.filter(deleted_at__isnull=True)


def _scalar_count(queryset, group_field):
    """
    Wrap a queryset as a correlated scalar COUNT subquery.

    `group_field` is the column the inner query groups by (the correlation key),
    which keeps the outer query free of any GROUP BY.
    """
    inner = (
        queryset.order_by()
        .values(group_field)
        .annotate(c=Count('id'))
        .values('c')[:1]
    )
    return Coalesce(Subquery(inner, output_field=IntegerField()), 0)


def annotate_topic_counters(queryset):
    """
    Attach the direct (non-recursive) counters to a SurveyTopic queryset.

      survey_count         direct live surveys
      active_survey_count  direct live surveys that are submitted + active
      response_count       responses to direct live surveys
      children_count       direct live child topics

    Each counter is a correlated scalar subquery whose inner query groups by the
    correlation column, so exactly one row can come back per outer topic and the
    outer query keeps a completely empty GROUP BY clause.

    Subtree rollups are NOT done here — see attach_subtree_counts() for why.
    """
    direct = _live_surveys().filter(topic=OuterRef('pk'))

    return queryset.annotate(
        survey_count=_scalar_count(direct, 'topic'),
        active_survey_count=_scalar_count(
            direct.filter(is_active=True, status='submitted'), 'topic'
        ),
        response_count=_scalar_count(
            SurveyResponse.objects.filter(
                survey__topic=OuterRef('pk'),
                survey__deleted_at__isnull=True,
            ),
            'survey__topic',
        ),
        children_count=_scalar_count(
            SurveyTopic.objects.filter(parent=OuterRef('pk'), deleted_at__isnull=True),
            'parent',
        ),
    )


def attach_subtree_counts(topics):
    """
    Set total_survey_count / total_response_count on already-materialized topics.

    A correlated subtree aggregate would need a GROUP BY on a constant (portable
    across backends only by accident) or a self-join that multiplies rows. Instead
    we run two flat aggregates grouped by topic path — no LOB column is selected,
    so both are Oracle-safe — and roll them up in Python. The path map has one
    entry per topic that actually owns surveys (tens to hundreds), so this is two
    extra queries total, regardless of page size.
    """
    topics = list(topics)
    if not topics:
        return topics

    survey_counts = {
        row['topic__path']: row['c']
        for row in _live_surveys().filter(topic__isnull=False)
        .values('topic__path').annotate(c=Count('id'))
        if row['topic__path']
    }
    response_counts = {
        row['survey__topic__path']: row['c']
        for row in SurveyResponse.objects.filter(
            survey__deleted_at__isnull=True, survey__topic__isnull=False
        ).values('survey__topic__path').annotate(c=Count('id'))
        if row['survey__topic__path']
    }

    for topic in topics:
        prefix = f"{topic.path}."
        topic.total_survey_count = sum(
            count for path, count in survey_counts.items()
            if path == topic.path or path.startswith(prefix)
        )
        topic.total_response_count = sum(
            count for path, count in response_counts.items()
            if path == topic.path or path.startswith(prefix)
        )
    return topics


def topic_subtree_counts(topic):
    """
    Exact subtree rollups for one topic (used by the topic detail KPIs).

    Done as three plain aggregates instead of annotations because the values are
    scalars for a single topic — cheaper and impossible to get wrong.
    """
    subtree_surveys = _live_surveys().filter(topic__path__startswith=topic.path)
    total = subtree_surveys.count()
    active = subtree_surveys.filter(is_active=True, status='submitted').count()
    drafts = subtree_surveys.filter(status='draft').count()
    responses = SurveyResponse.objects.filter(
        survey__topic__path__startswith=topic.path,
        survey__deleted_at__isnull=True,
    ).count()
    return {
        'total_surveys': total,
        'active_surveys': active,
        'draft_surveys': drafts,
        'total_responses': responses,
    }


def _is_valid_uuid(value):
    try:
        uuid_lib.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


class SurveyTopicViewSet(ModelViewSet):
    """
    CRUD + navigation endpoints for survey topics.

    GET    /api/surveys/topics/                 list (paginated cards)
    POST   /api/surveys/topics/                 create                 (admin+)
    GET    /api/surveys/topics/{id}/            detail + breadcrumb + children + KPIs
    PATCH  /api/surveys/topics/{id}/            update / move / pin    (admin+)
    DELETE /api/surveys/topics/{id}/            soft delete            (super_admin)
    POST   /api/surveys/topics/{id}/archive/    archive / unarchive    (admin+)
    GET    /api/surveys/topics/tree/            flat forest for tree + map views
    GET    /api/surveys/topics/{id}/nodes/      lazy children + survey nodes (map)
    POST   /api/surveys/topics/assign/          bulk assign surveys    (admin+)
    POST   /api/surveys/topics/{id}/detach/     bulk remove surveys    (admin+)
    GET    /api/surveys/topics/palette/         allowed colours + icons
    """

    queryset = SurveyTopic.objects.filter(deleted_at__isnull=True)
    serializer_class = SurveyTopicSerializer
    permission_classes = [IsAuthenticated, CanManageTopics]
    pagination_class = TopicPagination

    SORT_MAP = {
        'name_asc': ['name'],
        'name_desc': ['-name'],
        'newest': ['-created_at'],
        'oldest': ['created_at'],
        'most_surveys': ['-survey_count', '-created_at'],
        'most_responses': ['-response_count', '-created_at'],
    }

    # ── Querysets ────────────────────────────────────────────────────────────
    def get_queryset(self):
        queryset = SurveyTopic.objects.filter(deleted_at__isnull=True).select_related('parent', 'created_by')
        queryset = annotate_topic_counters(queryset)

        if self.action != 'list':
            return queryset

        request = self.request

        # search: name/description are plaintext columns, so this stays in SQL
        # (unlike survey titles, which are encrypted and must be filtered in Python)
        search = (safe_get_query_params(request, 'search', '') or '').strip()

        # parent: 'root' (default) | 'all' | <uuid>.
        # Searching is a "find it anywhere" action, so an explicit search overrides
        # the default root scope — otherwise a nested topic could never be found.
        parent = safe_get_query_params(request, 'parent', 'root') or 'root'
        if search and parent == 'root':
            parent = 'all'

        if parent == 'root':
            queryset = queryset.filter(parent__isnull=True)
        elif parent != 'all':
            queryset = queryset.filter(parent_id=parent) if _is_valid_uuid(parent) else queryset.none()

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(description__icontains=search)
            )

        # archived: '0' (default) | '1' | 'all'
        archived = safe_get_query_params(request, 'is_archived', '0') or '0'
        if archived == '1':
            queryset = queryset.filter(is_archived=True)
        elif archived != 'all':
            queryset = queryset.filter(is_archived=False)

        if (safe_get_query_params(request, 'only_mine', '') or '') in ('1', 'true'):
            queryset = queryset.filter(created_by=request.user)

        sort_by = safe_get_query_params(request, 'sort_by', 'name_asc') or 'name_asc'
        ordering = self.SORT_MAP.get(sort_by, self.SORT_MAP['name_asc'])
        # Pinned topics always float to the top of whatever sort is active
        return queryset.order_by('-is_pinned', *ordering)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        # Breadcrumbs cost one extra query per topic, so only detail views get them
        context['include_breadcrumb'] = self.action in ('retrieve', 'create', 'update', 'partial_update')
        return context

    # ── CRUD ─────────────────────────────────────────────────────────────────
    def list(self, request, *args, **kwargs):
        try:
            queryset = self.get_queryset()
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(attach_subtree_counts(page), many=True)
                response = self.get_paginated_response(serializer.data)
                if hasattr(response, 'data') and isinstance(response.data, dict):
                    response.data['applied_filters'] = {
                        'search': safe_get_query_params(request, 'search', ''),
                        'parent': safe_get_query_params(request, 'parent', 'root'),
                        'sort_by': safe_get_query_params(request, 'sort_by', 'name_asc'),
                        'is_archived': safe_get_query_params(request, 'is_archived', '0'),
                        'only_mine': safe_get_query_params(request, 'only_mine', ''),
                    }
                return response

            serializer = self.get_serializer(attach_subtree_counts(queryset), many=True)
            return uniform_response(
                success=True,
                message="Topics retrieved successfully",
                data={'results': serializer.data},
            )
        except Exception as e:
            logger.error(f"Error listing survey topics: {e}")
            return uniform_response(
                success=False,
                message="Failed to retrieve topics",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def retrieve(self, request, *args, **kwargs):
        try:
            topic = self.get_object()
            attach_subtree_counts([topic])
            serializer = self.get_serializer(topic)

            children = attach_subtree_counts(annotate_topic_counters(
                SurveyTopic.objects.filter(parent=topic, deleted_at__isnull=True)
                .select_related('parent', 'created_by')
            ).order_by('-is_pinned', 'display_order', 'name'))

            return uniform_response(
                success=True,
                message="Topic retrieved successfully",
                data={
                    'topic': serializer.data,
                    'children': SurveyTopicSerializer(
                        children, many=True, context={**self.get_serializer_context(),
                                                      'include_breadcrumb': False}
                    ).data,
                    'kpis': topic_subtree_counts(topic),
                },
            )
        except Exception as e:
            logger.error(f"Error retrieving topic {kwargs.get('pk')}: {e}")
            return uniform_response(
                success=False,
                message="Topic not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

    def create(self, request, *args, **kwargs):
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            topic = serializer.save(created_by=request.user)
            logger.info(f"Topic '{topic.name}' ({topic.id}) created by {request.user.email}")

            # Re-read through the annotated queryset so counters are present
            topic = self.get_queryset().filter(pk=topic.pk).first() or topic
            attach_subtree_counts([topic])
            return uniform_response(
                success=True,
                message="Topic created successfully",
                data=self.get_serializer(topic).data,
                status_code=status.HTTP_201_CREATED,
            )
        except Exception as e:
            logger.error(f"Error creating topic: {e}")
            return uniform_response(
                success=False,
                message=self._error_message(e, "Failed to create topic"),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

    def update(self, request, *args, **kwargs):
        try:
            topic = self.get_object()
            serializer = self.get_serializer(topic, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            with transaction.atomic():
                topic = serializer.save()
            logger.info(f"Topic {topic.id} updated by {request.user.email}")

            topic = self.get_queryset().filter(pk=topic.pk).first() or topic
            attach_subtree_counts([topic])
            return uniform_response(
                success=True,
                message="Topic updated successfully",
                data=self.get_serializer(topic).data,
            )
        except Exception as e:
            logger.error(f"Error updating topic {kwargs.get('pk')}: {e}")
            return uniform_response(
                success=False,
                message=self._error_message(e, "Failed to update topic"),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """
        Soft delete a topic (super admin only).

        Surveys are detached, never deleted; child topics are re-parented.
        """
        try:
            if getattr(request.user, 'role', None) != 'super_admin':
                return uniform_response(
                    success=False,
                    message="Only super administrators can delete topics. You can archive it instead.",
                    status_code=status.HTTP_403_FORBIDDEN,
                )

            topic = self.get_object()
            detached = topic.surveys.count()
            children = topic.children.count()
            topic.soft_delete()

            logger.info(
                f"Topic {topic.id} soft-deleted by {request.user.email}: "
                f"{detached} survey(s) detached, {children} child topic(s) re-parented"
            )
            return uniform_response(
                success=True,
                message="Topic deleted successfully",
                data={'detached_surveys': detached, 'reparented_children': children},
            )
        except Exception as e:
            logger.error(f"Error deleting topic {kwargs.get('pk')}: {e}")
            return uniform_response(
                success=False,
                message="Failed to delete topic",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # ── Extra actions ────────────────────────────────────────────────────────
    @action(detail=True, methods=['post'], url_path='archive')
    def archive(self, request, pk=None):
        """Archive / unarchive a topic. POST {"is_archived": true|false}"""
        try:
            topic = self.get_object()
            is_archived = request.data.get('is_archived', True)
            if isinstance(is_archived, str):
                is_archived = is_archived.lower() in ('1', 'true', 'yes')

            topic.is_archived = bool(is_archived)
            topic.save(update_fields=['is_archived'])
            logger.info(
                f"Topic {topic.id} {'archived' if topic.is_archived else 'unarchived'} "
                f"by {request.user.email}"
            )
            return uniform_response(
                success=True,
                message="Topic archived successfully" if topic.is_archived
                        else "Topic restored successfully",
                data={'id': str(topic.id), 'is_archived': topic.is_archived},
            )
        except Exception as e:
            logger.error(f"Error archiving topic {pk}: {e}")
            return uniform_response(
                success=False,
                message="Failed to archive topic",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=['get'], url_path='tree')
    def tree(self, request):
        """
        Flat forest for the tree + map views.

        Returns at most TREE_NODE_LIMIT nodes; `truncated` tells the UI to fall back
        to the (paginated) grid instead of silently showing a partial forest.
        """
        try:
            include_archived = (safe_get_query_params(request, 'include_archived', '') or '') in ('1', 'true')
            queryset = SurveyTopic.objects.filter(deleted_at__isnull=True)
            if not include_archived:
                queryset = queryset.filter(is_archived=False)

            total = queryset.count()
            queryset = annotate_topic_counters(queryset).order_by('depth', '-is_pinned', 'display_order', 'name')
            nodes = attach_subtree_counts(list(queryset[:TREE_NODE_LIMIT]))

            ungrouped = _live_surveys().filter(topic__isnull=True).count()

            return uniform_response(
                success=True,
                message="Topic tree retrieved successfully",
                data={
                    'results': SurveyTopicTreeSerializer(nodes, many=True).data,
                    'total': total,
                    'truncated': total > TREE_NODE_LIMIT,
                    'limit': TREE_NODE_LIMIT,
                    'ungrouped_survey_count': ungrouped,
                },
            )
        except Exception as e:
            logger.error(f"Error building topic tree: {e}")
            return uniform_response(
                success=False,
                message="Failed to build topic tree",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=['get'], url_path='nodes')
    def nodes(self, request, pk=None):
        """
        Lazy expansion for the map: this topic's child topics + its surveys as light
        nodes. Keeps the canvas O(visible) rather than O(all surveys).
        """
        try:
            topic = self.get_object()

            children = attach_subtree_counts(annotate_topic_counters(
                SurveyTopic.objects.filter(parent=topic, deleted_at__isnull=True)
            ).order_by('-is_pinned', 'display_order', 'name'))

            surveys_qs = self._visible_surveys_for(request.user).filter(topic=topic)
            total_surveys = surveys_qs.count()
            surveys_qs = surveys_qs.annotate(
                response_count=_scalar_count(
                    SurveyResponse.objects.filter(survey=OuterRef('pk')), 'survey'
                )
            ).order_by('-created_at')[:NODES_SURVEY_LIMIT]

            return uniform_response(
                success=True,
                message="Topic nodes retrieved successfully",
                data={
                    'topic_id': str(topic.id),
                    'children': SurveyTopicTreeSerializer(children, many=True).data,
                    'surveys': TopicSurveyNodeSerializer(
                        surveys_qs, many=True, context={'request': request}
                    ).data,
                    'survey_total': total_surveys,
                    'truncated': total_surveys > NODES_SURVEY_LIMIT,
                },
            )
        except Exception as e:
            logger.error(f"Error loading nodes for topic {pk}: {e}")
            return uniform_response(
                success=False,
                message="Failed to load topic nodes",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=['post'], url_path='assign')
    def assign(self, request):
        """
        Bulk assign surveys to a topic (or clear it with topic_id = null).

        POST { "topic_id": "<uuid>" | null, "survey_ids": ["<uuid>", ...] }
        """
        topic_id = request.data.get('topic_id')
        survey_ids = request.data.get('survey_ids') or []
        return self._move_surveys(request, topic_id, survey_ids)

    @action(detail=True, methods=['post'], url_path='detach')
    def detach(self, request, pk=None):
        """
        Remove surveys from this topic — they become "ungrouped", never deleted.

        POST { "survey_ids": ["<uuid>", ...] }
        """
        try:
            topic = self.get_object()
        except Exception:
            return uniform_response(
                success=False, message="Topic not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        survey_ids = request.data.get('survey_ids') or []
        return self._move_surveys(request, None, survey_ids, restrict_to_topic=topic)

    @action(detail=False, methods=['get'], url_path='palette',
            permission_classes=[IsAuthenticated])
    def palette(self, request):
        """Colours + icons the server will accept, so the UI never offers a rejected value."""
        return uniform_response(
            success=True,
            message="Palette retrieved successfully",
            data={
                'colors': SurveyTopic.ALLOWED_COLORS,
                'icons': SurveyTopic.ALLOWED_ICONS,
                'max_depth': SurveyTopic.MAX_DEPTH,
            },
        )

    # ── Internals ────────────────────────────────────────────────────────────
    def _visible_surveys_for(self, user):
        """
        Surveys the given user may see, mirroring SurveyViewSet.get_queryset().

        Only used for the map's light survey nodes; the real survey lists keep going
        through SurveyViewSet so the visibility rules live in exactly one place.
        """
        base = _live_surveys()
        role = getattr(user, 'role', None)
        if role in ('super_admin', 'admin', 'manager'):
            return base
        user_groups = user.user_groups.values_list('group', flat=True)
        return base.filter(
            Q(creator=user)
            | (Q(shared_with=user) & Q(status='submitted'))
            | (Q(shared_with_groups__in=user_groups) & Q(status='submitted'))
            | (Q(visibility='PUBLIC') & Q(status='submitted'))
            | (Q(visibility='AUTH') & Q(status='submitted'))
        ).distinct()

    def _move_surveys(self, request, topic_id, survey_ids, restrict_to_topic=None):
        """
        Shared implementation for assign + detach.

        - authorization is per survey via can_user_manage_survey()
        - the write is a single UPDATE, deliberately NOT survey.save(): save()
          re-encrypts title/description and recomputes title_hash, which is both
          wasteful and risky for a metadata-only change. updated_at is set
          explicitly because auto_now only fires on save().
        """
        try:
            if getattr(request.user, 'role', None) not in ('admin', 'super_admin'):
                return uniform_response(
                    success=False,
                    message="Only administrators or super administrators can organize surveys into topics",
                    status_code=status.HTTP_403_FORBIDDEN,
                )

            if not isinstance(survey_ids, list) or not survey_ids:
                return uniform_response(
                    success=False,
                    message="survey_ids is required",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            if len(survey_ids) > MAX_BULK_SURVEYS:
                return uniform_response(
                    success=False,
                    message=f"Cannot move more than {MAX_BULK_SURVEYS} surveys in one request",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            clean_ids = [sid for sid in survey_ids if _is_valid_uuid(sid)]
            invalid = len(survey_ids) - len(clean_ids)

            topic = None
            if topic_id:
                if not _is_valid_uuid(topic_id):
                    return uniform_response(
                        success=False, message="Invalid topic id",
                        status_code=status.HTTP_400_BAD_REQUEST,
                    )
                topic = SurveyTopic.objects.filter(pk=topic_id, deleted_at__isnull=True).first()
                if topic is None:
                    return uniform_response(
                        success=False, message="Topic not found",
                        status_code=status.HTTP_404_NOT_FOUND,
                    )
                if topic.is_archived:
                    return uniform_response(
                        success=False,
                        message="This topic is archived and cannot receive new surveys",
                        status_code=status.HTTP_400_BAD_REQUEST,
                    )

            surveys = _live_surveys().filter(id__in=clean_ids)
            if restrict_to_topic is not None:
                surveys = surveys.filter(topic=restrict_to_topic)

            # Only the encrypted-free columns are needed for the permission check
            surveys = surveys.only('id', 'creator', 'topic')

            allowed_ids, skipped = [], 0
            previous = {}
            for survey in surveys:
                if can_user_manage_survey(request.user, survey):
                    allowed_ids.append(survey.id)
                    previous[str(survey.id)] = str(survey.topic_id) if survey.topic_id else None
                else:
                    skipped += 1

            found = len(allowed_ids) + skipped
            missing = len(clean_ids) - found

            assigned = 0
            if allowed_ids:
                with transaction.atomic():
                    assigned = Survey.objects.filter(id__in=allowed_ids).update(
                        topic=topic,
                        updated_at=timezone.now(),
                    )

            errors = []
            if skipped:
                errors.append(f"{skipped} survey(s) skipped: you cannot manage them")
            if missing > 0:
                errors.append(f"{missing} survey(s) not found")
            if invalid:
                errors.append(f"{invalid} invalid survey id(s) ignored")

            logger.info(
                f"Topic assign by {request.user.email}: topic={topic.id if topic else None}, "
                f"assigned={assigned}, skipped={skipped}, missing={missing}"
            )

            return uniform_response(
                success=True,
                message="Surveys moved successfully" if topic else "Surveys removed from topic successfully",
                data={
                    'topic_id': str(topic.id) if topic else None,
                    'topic_name': topic.name if topic else None,
                    'assigned': assigned,
                    'skipped': skipped + max(0, missing),
                    'errors': errors,
                    # lets the UI offer a real Undo instead of a guess
                    'previous_topics': previous,
                },
            )
        except Exception as e:
            logger.error(f"Error moving surveys between topics: {e}")
            return uniform_response(
                success=False,
                message="Failed to move surveys",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @staticmethod
    def _error_message(exc, fallback):
        """Surface DRF validation messages, hide anything else behind a fallback."""
        detail = getattr(exc, 'detail', None)
        if detail is None:
            return fallback
        if isinstance(detail, dict):
            for field, messages in detail.items():
                if isinstance(messages, (list, tuple)) and messages:
                    return str(messages[0])
                return str(messages)
        if isinstance(detail, (list, tuple)) and detail:
            return str(detail[0])
        return str(detail)
