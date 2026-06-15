"""
Async Firestore Utilities
=========================
Thin async wrappers around the synchronous Firebase Admin SDK.
Every module should import helpers from here instead of calling
blocking Firestore methods directly in async code.

Why this exists:
    firebase-admin's Firestore client is synchronous.  Calling .get(),
    .update(), .stream() etc. inside an ``async def`` endpoint blocks
    the entire asyncio event loop, starving all concurrent requests.
    These helpers push blocking I/O into a thread-pool via
    ``asyncio.to_thread`` so the event loop stays responsive.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Callable, List, Optional, Tuple

from firebase_admin import firestore as _fs


# ──────────────────────────────────────────────
# Singleton client
# ──────────────────────────────────────────────

_db = None


def get_db():
    """Return the Firestore client (lazy singleton)."""
    global _db
    if _db is None:
        _db = _fs.client()
    return _db


# ──────────────────────────────────────────────
# Timezone helper
# ──────────────────────────────────────────────

def utcnow() -> datetime:
    """Timezone-aware UTC now.  Use *everywhere* instead of datetime.utcnow()."""
    return datetime.now(timezone.utc)


# ──────────────────────────────────────────────
# Document CRUD
# ──────────────────────────────────────────────

async def get_doc(collection: str, doc_id: str) -> Optional[dict]:
    """Fetch a single document.  Returns dict or None if missing."""
    db = get_db()
    ref = db.collection(collection).document(doc_id)
    snap = await asyncio.to_thread(ref.get)
    return snap.to_dict() if snap.exists else None


async def get_doc_snapshot(collection: str, doc_id: str):
    """Fetch a raw DocumentSnapshot (when you need .exists / .reference)."""
    db = get_db()
    ref = db.collection(collection).document(doc_id)
    return await asyncio.to_thread(ref.get)


async def set_doc(collection: str, doc_id: str, data: dict, merge: bool = False):
    """Create or overwrite a document."""
    db = get_db()
    ref = db.collection(collection).document(doc_id)
    await asyncio.to_thread(lambda: ref.set(data, merge=merge))


async def update_doc(collection: str, doc_id: str, data: dict):
    """Update fields on an existing document.  Raises if doc doesn't exist."""
    db = get_db()
    ref = db.collection(collection).document(doc_id)
    await asyncio.to_thread(lambda: ref.update(data))


async def delete_doc(collection: str, doc_id: str):
    """Delete a document."""
    db = get_db()
    ref = db.collection(collection).document(doc_id)
    await asyncio.to_thread(ref.delete)


# ──────────────────────────────────────────────
# Query helpers
# ──────────────────────────────────────────────

def build_query(
    collection: str,
    filters: Optional[List[Tuple[str, str, Any]]] = None,
    order_by: Optional[str] = None,
    descending: bool = False,
    limit: Optional[int] = None,
    start_after_doc=None,
):
    """
    Build a Firestore query object (synchronous — returns a Query).

    Parameters
    ----------
    filters : list of (field, operator, value) tuples
    order_by : field name to sort by
    descending : sort direction
    limit : max docs to return
    start_after_doc : a DocumentSnapshot for cursor-based pagination
    """
    db = get_db()
    q = db.collection(collection)

    if filters:
        for field, op, value in filters:
            q = q.where(filter=_fs.FieldFilter(field, op, value))

    if order_by:
        direction = (
            _fs.Query.DESCENDING if descending else _fs.Query.ASCENDING
        )
        q = q.order_by(order_by, direction=direction)

    if start_after_doc is not None:
        q = q.start_after(start_after_doc)

    if limit:
        q = q.limit(limit)

    return q


async def stream_query(query) -> List[dict]:
    """Stream a Firestore query in a thread, returning list of dicts."""
    def _collect():
        return [doc.to_dict() for doc in query.stream()]
    return await asyncio.to_thread(_collect)


async def stream_query_snapshots(query) -> list:
    """Stream a query returning raw DocumentSnapshot objects."""
    def _collect():
        return list(query.stream())
    return await asyncio.to_thread(_collect)


# ──────────────────────────────────────────────
# Transactions
# ──────────────────────────────────────────────

async def run_transaction(transactional_fn: Callable, **kwargs):
    """
    Execute a ``@firestore.transactional`` function in a thread pool.

    Usage::

        @_fs.transactional
        def _do_update(transaction, ref, new_status):
            snap = ref.get(transaction=transaction)
            transaction.update(ref, {'status': new_status})
            return snap.to_dict()

        result = await run_transaction(_do_update, ref=my_ref, new_status='done')
    """
    db = get_db()

    def _run():
        transaction = db.transaction()
        return transactional_fn(transaction, **kwargs)

    return await asyncio.to_thread(_run)


# ──────────────────────────────────────────────
# Batch helpers
# ──────────────────────────────────────────────

async def batch_update(collection: str, updates: List[Tuple[str, dict]]):
    """
    Batch-update multiple documents in a single commit.

    Parameters
    ----------
    updates : list of (doc_id, field_dict) tuples
    """
    db = get_db()

    def _commit():
        batch = db.batch()
        for doc_id, fields in updates:
            ref = db.collection(collection).document(doc_id)
            batch.update(ref, fields)
        batch.commit()

    await asyncio.to_thread(_commit)
