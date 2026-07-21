"""Pipeline orchestrator.

  python3 -m pipeline.run --status              # print the state table
  python3 -m pipeline.run --once                # run every DUE source once
  python3 -m pipeline.run --once --force        # run everything now
  python3 -m pipeline.run --source nikshay_tb   # run specific source(s)
  python3 -m pipeline.run --daemon              # continuous mode (the demo)
  add --no-publish to any of the above to skip Firestore writes

State lives in data/state/pipeline_state.json and is mirrored into
docs/PIPELINE_CHECKLIST.md after every step — resume-safe by design.
"""
import argparse
import fcntl
import logging
import os
import signal
import sys
import time

from . import config, state as state_mod
from .fetchers import FETCHERS
from .http_client import make_session

log = logging.getLogger("pipeline")

_lock_fh = None  # held for process lifetime; flock dies with the process


def acquire_instance_lock():
    """state file is whole-file load/save — concurrent instances clobber each
    other (observed 2026-07-15: daemon + --source re-ran pmjay every ~5 min).
    Exclusive non-blocking flock; auto-released even on SIGKILL."""
    global _lock_fh
    config.ensure_dirs()
    _lock_fh = open(config.STATE_DIR / "pipeline.lock", "w")
    try:
        fcntl.flock(_lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit("another pipeline instance is already running (lock held on "
                 "data/state/pipeline.lock) — state is not multi-process "
                 "safe, refusing to start. The lock releases automatically "
                 "when that process exits.")
    _lock_fh.write(str(os.getpid()))
    _lock_fh.flush()


def setup_logging():
    config.ensure_dirs()
    fmt = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(config.LOG_DIR / "pipeline.log"),
    ])


def run_source(state, source_id, publish=True):
    cfg = config.SOURCES[source_id]
    fetcher = FETCHERS[cfg["kind"]]
    log.info("=== %s (step %s) start ===", source_id, cfg["step"])
    state_mod.record_attempt(state, source_id)
    session = make_session()
    prev = state_mod.src(state, source_id)
    prev_hash = prev.get("content_hash")
    prev_raw = prev.get("raw_path")
    prev_published = prev.get("published_docs")

    hb = {"step": cfg["step"], "source": source_id}
    try:
        res = fetcher(source_id, cfg, session, prev_hash)
    except Exception as e:  # noqa: BLE001 — exact error goes to state table
        log.exception("%s FAILED", source_id)
        state_mod.record_error(state, source_id, e)
        hb.update(status="error", error=str(e)[:400])
        _heartbeat(state, source_id, hb, publish)
        return False

    if res.get("skipped"):
        log.warning("%s skipped: %s", source_id, res["why"])
        state_mod.record_skipped(state, source_id, res["why"])
        hb.update(status="skipped", note=res["why"])
        _heartbeat(state, source_id, hb, publish)
        return True

    unchanged = res.get("unchanged", False)
    state_mod.record_success(
        state, source_id, res.get("rows"),
        res.get("raw_path") or prev_raw, res.get("content_hash"),
        res.get("verify_note"), unchanged=unchanged)
    log.info("%s fetch OK: %s", source_id, res.get("verify_note"))

    hb.update(status=("unchanged" if unchanged else "ok"),
              rows=res.get("rows"), note=res.get("verify_note", "")[:400])

    agg = res.get("agg")
    needs_publish = agg and publish and (not unchanged or not prev_published)
    if needs_publish:
        from .publish import firestore  # lazy: no cred needed for --no-publish
        try:
            n = 0
            for collection, docs in agg.items():
                n += firestore.publish_docs(state, collection, docs)
            state_mod.record_published(state, source_id, n)
            hb["published_docs"] = n
        except firestore.QuotaDeferred as e:
            log.warning("%s: %s", source_id, e)
            hb.update(publish_deferred=str(e)[:200])
        except Exception as e:  # noqa: BLE001
            log.exception("%s publish FAILED", source_id)
            hb.update(publish_error=str(e)[:400])
            # fetch stays a success; the publish error must stay visible:
            s = state_mod.src(state, source_id)
            s["verify_note"] = (s.get("verify_note") or "") + \
                " | PUBLISH ERROR: " + str(e)[:200]
            state_mod.save(state)
    _heartbeat(state, source_id, hb, publish)
    return True


def _heartbeat(state, source_id, payload, publish):
    if not publish:
        return
    try:
        from .publish import firestore
        firestore.heartbeat(state, source_id, payload)
    except Exception as e:  # noqa: BLE001
        log.warning("heartbeat for %s failed: %s", source_id, str(e)[:200])


def due_sources(state, force=False):
    return [sid for sid, cfg in config.SOURCES.items()
            if state_mod.is_due(state, sid, cfg["cadence_h"], force=force)]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--once", action="store_true", help="run all due sources once")
    ap.add_argument("--daemon", action="store_true", help="continuous mode")
    ap.add_argument("--source", help="comma-separated source ids to run now")
    ap.add_argument("--force", action="store_true", help="ignore cadence")
    ap.add_argument("--no-publish", action="store_true",
                    help="fetch + save raw only; skip Firestore")
    ap.add_argument("--status", action="store_true", help="print state table")
    args = ap.parse_args()

    setup_logging()
    config.ensure_dirs()
    state = state_mod.load()
    publish = not args.no_publish

    if args.status:
        print(state_mod.render_state_table(state))
        return

    acquire_instance_lock()  # every mutating mode below needs exclusivity
    state = state_mod.load()  # reload now that we hold the lock

    if args.source:
        for sid in [s.strip() for s in args.source.split(",")]:
            if sid not in config.SOURCES:
                sys.exit("unknown source '{}'. Known: {}".format(
                    sid, ", ".join(config.SOURCES)))
            run_source(state, sid, publish=publish)
        return

    if args.once:
        for sid in due_sources(state, force=args.force):
            run_source(state, sid, publish=publish)
        print(state_mod.render_state_table(state))
        return

    if args.daemon:
        log.info("daemon starting; tick=%ss; Ctrl-C to stop",
                 config.DAEMON_TICK_SECONDS)
        stop = {"flag": False}

        def _sig(_n, _f):
            stop["flag"] = True
            log.info("signal received — finishing current source then exiting")

        signal.signal(signal.SIGINT, _sig)
        signal.signal(signal.SIGTERM, _sig)
        while not stop["flag"]:
            ran = False
            for sid in due_sources(state):
                if stop["flag"]:
                    break
                run_source(state, sid, publish=publish)
                ran = True
            if ran:
                log.info("tick complete; next check in %ss",
                         config.DAEMON_TICK_SECONDS)
            time.sleep(config.DAEMON_TICK_SECONDS)
        log.info("daemon stopped cleanly")
        return

    ap.print_help()


if __name__ == "__main__":
    main()
