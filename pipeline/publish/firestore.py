"""Firestore publisher — batched upserts with a daily write budget.

Only aggregated district docs are written (never raw rows). The budget
(config.FIRESTORE_DAILY_WRITE_CAP) keeps the daemon safely inside the
Spark free tier's ~20k writes/day.
"""
import logging
from datetime import datetime, timezone

from .. import config, state as state_mod

log = logging.getLogger("pipeline.firestore")

_client = None


class QuotaDeferred(Exception):
    """Raised when a publish would exceed today's write budget."""


def client():
    global _client
    if _client is None:
        import firebase_admin
        from firebase_admin import credentials, firestore
        if not firebase_admin._apps:
            cred = credentials.Certificate(config.firebase_service_account())
            opts = {}
            project_id = config.firebase_project_id()
            if project_id:
                opts["projectId"] = project_id
            firebase_admin.initialize_app(cred, opts or None)
        _client = firestore.client()
    return _client


def publish_docs(state, collection, docs, merge=True):
    """Upsert {doc_id: doc} into `collection`. Returns docs written."""
    if not docs:
        return 0
    budget = state_mod.writes_available(state)
    if len(docs) > budget:
        raise QuotaDeferred(
            "publish of {} docs to '{}' deferred: only {} writes left in "
            "today's budget".format(len(docs), collection, budget))
    db = client()
    items = [(str(doc_id), doc) for doc_id, doc in docs.items()]
    _commit_adaptive(db, collection, items, merge)
    state_mod.add_writes(state, len(docs))
    log.info("published %d docs -> %s", len(docs), collection)
    return len(docs)


_BATCH_SIZE = 300  # < Firestore's 500-write cap; real limit is 10MB/commit


def _commit_adaptive(db, collection, items, merge, size=_BATCH_SIZE):
    """Commit in chunks; on 'Transaction too big' halve the chunk and retry
    (SECC-style fat docs can exceed the 10MB commit limit at any fixed count).
    """
    from google.api_core.exceptions import InvalidArgument
    i = 0
    while i < len(items):
        chunk = items[i:i + size]
        batch = db.batch()
        for doc_id, doc in chunk:
            batch.set(db.collection(collection).document(doc_id), doc,
                      merge=merge)
        try:
            batch.commit()
        except InvalidArgument as e:
            if "too big" in str(e).lower() and size > 5:
                log.warning("%s: commit of %d docs too big — halving to %d",
                            collection, len(chunk), size // 2)
                _commit_adaptive(db, collection, chunk, merge, size // 2)
            else:
                raise
        i += size


def heartbeat(state, source_id, payload):
    """pipeline_status/{source_id} — the live app shows freshness from this."""
    db = client()
    payload = dict(payload)
    payload["ts"] = datetime.now(timezone.utc).isoformat()
    db.collection("pipeline_status").document(source_id).set(payload, merge=True)
    state_mod.add_writes(state, 1)
