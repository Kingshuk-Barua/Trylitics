"""Groq client for the GenAI layer.

Deliberately dependency-free (uses `requests`, already a pipeline dependency)
so nothing new is added to requirements for the demo path.

Model roles — different families on purpose, because the evaluation designs in
`MAI_UPLIFT_PLAN.md` §4 depend on it:

    G1_PROPOSE   llama-3.3-70b-versatile   Indian administrative-geography recall
    G1_VERIFY    openai/gpt-oss-120b       DIFFERENT family, so "two independent
                                           runs must agree" is a real cross-check
                                           rather than one model agreeing with
                                           itself at temperature 0
    G1_TIEBREAK  qwen/qwen3.6-27b          third family, only on disagreement
    G2_GENERATE  openai/gpt-oss-20b        698 calls, fastest text model
    G2_JUDGE     llama-3.3-70b-versatile   never the generator — a model must not
                                           blind-rate its own output

Every id is overridable by env (MAI_GROQ_MODEL_<ROLE>) and validated against the
live /models endpoint at startup, so a deprecation fails loudly instead of
silently falling back.

Credentials resolve through the repo's own convention: environment first (a
local .env is auto-loaded by pipeline.config), then Credentials/Groq.json.
"""
import json
import os
import random
import threading
import time

import requests

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline import config as _pipeline_config  # noqa: E402  (.env autoload)

API_BASE = "https://api.groq.com/openai/v1"

ROLES = {
    "G1_PROPOSE": "llama-3.3-70b-versatile",
    "G1_VERIFY": "openai/gpt-oss-120b",
    "G1_TIEBREAK": "qwen/qwen3.6-27b",
    "G2_GENERATE": "openai/gpt-oss-20b",
    "G2_JUDGE": "llama-3.3-70b-versatile",
}


# Declared alternates, used ONLY when the primary for a role has exhausted its
# per-day token allowance. This is not a downgrade path chosen for convenience:
# the role assignment above is part of the evaluation design (the verifier must
# be a different family from the proposer; the judge must never be the
# generator), so every alternate below preserves that property, and the model
# actually used is printed and recorded in the run artefacts.
ROLE_FALLBACKS = {
    "G1_PROPOSE": ["qwen/qwen3.6-27b", "openai/gpt-oss-120b"],
    "G1_VERIFY": ["qwen/qwen3.6-27b", "llama-3.3-70b-versatile"],
    "G1_TIEBREAK": ["openai/gpt-oss-120b", "llama-3.1-8b-instant"],
    "G2_GENERATE": ["llama-3.1-8b-instant", "openai/gpt-oss-safeguard-20b"],
    "G2_JUDGE": ["qwen/qwen3.6-27b", "openai/gpt-oss-120b"],
}


def api_keys():
    """Every key available, in preference order.

    Free-tier limits are per key per day, so a long run is more likely to be
    stopped by a daily allowance than by anything about the model. Supplying
    several keys (GROQ_API_KEY, then GROQ_API_KEY_2, _3, … or a comma-separated
    GROQ_API_KEYS) lets the run continue on the SAME model rather than
    silently changing the experiment.
    """
    keys = []
    multi = os.environ.get("GROQ_API_KEYS", "")
    keys += [k.strip() for k in multi.split(",") if k.strip()]
    for name in ["GROQ_API_KEY"] + ["GROQ_API_KEY_%d" % i for i in range(2, 9)]:
        k = os.environ.get(name)
        if k and k.strip():
            keys.append(k.strip())
    path = _pipeline_config.CREDENTIALS_DIR / "Groq.json"
    if path.is_file():
        with open(path) as f:
            blob = json.load(f)["groq"]
        for k in ([blob.get("api_key")] + list(blob.get("api_keys") or [])):
            if k:
                keys.append(k)
    seen, out = set(), []
    for k in keys:
        if k not in seen:
            seen.add(k)
            out.append(k)
    if not out:
        raise RuntimeError(
            "GROQ_API_KEY not set. Put it in .env (GROQ_API_KEY=gsk_...) or in "
            "Credentials/Groq.json as {\"groq\": {\"api_key\": \"gsk_...\"}}")
    return out


def api_key():
    return api_keys()[0]


def model_for(role):
    return os.environ.get("MAI_GROQ_MODEL_" + role) or ROLES[role]


