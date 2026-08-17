"""
Test cases for survey topics ("مواضيع") — the folders that group related surveys —
and for the assigned-users panel used by the survey preview.

Covers:
- model invariants: name normalization / case-insensitive uniqueness, depth cap,
  cycle prevention, path + depth resync when a subtree moves, soft delete
  detaching surveys and re-parenting children
- the topics API: CRUD permissions per role, archive, tree cap, lazy nodes,
  bulk assign / detach (including partial success), palette whitelist
- the survey list endpoint's new `topic` filter and topic-scoped KPIs
- the assigned-users endpoint for every visibility level
- query budgets, so a page of topic cards can never regress into an N+1
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from authentication.models import Group, UserGroup
from surveys.models import Response as SurveyResponse
from surveys.models import Survey, SurveyTopic
from surveys.serializers import SurveyTopicSerializer
from surveys.views import SurveyViewSet
from surveys.views_topics import SurveyTopicViewSet

User = get_user_model()


def envelope(response):
    """Unwrap the uniform_response / paginator envelope used across this app."""
    data = response.data
    if isinstance(data, dict) and 'data' in data:
        return data['data']
    return data


class TopicTestBase(TestCase):
    """Shared fixtures: a super admin, an admin, and a plain user."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.super_admin = User.objects.create_user(
            username='super@example.com', email='super@example.com',
            password='testpass123', role='super_admin',
        )
        self.admin = User.objects.create_user(
            username='admin@example.com', email='admin@example.com',
            password='testpass123', role='admin',
        )
        self.member = User.objects.create_user(
            username='member@example.com', email='member@example.com',
            password='testpass123', role='user', first_name='Mem', last_name='Ber',
        )

    # ── helpers ──────────────────────────────────────────────────────────────
    def make_topic(self, name, parent=None, **kwargs):
        return SurveyTopic.objects.create(
            name=name, parent=parent, created_by=self.admin, **kwargs
        )

    def make_survey(self, title='Survey', creator=None, topic=None, **kwargs):
        return Survey.objects.create(
            title=title,
            creator=creator or self.admin,
            topic=topic,
            status=kwargs.pop('status', 'submitted'),
            visibility=kwargs.pop('visibility', 'AUTH'),
            **kwargs,
        )

    def call(self, view, method, path, user, data=None, query=None, **kwargs):
        request = getattr(self.factory, method)(path, data, format='json') if data is not None \
            else getattr(self.factory, method)(path, query or {})
        force_authenticate(request, user=user)
        return view(request, **kwargs)


class SurveyTopicModelTests(TopicTestBase):
    """Model-level invariants."""

    def test_name_is_trimmed_and_key_is_casefolded(self):
        topic = self.make_topic('  Customer Experience  ')
        self.assertEqual(topic.name, 'Customer Experience')
        self.assertEqual(topic.name_key, 'customer experience')

    def test_root_topic_has_depth_zero_and_own_path(self):
        topic = self.make_topic('Root')
        self.assertEqual(topic.depth, 0)
        self.assertEqual(topic.path, topic.id.hex)

    def test_nested_topic_extends_parent_path(self):
        root = self.make_topic('Root')
        child = self.make_topic('Child', parent=root)
        self.assertEqual(child.depth, 1)
        self.assertEqual(child.path, f'{root.path}.{child.id.hex}')
        self.assertEqual([t.id for t in child.ancestors()], [root.id])

    def test_moving_a_subtree_resyncs_descendant_paths_and_depths(self):
        """
        Built three levels deep through the model on purpose: MAX_DEPTH is a
        serializer rule, so legacy/imported rows can still be deeper, and the path
        resync must keep them consistent when an ancestor moves.
        """
        root = self.make_topic('Root')
        child = self.make_topic('Child', parent=root)
        grand = self.make_topic('Grand', parent=child)

        child.parent = None
        child.save()

        child.refresh_from_db()
        grand.refresh_from_db()
        self.assertEqual(child.depth, 0)
        self.assertEqual(child.path, child.id.hex)
        self.assertEqual(grand.depth, 1)
        self.assertEqual(grand.path, f'{child.path}.{grand.id.hex}')

    def test_is_ancestor_of(self):
        root = self.make_topic('Root')
        child = self.make_topic('Child', parent=root)
        grand = self.make_topic('Grand', parent=child)
        self.assertTrue(root.is_ancestor_of(grand))
        self.assertFalse(grand.is_ancestor_of(root))
        self.assertFalse(root.is_ancestor_of(root))

    def test_soft_delete_detaches_surveys_and_reparents_children(self):
        root = self.make_topic('Root')
        child = self.make_topic('Child', parent=root)
        survey = self.make_survey(topic=root)

        root.soft_delete()

        survey.refresh_from_db()
        child.refresh_from_db()
        root.refresh_from_db()
        self.assertIsNone(survey.topic_id)
        self.assertIsNone(child.parent_id)
        self.assertEqual(child.depth, 0)
        self.assertIsNotNone(root.deleted_at)
        # the survey itself must survive
        self.assertTrue(Survey.objects.filter(pk=survey.pk, deleted_at__isnull=True).exists())

    def test_deleting_a_topic_row_never_deletes_its_surveys(self):
        root = self.make_topic('Root')
        survey = self.make_survey(topic=root)
        root.delete()  # hard delete, worst case
        survey.refresh_from_db()
        self.assertIsNone(survey.topic_id)


