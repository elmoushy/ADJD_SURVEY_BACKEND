"""
Oracle-safe BLOB writes.

Why this exists
---------------
Every attachment model in this project uses a client-generated UUID primary
key. Because that pk is not database-returning, Django's insert compiler takes
its *bulk* branch even for a single row::

    can_bulk = not self.returning_fields and self.connection.features.has_bulk_insert

On Oracle that branch emits the file through ``BulkInsertMapper``::

    INSERT INTO "SURVEYS_SURVEY_ATTACHMENT" (..., "FILE_DATA", ...)
    SELECT * FROM (SELECT :arg0 col_0, ..., TO_BLOB(:arg2) col_2, ... FROM DUAL)

At the same time ``django.db.backends.oracle.base.OracleParam`` only assigns an
``input_size`` for long *strings* (``DB_TYPE_CLOB``) — a ``bytes`` parameter is
always left at ``input_size = None``, so python-oracledb binds a multi-megabyte
upload as LONG RAW. Oracle accepts a LONG bind only when it is assigned
directly to a column; as the argument of ``TO_BLOB()`` inside a subquery it
raises::

    ORA-01461: can bind a LONG value only for insert into a LONG column

Small files slip through because they bind as ordinary RAW, which is why only
the larger uploads failed.

What this does
--------------
``OracleBlobSafeMixin`` splits the write in two, on Oracle only:

1. Write the row with a one-byte placeholder in each BLOB column. The columns
   are ``BLOB NOT NULL`` and Oracle stores an empty binary value as NULL, so
   the placeholder cannot be ``b''``.
2. Write each BLOB with an explicit ``DB_TYPE_BLOB`` bind::

       UPDATE "SURVEYS_SURVEY_ATTACHMENT"
          SET "FILE_DATA" = :data
        WHERE "ID" = :pk

   That assigns straight to the column, so neither a LONG bind nor a
   ``TO_BLOB()`` wrapper is involved and the size of the file stops mattering.

Both statements run inside one transaction, so the placeholder is never visible
to another session and a failed BLOB write rolls the whole row back. The write
is verified by row count: a BLOB update that matches no row raises instead of
silently leaving the placeholder behind.

On every other backend (sqlite in dev and tests) ``save()`` is left untouched.

Note: ``bulk_create()`` bypasses ``Model.save()`` and would still hit the
original Oracle bug. Nothing in this project bulk-creates attachments; new code
that needs to must go through ``save()`` or extend this module.
"""

import logging

from django.db import DatabaseError, connections, router, transaction

logger = logging.getLogger(__name__)

# BLOB columns are declared NOT NULL and Oracle maps an empty binary value to
# NULL, so the stand-in has to be a real byte. It only ever exists inside the
# transaction that immediately overwrites it.
BLOB_PLACEHOLDER = b'\x00'

# Legacy positional order of Model.save(), still tolerated by Django 5.x.
_SAVE_POSITIONAL = ('force_insert', 'force_update', 'using', 'update_fields')


def blob_to_bytes(value):
    """Normalise whatever a backend hands back for a BLOB into plain bytes."""
    if value is None:
        return b''
    if isinstance(value, bytes):
        return value
    if hasattr(value, 'read'):  # oracledb LOB locator
        return bytes(value.read() or b'')
    return bytes(value)  # bytearray / memoryview


def _driver_cursor(cursor):
    """
    Unwrap Django's cursor wrappers down to the python-oracledb cursor.

    connection.cursor() -> CursorWrapper/CursorDebugWrapper
                        -> FormatStylePlaceholderCursor
                        -> oracledb.Cursor

    The driver cursor is needed because Django's wrapper rewrites ``%s``
    placeholders and re-derives its own input sizes, which is exactly the
    behaviour this module exists to bypass.
    """
    inner = cursor
    for _ in range(8):  # bounded: never spin on a self-referential wrapper
        nested = getattr(inner, 'cursor', None)
        if nested is None or nested is inner:
            break
        inner = nested
    return inner


def write_blob(connection, instance, field_name, data):
    """
    Write one BLOB column with an explicit LOB bind.

    Direct column assignment plus a ``DB_TYPE_BLOB`` input size keeps the value
    off both paths Oracle rejects: no LONG bind, no ``TO_BLOB()`` conversion.
    """
    meta = instance._meta
    quote = connection.ops.quote_name
    sql = 'UPDATE {table} SET {column} = :data WHERE {pk} = :pk'.format(
        table=quote(meta.db_table),
        column=quote(meta.get_field(field_name).column),
        pk=quote(meta.pk.column),
    )
    # Oracle has no native UUID type — the pk is bound as its 32-char hex form,
    # exactly as Django binds it everywhere else.
    pk_value = meta.pk.get_db_prep_value(instance.pk, connection, prepared=False)

    with connection.wrap_database_errors:
        with connection.cursor() as cursor:
            driver_cursor = _driver_cursor(cursor)
            driver_cursor.setinputsizes(data=connection.Database.DB_TYPE_BLOB)
            driver_cursor.execute(sql, {'data': data, 'pk': pk_value})
            rowcount = driver_cursor.rowcount

    if rowcount != 1:
        # Raising inside the caller's atomic block rolls the placeholder row
        # back rather than leaving a truncated file behind.
        raise DatabaseError(
            f'{meta.label}.{field_name}: BLOB write matched {rowcount} rows '
            f'for pk {instance.pk} (expected 1)'
        )


class OracleBlobSafeMixin:
    """
    Mixin for models with BinaryField columns. List them in ``blob_fields``.

    Must come before ``models.Model`` in the bases. It is a plain object (not
    an abstract model), so it changes no field, option or manager and needs no
    migration.
    """

    #: Names of the BinaryField attributes this model stores as Oracle BLOBs.
    blob_fields = ()

    def save(self, *args, **kwargs):
        options = dict(zip(_SAVE_POSITIONAL, args))
        options.update(kwargs)

        using = options.get('using') or router.db_for_write(
            type(self), instance=self
        )
        connection = connections[using]

        if connection.vendor != 'oracle':
            return super().save(*args, **kwargs)

        update_fields = options.get('update_fields')
        written = None if update_fields is None else set(update_fields)
        pending = [
            name for name in self.blob_fields
            if written is None or name in written
        ]
        if not pending:
            return super().save(*args, **kwargs)

        payloads = {name: blob_to_bytes(getattr(self, name)) for name in pending}
        result = None
        try:
            for name in pending:
                setattr(self, name, BLOB_PLACEHOLDER)
            with transaction.atomic(using=using):
                result = super().save(*args, **kwargs)
                for name, data in payloads.items():
                    write_blob(connection, self, name, data)
        finally:
            # Leave the instance holding the real bytes either way, so callers
            # and serializers never see the placeholder.
            for name, data in payloads.items():
                setattr(self, name, data)

        logger.debug(
            'Oracle BLOB write: %s pk=%s fields=%s bytes=%s',
            self._meta.label, self.pk, pending,
            {name: len(data) for name, data in payloads.items()},
        )
        return result
