"""
Tests for the Oracle-safe BLOB write path (adjd_survey.oracle_blob).

The bug being guarded against is ORA-01461: on Oracle, Django routes a
single-row insert of a UUID-pk model through its bulk-insert SQL, which wraps
BinaryField values in TO_BLOB() and binds them as LONG RAW — illegal for
anything past a few KB. OracleBlobSafeMixin writes the row first and the BLOB
second, with an explicit LOB bind.

Most of these run on any backend: they check the statement and the binds the
Oracle path would produce, which is where a silent corruption would come from
(a mismatched pk bind updates no row and leaves the placeholder behind).
The end-to-end round trip only runs when the tests are pointed at Oracle.
"""

import uuid
from unittest.mock import MagicMock

from django.contrib.auth import get_user_model
from django.db import DatabaseError, connection
from django.test import TestCase

from adjd_survey.oracle_blob import (
    BLOB_PLACEHOLDER,
    OracleBlobSafeMixin,
    blob_to_bytes,
    write_blob,
)
from surveys.models import Survey, SurveyAttachment

User = get_user_model()

IS_ORACLE = connection.vendor == 'oracle'


class _FakeLob:
    """Stands in for an oracledb LOB locator, which is read() not bytes()."""

    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return self._payload


class BlobToBytesTests(TestCase):
    """Every shape a backend may hand back for a BLOB must normalise to bytes."""

    def test_none_becomes_empty_bytes(self):
        self.assertEqual(blob_to_bytes(None), b'')

    def test_bytes_pass_through(self):
        self.assertEqual(blob_to_bytes(b'\x00\xffdata'), b'\x00\xffdata')

    def test_memoryview_is_materialised(self):
        self.assertEqual(blob_to_bytes(memoryview(b'abc')), b'abc')

    def test_lob_locator_is_read(self):
        self.assertEqual(blob_to_bytes(_FakeLob(b'%PDF-1.7')), b'%PDF-1.7')

    def test_empty_lob_reading_none(self):
        self.assertEqual(blob_to_bytes(_FakeLob(None)), b'')


class WriteBlobStatementTests(TestCase):
    """
    The BLOB UPDATE must target the right row with the right bind types.

    A wrong pk bind (e.g. the dashed UUID form instead of Oracle's 32-char hex)
    would match zero rows, commit, and leave the one-byte placeholder in place —
    a "successful" upload storing a corrupt file. That is what these assert.
    """

    def setUp(self):
        self.instance = SurveyAttachment(
            id=uuid.UUID('75afdcf3-3e1e-4f49-8a1d-7ffb8f2191f3')
        )

        self.driver_cursor = MagicMock()
        self.driver_cursor.rowcount = 1
        # No .cursor attribute: this is the innermost (driver) cursor.
        del self.driver_cursor.cursor

        django_cursor = MagicMock()
        django_cursor.cursor = self.driver_cursor
        django_cursor.__enter__ = MagicMock(return_value=django_cursor)
        django_cursor.__exit__ = MagicMock(return_value=False)

        self.connection = MagicMock()
        self.connection.cursor.return_value = django_cursor
        self.connection.ops.quote_name.side_effect = lambda name: '"%s"' % name.upper()
        self.connection.Database.DB_TYPE_BLOB = 'DB_TYPE_BLOB'
        # get_db_prep_value is asked of the real field, not the mock.
        self.connection.features.has_native_uuid_field = False

    def _call(self, data=b'x' * 5000):
        write_blob(self.connection, self.instance, 'file_data', data)
        return self.driver_cursor.execute.call_args

    def test_updates_the_blob_column_by_primary_key(self):
        sql, binds = self._call()[0]
        self.assertEqual(
            sql,
            'UPDATE "SURVEYS_SURVEY_ATTACHMENT" SET "FILE_DATA" = :data '
            'WHERE "ID" = :pk',
        )
        self.assertNotIn('TO_BLOB', sql)

    def test_primary_key_is_bound_as_oracle_hex(self):
        _, binds = self._call()[0]
        self.assertEqual(binds['pk'], '75afdcf33e1e4f498a1d7ffb8f2191f3')
        self.assertNotIn('-', binds['pk'])

    def test_payload_is_bound_verbatim_as_a_lob(self):
        payload = b'%PDF-1.7' + b'\x00' * 3_000_000
        _, binds = self._call(payload)[0]
        self.assertEqual(binds['data'], payload)
        self.driver_cursor.setinputsizes.assert_called_once_with(
            data='DB_TYPE_BLOB'
        )

    def test_a_write_that_matches_no_row_raises(self):
        self.driver_cursor.rowcount = 0
        with self.assertRaises(DatabaseError):
            write_blob(self.connection, self.instance, 'file_data', b'x' * 5000)


class BlobFieldDeclarationTests(TestCase):
    """Every BinaryField in the project must be routed through the mixin."""

    def test_all_binary_field_models_opt_in(self):
        from django.apps import apps
        from django.db.models import BinaryField

        missing = []
        for model in apps.get_models():
            binary = [
                f.name for f in model._meta.get_fields()
                if isinstance(f, BinaryField)
            ]
            if not binary:
                continue
            declared = set(getattr(model, 'blob_fields', ()) or ())
            if not issubclass(model, OracleBlobSafeMixin) or not set(binary) <= declared:
                missing.append((model._meta.label, binary, sorted(declared)))

        self.assertEqual(missing, [], 'BinaryField models missing the Oracle BLOB path')


class OracleBlobRoundTripTests(TestCase):
    """
    End-to-end proof, Oracle only: a payload far past the LONG bind limit
    survives the insert and comes back byte-identical.
    """

    def setUp(self):
        if not IS_ORACLE:
            self.skipTest('Oracle-only: exercises the LOB bind path')
        self.user = User.objects.create_user(
            username='blob-test@adjd.com',
            email='blob-test@adjd.com',
            password='Test@12345',
            role='admin',
        )
        self.survey = Survey.objects.create(
            title='BLOB round trip', description='x', creator=self.user
        )

    def test_multi_megabyte_upload_round_trips(self):
        import hashlib

        payload = (b'%PDF-1.7\r' + bytes(range(256)) * 8192)  # ~2 MB
        attachment = SurveyAttachment.objects.create(
            survey=self.survey,
            file_data=payload,
            original_filename='round-trip.pdf',
            file_size=len(payload),
            mime_type='application/pdf',
            description='',
            display_order=0,
            uploaded_by=self.user,
        )

        # The in-memory instance keeps the real bytes, never the placeholder.
        self.assertEqual(blob_to_bytes(attachment.file_data), payload)
        self.assertNotEqual(blob_to_bytes(attachment.file_data), BLOB_PLACEHOLDER)

        stored = blob_to_bytes(
            SurveyAttachment.objects.get(pk=attachment.pk).file_data
        )
        self.assertEqual(len(stored), len(payload))
        self.assertEqual(
            hashlib.sha256(stored).hexdigest(),
            hashlib.sha256(payload).hexdigest(),
        )