def _extract_json(text):
    """Parse a JSON object out of a completion.

    `json_object` mode is looser than `json_schema`: some models still wrap the
    object in a markdown fence or add a leading sentence. Rather than fail the
    call, find the outermost balanced object.
    """
    if text is None:
        return None
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```")[1] if "```" in t[3:] else t[3:]
        if t.lstrip().lower().startswith("json"):
            t = t.lstrip()[4:]
    try:
        return json.loads(t)
    except (json.JSONDecodeError, ValueError):
        pass
    start = t.find("{")
    if start < 0:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(t)):
        ch = t[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(t[start:i + 1])
                except (json.JSONDecodeError, ValueError):
                    return None
    return None


class RateLimiter:
    """Token bucket. Groq's free tier is per-minute; a 429 storm wastes more
    time than pacing does."""

    def __init__(self, per_minute=25):
        self.interval = 60.0 / max(per_minute, 1)
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self):
        with self._lock:
            now = time.monotonic()
            if now < self._next:
                time.sleep(self._next - now)
                now = time.monotonic()
            self._next = now + self.interval


class GroqClient:
    def __init__(self, per_minute=25, timeout=90, max_retries=5):
        self.keys = api_keys()
        self.key_index = 0
        self.key = self.keys[0]
        # {role: model} once a daily limit has forced a declared alternate
        self.substitutions = {}
        self.exhausted = set()               # (key_index, model) pairs
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": "Bearer " + self.key,
            "Content-Type": "application/json",
            # urllib's default UA is blocked by Cloudflare (error 1010)
            "User-Agent": "TrilyticsMAI/2.0 (academic student project)",
        })
        self.limiter = RateLimiter(per_minute)
        self.timeout = timeout
        self.max_retries = max_retries
        self.calls = 0
        self.tokens_in = 0
        self.tokens_out = 0

    def _use_key(self, i):
        self.key_index = i
        self.key = self.keys[i]
        self.session.headers["Authorization"] = "Bearer " + self.key

    def _on_daily_exhaustion(self, role, model):
        """Rotate the KEY first, then the declared alternate MODEL.

        Order matters. A different key on the same model keeps the experiment
        identical; a different model does not. The substitution is returned so
        the caller can record it, and it is printed rather than swallowed.
        """
        self.exhausted.add((self.key_index, model))
        for i in range(len(self.keys)):
            if i != self.key_index and (i, model) not in self.exhausted:
                self._use_key(i)
                print("      [groq] daily limit on key #%d for %s — continuing "
                      "on key #%d, same model" % (self.key_index, model, i + 1))
                return model
        for alt in ROLE_FALLBACKS.get(role, []):
            if any((i, alt) not in self.exhausted for i in range(len(self.keys))):
                for i in range(len(self.keys)):
                    if (i, alt) not in self.exhausted:
                        self._use_key(i)
                        break
                self.substitutions[role] = alt
                print("      [groq] every key exhausted for %s — role %s falls "
                      "back to its DECLARED alternate %s (recorded in the run "
                      "artefacts)" % (model, role, alt))
                return alt
        raise RuntimeError(
            "groq daily token limit reached for role %s on %s and on every "
            "declared alternate %s, across all %d key(s). Add another key "
            "(GROQ_API_KEY_2=... in .env) or wait for the daily reset."
            % (role, model, ROLE_FALLBACKS.get(role, []), len(self.keys)))

    def model_for_role(self, role):
        """The model this client is actually using for a role right now —
        the configured one, unless a daily limit forced a declared alternate."""
        return self.substitutions.get(role) or model_for(role)

    def available_models(self):
        r = self.session.get(API_BASE + "/models", timeout=self.timeout)
        r.raise_for_status()
        return sorted(m["id"] for m in r.json()["data"])

    def validate_roles(self, roles=None):
        live = set(self.available_models())
        missing = {}
        for role in (roles or ROLES):
            m = model_for(role)
            if m not in live:
                missing[role] = m
        if missing:
            raise RuntimeError(
                "these role models are not live on Groq: %s\nlive: %s"
                % (missing, sorted(live)))
        return {role: model_for(role) for role in (roles or ROLES)}

    # Not every Groq model supports strict `json_schema` response_format —
    # llama-3.3-70b-versatile returns 400 for it but does support `json_object`.
    # Detected once per model, then cached, so a capability difference between
    # families never becomes a silent behavioural difference.
    _schema_support = {}

    def chat(self, role, system, user, temperature=0.0, json_schema=None,
             max_tokens=1024, reasoning_effort=None):
        """One completion. Returns parsed JSON when json_schema is given.

        `max_tokens` is not free: Groq charges the REQUESTED completion budget
        against the per-model tokens-per-minute limit, not the tokens actually
        produced. gpt-oss-20b allows 8,000 TPM on the free tier, so asking for
        2,000 tokens to write a 90-word paragraph caps throughput at ~3 calls
        a minute and spends most of the run in 429 backoff. Ask for what the
        task needs.

        `reasoning_effort` ("low"/"medium"/"high") applies to the gpt-oss and
        qwen3 families. Low effort is right for composition tasks: the reasoning
        trace is billed, counts against the same budget, and its absence is
        what stops the model truncating mid-JSON.
        """
        model = self.model_for_role(role)
        strict = self._schema_support.get(model, True) and json_schema is not None

        if json_schema is not None and not strict:
            # json_object mode: the schema goes in the prompt and we validate.
            system = (system + "\n\nReturn ONLY a JSON object matching this "
                      "schema exactly (no prose, no markdown fence):\n"
                      + json.dumps(json_schema))

        payload = {
            "model": model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "temperature": temperature,
            "max_completion_tokens": max_tokens,
        }
        # Only the gpt-oss family accepts a graded reasoning_effort. qwen3.6-27b
        # rejects anything but `none`/`default` with a 400, so it must never be
        # sent the "low"/"medium"/"high" values the composition tasks use.
        if reasoning_effort and "gpt-oss" in model:
            payload["reasoning_effort"] = reasoning_effort
        if json_schema is not None:
            payload["response_format"] = (
                {"type": "json_schema",
                 "json_schema": {"name": "response", "strict": True,
                                 "schema": json_schema}}
                if strict else {"type": "json_object"})

        last = None
        for attempt in range(self.max_retries):
            self.limiter.wait()
            try:
                r = self.session.post(API_BASE + "/chat/completions",
                                      json=payload, timeout=self.timeout)
            except requests.RequestException as e:       # transport blip
                last = e
                time.sleep(min(2 ** attempt + random.random(), 30))
                continue
            if r.status_code == 429:
                # Per-DAY exhaustion is not a pacing problem and no amount of
                # backoff fixes it. Fail immediately and loudly so the caller
                # can switch models, instead of spending five minutes asleep
                # per item discovering the same thing.
                low429 = r.text.lower()
                if "per day" in low429 or "(tpd)" in low429 or "(rpd)" in low429:
                    self._on_daily_exhaustion(role, model)
                    return self.chat(role, system, user, temperature,
                                     json_schema, max_tokens, reasoning_effort)
                wait = float(r.headers.get("retry-after") or
                             (2 ** attempt + random.random()))
                time.sleep(min(wait, 60))
                last = RuntimeError("429 rate limited")
                continue
            if r.status_code >= 500:
                last = RuntimeError("%d %s" % (r.status_code, r.text[:200]))
                time.sleep(min(2 ** attempt + random.random(), 30))
                continue
            if not r.ok:
                # Reasoning models (gpt-oss-*, qwen3.x) spend part of
                # max_completion_tokens on hidden reasoning, so a budget that
                # is ample for a non-reasoning model truncates them mid-JSON.
                # Grow the budget rather than dropping the item.
                if (r.status_code == 400
                        and "max completion tokens reached" in r.text
                        and max_tokens < 8000):
                    return self.chat(role, system, user, temperature,
                                     json_schema, max_tokens * 3,
                                     reasoning_effort)
                # Two distinct strict-mode failures, both of which mean "this
                # model cannot honour json_schema for this request":
                #   400 ... json_schema ...            the model rejects the
                #                                      response_format outright
                #   400 Failed to validate JSON        the model was accepted
                #     / failed_generation              but its own output does
                #                                      not satisfy the schema
                # gpt-oss-20b produces the second on every call. Downgrading to
                # json_object keeps the schema in the system prompt and lets
                # _extract_json + the numeric verifier do the enforcing, which
                # is where enforcement actually belongs for this task.
                low = r.text.lower()
                if (r.status_code == 400 and strict
                        and ("json_schema" in low
                             or "failed to validate json" in low
                             or "failed_generation" in low)):
                    self._schema_support[model] = False
                    return self.chat(role, system, user, temperature,
                                     json_schema, max_tokens, reasoning_effort)
                # other 400s are our fault — do not retry blindly
                raise RuntimeError("groq %d for %s: %s"
                                   % (r.status_code, model, r.text[:400]))
            body = r.json()
            self.calls += 1
            usage = body.get("usage") or {}
            self.tokens_in += usage.get("prompt_tokens", 0)
            self.tokens_out += usage.get("completion_tokens", 0)
            text = body["choices"][0]["message"]["content"]
            if json_schema is None:
                return text
            parsed = _extract_json(text)
            if parsed is not None:
                return parsed
            last = RuntimeError("model returned non-JSON: %r" % text[:200])
            continue
        raise RuntimeError("groq call failed after %d attempts (%s): %s"
                           % (self.max_retries, model, last))

    def stats(self):
        out = {"calls": self.calls, "prompt_tokens": self.tokens_in,
               "completion_tokens": self.tokens_out,
               "keys_available": len(self.keys), "key_used": self.key_index + 1}
        if self.substitutions:
            out["model_substitutions"] = dict(self.substitutions)
        return out