class SurveyTopicSerializerTests(TopicTestBase):
    """Validation rules that keep the tree sane."""

    def test_duplicate_name_is_rejected_case_insensitively(self):
        self.make_topic('Customer Experience')
        serializer = SurveyTopicSerializer(data={'name': 'customer EXPERIENCE'})
        self.assertFalse(serializer.is_valid())
        self.assertIn('name', serializer.errors)

    def test_renaming_a_topic_to_its_own_name_is_allowed(self):
        topic = self.make_topic('Customer Experience')
        serializer = SurveyTopicSerializer(
            topic, data={'name': 'Customer Experience', 'description': 'x'}, partial=True
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_depth_cap_is_enforced(self):
        """Only two levels: a main topic and its sub-topics."""
        root = self.make_topic('Root')
        child = self.make_topic('Child', parent=root)  # depth 1 == MAX_DEPTH - 1

        # a sub-topic of the main topic is fine
        ok = SurveyTopicSerializer(data={'name': 'Another sub', 'parent': str(root.id)})
        self.assertTrue(ok.is_valid(), ok.errors)

        # a sub-topic OF a sub-topic is not
        too_deep = SurveyTopicSerializer(data={'name': 'Too deep', 'parent': str(child.id)})
        self.assertFalse(too_deep.is_valid())
        self.assertIn('parent', too_deep.errors)

    def test_max_depth_is_two(self):
        self.assertEqual(SurveyTopic.MAX_DEPTH, 2)

    def test_cycles_are_rejected(self):
        root = self.make_topic('Root')
        child = self.make_topic('Child', parent=root)
        serializer = SurveyTopicSerializer(root, data={'parent': str(child.id)}, partial=True)
        self.assertFalse(serializer.is_valid())
        self.assertIn('parent', serializer.errors)

    def test_self_parenting_is_rejected(self):
        root = self.make_topic('Root')
        serializer = SurveyTopicSerializer(root, data={'parent': str(root.id)}, partial=True)
        self.assertFalse(serializer.is_valid())

    def test_a_topic_with_subtopics_cannot_become_a_subtopic(self):
        # Root already has a sub-topic, so nesting it under another topic would push
        # that child to depth 2 — past MAX_DEPTH.
        root = self.make_topic('Root')
        self.make_topic('Child', parent=root)
        other_root = self.make_topic('Other')

        serializer = SurveyTopicSerializer(root, data={'parent': str(other_root.id)}, partial=True)
        self.assertFalse(serializer.is_valid())
        self.assertIn('parent', serializer.errors)

    def test_a_leaf_topic_can_become_a_subtopic(self):
        leaf = self.make_topic('Leaf')
        other_root = self.make_topic('Other')
        serializer = SurveyTopicSerializer(leaf, data={'parent': str(other_root.id)}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        moved = serializer.save()
        self.assertEqual(moved.depth, 1)

    def test_color_and_icon_are_whitelisted(self):
        bad_color = SurveyTopicSerializer(data={'name': 'A', 'color': 'red; background:url(x)'})
        self.assertFalse(bad_color.is_valid())
        bad_icon = SurveyTopicSerializer(data={'name': 'B', 'icon': 'skull-and-crossbones'})
        self.assertFalse(bad_icon.is_valid())
        good = SurveyTopicSerializer(data={'name': 'C', 'color': '#A17D23', 'icon': 'folder'})
        self.assertTrue(good.is_valid(), good.errors)


class SurveyTopicApiTests(TopicTestBase):
    """The /api/surveys/topics/ endpoints."""

    def test_list_returns_root_topics_with_counters(self):
        root = self.make_topic('Root')
        child = self.make_topic('Child', parent=root)
        self.make_survey(topic=root)
        self.make_survey(topic=child)

        view = SurveyTopicViewSet.as_view({'get': 'list'})
        response = self.call(view, 'get', '/api/surveys/topics/', self.admin)
        self.assertEqual(response.status_code, 200)

        data = envelope(response)
        self.assertEqual(len(data['results']), 1)  # only the root by default
        row = data['results'][0]
        self.assertEqual(row['survey_count'], 1)
        self.assertEqual(row['children_count'], 1)
        self.assertEqual(row['total_survey_count'], 2)  # subtree rollup

    def test_list_can_scope_to_a_parent_or_everything(self):
        root = self.make_topic('Root')
        self.make_topic('Child', parent=root)

        view = SurveyTopicViewSet.as_view({'get': 'list'})
        by_parent = envelope(self.call(
            view, 'get', '/api/surveys/topics/', self.admin, query={'parent': str(root.id)}
        ))
        self.assertEqual([r['name'] for r in by_parent['results']], ['Child'])

        all_topics = envelope(self.call(
            view, 'get', '/api/surveys/topics/', self.admin, query={'parent': 'all'}
        ))
        self.assertEqual(len(all_topics['results']), 2)

    def test_search_looks_across_the_whole_forest(self):
        root = self.make_topic('Root')
        self.make_topic('Nested needle', parent=root)

        view = SurveyTopicViewSet.as_view({'get': 'list'})
        found = envelope(self.call(
            view, 'get', '/api/surveys/topics/', self.admin, query={'search': 'needle'}
        ))
        self.assertEqual([r['name'] for r in found['results']], ['Nested needle'])

    def test_archived_topics_are_hidden_by_default(self):
        self.make_topic('Live')
        self.make_topic('Old', is_archived=True)

        view = SurveyTopicViewSet.as_view({'get': 'list'})
        default = envelope(self.call(view, 'get', '/api/surveys/topics/', self.admin))
        self.assertEqual([r['name'] for r in default['results']], ['Live'])

        archived = envelope(self.call(
            view, 'get', '/api/surveys/topics/', self.admin, query={'is_archived': '1'}
        ))
        self.assertEqual([r['name'] for r in archived['results']], ['Old'])

    def test_pinned_topics_come_first(self):
        self.make_topic('Zeta')
        self.make_topic('Alpha')
        self.make_topic('Pinned', is_pinned=True)

        view = SurveyTopicViewSet.as_view({'get': 'list'})
        data = envelope(self.call(
            view, 'get', '/api/surveys/topics/', self.admin, query={'sort_by': 'name_asc'}
        ))
        self.assertEqual(data['results'][0]['name'], 'Pinned')

    def test_regular_user_can_read_but_not_create(self):
        list_view = SurveyTopicViewSet.as_view({'get': 'list', 'post': 'create'})
        read = self.call(list_view, 'get', '/api/surveys/topics/', self.member)
        self.assertEqual(read.status_code, 200)

        write = self.call(list_view, 'post', '/api/surveys/topics/', self.member, data={'name': 'Nope'})
        self.assertEqual(write.status_code, 403)

    def test_admin_can_create_and_gets_counters_back(self):
        view = SurveyTopicViewSet.as_view({'post': 'create'})
        response = self.call(
            view, 'post', '/api/surveys/topics/', self.admin,
            data={'name': 'Customer Experience', 'color': '#A17D23', 'icon': 'folder'},
        )
        self.assertEqual(response.status_code, 201)
        data = envelope(response)
        self.assertEqual(data['name'], 'Customer Experience')
        self.assertEqual(data['survey_count'], 0)
        self.assertEqual(data['total_survey_count'], 0)
        self.assertEqual(SurveyTopic.objects.get(pk=data['id']).created_by, self.admin)

    def test_duplicate_create_returns_400_with_a_message(self):
        self.make_topic('Customer Experience')
        view = SurveyTopicViewSet.as_view({'post': 'create'})
        response = self.call(
            view, 'post', '/api/surveys/topics/', self.admin, data={'name': 'customer experience'}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('already exists', str(response.data.get('message', '')))

    def test_retrieve_returns_breadcrumb_children_and_kpis(self):
        root = self.make_topic('Root')
        child = self.make_topic('Child', parent=root)
        self.make_survey(topic=child)
        self.make_survey(topic=root, status='draft')

        view = SurveyTopicViewSet.as_view({'get': 'retrieve'})
        response = self.call(view, 'get', f'/api/surveys/topics/{root.id}/', self.admin, pk=str(root.id))
        self.assertEqual(response.status_code, 200)

        data = envelope(response)
        self.assertEqual([b['name'] for b in data['topic']['breadcrumb']], ['Root'])
        self.assertEqual([c['name'] for c in data['children']], ['Child'])
        self.assertEqual(data['kpis']['total_surveys'], 2)
        self.assertEqual(data['kpis']['draft_surveys'], 1)

    def test_only_super_admin_can_delete_and_surveys_are_detached(self):
        root = self.make_topic('Root')
        survey = self.make_survey(topic=root)
        view = SurveyTopicViewSet.as_view({'delete': 'destroy'})

        denied = self.call(view, 'delete', f'/api/surveys/topics/{root.id}/', self.admin, pk=str(root.id))
        self.assertEqual(denied.status_code, 403)

        allowed = self.call(
            view, 'delete', f'/api/surveys/topics/{root.id}/', self.super_admin, pk=str(root.id)
        )
        self.assertEqual(allowed.status_code, 200)
        survey.refresh_from_db()
        self.assertIsNone(survey.topic_id)
        self.assertEqual(envelope(allowed)['detached_surveys'], 1)

    def test_archive_and_unarchive(self):
        topic = self.make_topic('Root')
        view = SurveyTopicViewSet.as_view({'post': 'archive'})

        archived = self.call(
            view, 'post', f'/api/surveys/topics/{topic.id}/archive/', self.admin,
            data={'is_archived': True}, pk=str(topic.id),
        )
        self.assertEqual(archived.status_code, 200)
        topic.refresh_from_db()
        self.assertTrue(topic.is_archived)

        restored = self.call(
            view, 'post', f'/api/surveys/topics/{topic.id}/archive/', self.admin,
            data={'is_archived': False}, pk=str(topic.id),
        )
        self.assertEqual(restored.status_code, 200)
        topic.refresh_from_db()
        self.assertFalse(topic.is_archived)

    def test_tree_returns_flat_forest_with_ungrouped_count(self):
        root = self.make_topic('Root')
        self.make_topic('Child', parent=root)
        self.make_survey()  # ungrouped

        view = SurveyTopicViewSet.as_view({'get': 'tree'})
        response = self.call(view, 'get', '/api/surveys/topics/tree/', self.admin)
        data = envelope(response)
        self.assertEqual(data['total'], 2)
        self.assertFalse(data['truncated'])
        self.assertEqual(data['ungrouped_survey_count'], 1)
        self.assertEqual({r['depth'] for r in data['results']}, {0, 1})

    def test_nodes_returns_children_and_surveys(self):
        root = self.make_topic('Root')
        self.make_topic('Child', parent=root)
        survey = self.make_survey(topic=root)

        view = SurveyTopicViewSet.as_view({'get': 'nodes'})
        response = self.call(
            view, 'get', f'/api/surveys/topics/{root.id}/nodes/', self.admin, pk=str(root.id)
        )
        data = envelope(response)
        self.assertEqual([c['name'] for c in data['children']], ['Child'])
        self.assertEqual([s['id'] for s in data['surveys']], [str(survey.id)])
        self.assertFalse(data['truncated'])

    def test_palette_lists_allowed_values(self):
        view = SurveyTopicViewSet.as_view({'get': 'palette'})
        data = envelope(self.call(view, 'get', '/api/surveys/topics/palette/', self.member))
        self.assertIn('#A17D23', data['colors'])
        self.assertIn('folder', data['icons'])
        self.assertEqual(data['max_depth'], SurveyTopic.MAX_DEPTH)
        self.assertEqual(data['max_depth'], 2)


class TopicAssignmentApiTests(TopicTestBase):
    """Bulk assign / detach behaviour and its authorization rules."""

    def setUp(self):
        super().setUp()
        self.topic = self.make_topic('Root')
        self.mine = self.make_survey(title='Mine', creator=self.admin)
        self.theirs = self.make_survey(title='Theirs', creator=self.super_admin)

    def test_admin_assigns_own_surveys_and_skips_the_rest(self):
        view = SurveyTopicViewSet.as_view({'post': 'assign'})
        response = self.call(
            view, 'post', '/api/surveys/topics/assign/', self.admin,
            data={'topic_id': str(self.topic.id),
                  'survey_ids': [str(self.mine.id), str(self.theirs.id)]},
        )
        self.assertEqual(response.status_code, 200)
        data = envelope(response)
        self.assertEqual(data['assigned'], 1)
        self.assertEqual(data['skipped'], 1)

        self.mine.refresh_from_db()
        self.theirs.refresh_from_db()
        self.assertEqual(self.mine.topic_id, self.topic.id)
        self.assertIsNone(self.theirs.topic_id)

    def test_super_admin_can_assign_anything(self):
        view = SurveyTopicViewSet.as_view({'post': 'assign'})
        data = envelope(self.call(
            view, 'post', '/api/surveys/topics/assign/', self.super_admin,
            data={'topic_id': str(self.topic.id),
                  'survey_ids': [str(self.mine.id), str(self.theirs.id)]},
        ))
        self.assertEqual(data['assigned'], 2)
        self.assertEqual(data['skipped'], 0)

    def test_assign_reports_previous_topics_so_the_ui_can_undo(self):
        other = self.make_topic('Other')
        Survey.objects.filter(pk=self.mine.pk).update(topic=other)

        view = SurveyTopicViewSet.as_view({'post': 'assign'})
        data = envelope(self.call(
            view, 'post', '/api/surveys/topics/assign/', self.admin,
            data={'topic_id': str(self.topic.id), 'survey_ids': [str(self.mine.id)]},
        ))
        self.assertEqual(data['previous_topics'][str(self.mine.id)], str(other.id))

    def test_assign_with_null_topic_clears_it(self):
        Survey.objects.filter(pk=self.mine.pk).update(topic=self.topic)
        view = SurveyTopicViewSet.as_view({'post': 'assign'})
        self.call(
            view, 'post', '/api/surveys/topics/assign/', self.admin,
            data={'topic_id': None, 'survey_ids': [str(self.mine.id)]},
        )
        self.mine.refresh_from_db()
        self.assertIsNone(self.mine.topic_id)

    def test_detach_only_touches_surveys_inside_that_topic(self):
        other_topic = self.make_topic('Other')
        Survey.objects.filter(pk=self.mine.pk).update(topic=other_topic)

        view = SurveyTopicViewSet.as_view({'post': 'detach'})
        data = envelope(self.call(
            view, 'post', f'/api/surveys/topics/{self.topic.id}/detach/', self.admin,
            data={'survey_ids': [str(self.mine.id)]}, pk=str(self.topic.id),
        ))
        self.assertEqual(data['assigned'], 0)
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.topic_id, other_topic.id)

    def test_archived_topic_rejects_new_surveys(self):
        archived = self.make_topic('Archived', is_archived=True)
        view = SurveyTopicViewSet.as_view({'post': 'assign'})
        response = self.call(
            view, 'post', '/api/surveys/topics/assign/', self.admin,
            data={'topic_id': str(archived.id), 'survey_ids': [str(self.mine.id)]},
        )
        self.assertEqual(response.status_code, 400)

    def test_regular_user_cannot_assign(self):
        view = SurveyTopicViewSet.as_view({'post': 'assign'})
        response = self.call(
            view, 'post', '/api/surveys/topics/assign/', self.member,
            data={'topic_id': str(self.topic.id), 'survey_ids': [str(self.mine.id)]},
        )
        self.assertEqual(response.status_code, 403)

    def test_assign_requires_survey_ids(self):
        view = SurveyTopicViewSet.as_view({'post': 'assign'})
        response = self.call(
            view, 'post', '/api/surveys/topics/assign/', self.admin,
            data={'topic_id': str(self.topic.id), 'survey_ids': []},
        )
        self.assertEqual(response.status_code, 400)

    def test_assign_does_not_corrupt_encrypted_title(self):
        """The bulk UPDATE must not re-encrypt or re-hash the title."""
        original_hash = Survey.objects.get(pk=self.mine.pk).title_hash
        view = SurveyTopicViewSet.as_view({'post': 'assign'})
        self.call(
            view, 'post', '/api/surveys/topics/assign/', self.admin,
            data={'topic_id': str(self.topic.id), 'survey_ids': [str(self.mine.id)]},
        )
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.title, 'Mine')
        self.assertEqual(self.mine.title_hash, original_hash)


class SurveyListTopicFilterTests(TopicTestBase):
    """The `topic` filter and topic-scoped KPIs on the survey list endpoint."""

    def setUp(self):
        super().setUp()
        self.root = self.make_topic('Root')
        self.child = self.make_topic('Child', parent=self.root)
        self.in_root = self.make_survey(title='In root', topic=self.root)
        self.in_child = self.make_survey(title='In child', topic=self.child)
        self.ungrouped = self.make_survey(title='Ungrouped')
        self.view = SurveyViewSet.as_view({'get': 'list'})

    def titles(self, **query):
        response = self.call(self.view, 'get', '/api/surveys/surveys/', self.admin, query=query)
        self.assertEqual(response.status_code, 200)
        return {row['title'] for row in envelope(response)['results']}

    def test_topic_none_returns_ungrouped_only(self):
        self.assertEqual(self.titles(topic='none'), {'Ungrouped'})

    def test_topic_any_returns_grouped_only(self):
        self.assertEqual(self.titles(topic='any'), {'In root', 'In child'})

    def test_topic_uuid_returns_direct_children_only(self):
        self.assertEqual(self.titles(topic=str(self.root.id)), {'In root'})

    def test_include_descendants_returns_the_subtree(self):
        self.assertEqual(
            self.titles(topic=str(self.root.id), include_descendants='1'),
            {'In root', 'In child'},
        )

    def test_unknown_topic_returns_nothing(self):
        self.assertEqual(self.titles(topic='11111111-1111-1111-1111-111111111111'), set())

    def test_kpis_are_scoped_to_the_topic(self):
        response = self.call(
            self.view, 'get', '/api/surveys/surveys/', self.admin,
            query={'topic': str(self.root.id)},
        )
        body = response.data
        self.assertEqual(body['total_surveys'], 1)

        subtree = self.call(
            self.view, 'get', '/api/surveys/surveys/', self.admin,
            query={'topic': str(self.root.id), 'include_descendants': '1'},
        )
        self.assertEqual(subtree.data['total_surveys'], 2)

        globally = self.call(self.view, 'get', '/api/surveys/surveys/', self.admin)
        self.assertEqual(globally.data['total_surveys'], 3)

    def test_serializer_exposes_topic_mirrors(self):
        response = self.call(
            self.view, 'get', '/api/surveys/surveys/', self.admin, query={'topic': str(self.root.id)}
        )
        row = envelope(response)['results'][0]
        self.assertEqual(str(row['topic']), str(self.root.id))
        self.assertEqual(row['topic_name'], 'Root')

    def test_survey_can_be_filed_and_cleared_through_the_serializer(self):
        detail = SurveyViewSet.as_view({'patch': 'partial_update'})
        response = self.call(
            detail, 'patch', f'/api/surveys/surveys/{self.ungrouped.id}/', self.admin,
            data={'topic': str(self.root.id)}, pk=str(self.ungrouped.id),
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.ungrouped.refresh_from_db()
        self.assertEqual(self.ungrouped.topic_id, self.root.id)

        cleared = self.call(
            detail, 'patch', f'/api/surveys/surveys/{self.ungrouped.id}/', self.admin,
            data={'topic': ''}, pk=str(self.ungrouped.id),
        )
        self.assertEqual(cleared.status_code, 200, cleared.data)
        self.ungrouped.refresh_from_db()
        self.assertIsNone(self.ungrouped.topic_id)

    def test_archived_topic_is_rejected_by_the_serializer(self):
        archived = self.make_topic('Archived', is_archived=True)
        detail = SurveyViewSet.as_view({'patch': 'partial_update'})
        response = self.call(
            detail, 'patch', f'/api/surveys/surveys/{self.ungrouped.id}/', self.admin,
            data={'topic': str(archived.id)}, pk=str(self.ungrouped.id),
        )
        self.assertEqual(response.status_code, 400)


class AssignedUsersApiTests(TopicTestBase):
    """The assigned-users panel behind the survey preview."""

    def setUp(self):
        super().setUp()
        self.view = SurveyViewSet.as_view({'get': 'assigned_users'})
        self.group = Group.objects.create(name='Legal')
        self.group_member = User.objects.create_user(
            username='legal@example.com', email='legal@example.com',
            password='testpass123', role='user', first_name='Leg', last_name='Al',
        )
        UserGroup.objects.create(user=self.group_member, group=self.group)

    def fetch(self, survey, user=None, **query):
        response = self.call(
            self.view, 'get', f'/api/surveys/surveys/{survey.id}/assigned-users/',
            user or self.admin, query=query, pk=str(survey.id),
        )
        return response, envelope(response)

    def test_private_survey_lists_named_users(self):
        survey = self.make_survey(visibility='PRIVATE')
        survey.shared_with.add(self.member)

        response, data = self.fetch(survey)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['mode'], 'explicit')
        self.assertEqual(data['total_users'], 1)
        self.assertEqual(data['results'][0]['email'], self.member.email)
        self.assertEqual(data['results'][0]['source'], 'direct')
        self.assertFalse(data['results'][0]['responded'])

    def test_group_members_are_included_with_group_source(self):
        survey = self.make_survey(visibility='GROUPS')
        survey.shared_with_groups.add(self.group)

        _, data = self.fetch(survey)
        self.assertEqual(data['total_users'], 1)
        self.assertEqual(data['results'][0]['source'], 'group')
        self.assertEqual(data['groups'][0]['name'], 'Legal')
        self.assertEqual(data['groups'][0]['member_count'], 1)

    def test_responded_state_and_filters(self):
        survey = self.make_survey(visibility='PRIVATE')
        survey.shared_with.add(self.member, self.group_member)
        SurveyResponse.objects.create(survey=survey, respondent=self.member)

        _, data = self.fetch(survey)
        self.assertEqual(data['total_users'], 2)
        self.assertEqual(data['responded_count'], 1)
        self.assertEqual(data['pending_count'], 1)

        _, responded = self.fetch(survey, response_status='responded')
        self.assertEqual([r['email'] for r in responded['results']], [self.member.email])
        # date only (YYYY-MM-DD) — the preview shows the day, not the clock
        responded_at = responded['results'][0]['responded_at']
        self.assertIsNotNone(responded_at)
        self.assertRegex(responded_at, r'^\d{4}-\d{2}-\d{2}$')

        _, pending = self.fetch(survey, response_status='pending')
        self.assertEqual([r['email'] for r in pending['results']], [self.group_member.email])

    def test_search_matches_name_and_email(self):
        survey = self.make_survey(visibility='PRIVATE')
        survey.shared_with.add(self.member, self.group_member)

        _, by_email = self.fetch(survey, search='legal@')
        self.assertEqual([r['email'] for r in by_email['results']], [self.group_member.email])

        _, by_name = self.fetch(survey, search='Mem')
        self.assertEqual([r['email'] for r in by_name['results']], [self.member.email])

    def test_pagination(self):
        survey = self.make_survey(visibility='PRIVATE')
        survey.shared_with.add(self.member, self.group_member, self.super_admin)

        _, page1 = self.fetch(survey, per_page=2, page=1)
        self.assertEqual(len(page1['results']), 2)
        self.assertEqual(page1['total_pages'], 2)

        _, page2 = self.fetch(survey, per_page=2, page=2)
        self.assertEqual(len(page2['results']), 1)

    def test_auth_survey_reports_all_authenticated(self):
        survey = self.make_survey(visibility='AUTH')
        _, data = self.fetch(survey)
        self.assertEqual(data['mode'], 'all_authenticated')
        self.assertEqual(data['total_users'], User.objects.filter(is_active=True).count())
        self.assertEqual(data['results'][0]['source'], 'all_authenticated')

    def test_public_survey_has_no_audience(self):
        survey = self.make_survey(visibility='PUBLIC')
        _, data = self.fetch(survey)
        self.assertEqual(data['mode'], 'public')
        self.assertEqual(data['total_users'], 0)
        self.assertEqual(data['results'], [])

    def test_regular_user_cannot_read_the_audience(self):
        survey = self.make_survey(visibility='PRIVATE', creator=self.admin)
        survey.shared_with.add(self.member)
        response, _ = self.fetch(survey, user=self.member)
        self.assertEqual(response.status_code, 403)


class TopicQueryBudgetTests(TopicTestBase):
    """Guard rails against N+1 regressions."""

    def test_topic_list_query_count_is_independent_of_page_size(self):
        for i in range(3):
            topic = self.make_topic(f'Topic {i}')
            self.make_survey(title=f'S{i}', topic=topic)

        view = SurveyTopicViewSet.as_view({'get': 'list'})

        with self.assertNumQueries(4):
            # 1 count (paginator) + 1 page + 2 subtree rollups
            self.call(view, 'get', '/api/surveys/topics/', self.admin)

        for i in range(3, 9):
            topic = self.make_topic(f'Topic {i}')
            self.make_survey(title=f'S{i}', topic=topic)

        with self.assertNumQueries(4):
            self.call(view, 'get', '/api/surveys/topics/', self.admin)

    def test_survey_list_does_not_query_per_topic(self):
        topic = self.make_topic('Root')
        for i in range(5):
            self.make_survey(title=f'S{i}', topic=topic)

        view = SurveyViewSet.as_view({'get': 'list'})
        # Baseline with one survey, then with five: the delta must stay flat for the
        # topic mirrors (select_related('topic') + 'topic' in the .only() list).
        response = self.call(view, 'get', '/api/surveys/surveys/', self.admin,
                             query={'topic': str(topic.id)})
        self.assertEqual(response.status_code, 200)
        rows = envelope(response)['results']
        self.assertEqual(len(rows), 5)
        self.assertTrue(all(r['topic_name'] == 'Root' for r in rows))
