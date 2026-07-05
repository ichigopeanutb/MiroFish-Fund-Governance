"""Private-beta access registry for the fund-governance demo.

The registry is intentionally file-backed for the alpha release so real access
codes can live outside git while the repo still contains the management logic.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


HASH_ITERATIONS = 240_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    if len(raw) == 10:
        raw = f"{raw}T23:59:59+00:00"
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _empty_registry() -> dict:
    return {
        "schema_version": "0.1",
        "registry_type": "business_demo_access_registry",
        "created_at": _now(),
        "updated_at": _now(),
        "codes": [],
        "audit_log": [],
    }


def hash_access_code(code: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        code.encode("utf-8"),
        salt.encode("utf-8"),
        HASH_ITERATIONS,
    ).hex()
    return f"pbkdf2_sha256${HASH_ITERATIONS}${salt}${digest}"


def verify_access_code(code: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt, expected = stored_hash.split("$", 3)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        code.encode("utf-8"),
        salt.encode("utf-8"),
        int(iterations),
    ).hex()
    return hmac.compare_digest(digest, expected)


def generate_access_code(group: str = "BETA") -> str:
    prefix = "".join(ch for ch in group.upper().replace(" ", "_") if ch.isalnum() or ch == "_")
    prefix = prefix[:18] or "BETA"
    return f"{prefix}_{secrets.token_urlsafe(12).replace('-', '').replace('_', '')[:14]}"


class BusinessDemoAccessRegistry:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def exists(self) -> bool:
        return self.path.exists()

    def read(self) -> dict:
        if not self.path.exists():
            return _empty_registry()
        return json.loads(self.path.read_text(encoding="utf-8"))

    def write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data["updated_at"] = _now()
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def has_codes(self) -> bool:
        return bool(self.read().get("codes"))

    def public_summary(self) -> dict:
        data = self.read()
        codes = data.get("codes", [])
        active_count = sum(1 for item in codes if item.get("status") == "active")
        return {
            "schema_version": data.get("schema_version", "0.1"),
            "registry_path": str(self.path),
            "code_count": len(codes),
            "active_count": active_count,
            "updated_at": data.get("updated_at"),
        }

    def list_codes(self) -> list[dict]:
        rows = []
        for item in self.read().get("codes", []):
            rows.append(self._redact_code(item))
        return rows

    def create_code(self, payload: dict, actor: str = "owner") -> dict:
        data = self.read()
        code = (payload.get("code") or "").strip() or generate_access_code(payload.get("group", "BETA"))
        now = _now()
        item = {
            "code_id": f"code_{uuid4().hex[:12]}",
            "label": (payload.get("label") or "Private beta tester").strip(),
            "group": (payload.get("group") or "private_beta").strip(),
            "status": payload.get("status") or "active",
            "scopes": _normalize_scopes(payload.get("scopes")),
            "expires_at": (payload.get("expires_at") or "").strip(),
            "code_hash": hash_access_code(code),
            "created_at": now,
            "updated_at": now,
            "last_used_at": "",
            "uses": 0,
        }
        data.setdefault("codes", []).append(item)
        self._append_audit(data, "code_created", item, actor=actor, status="ok")
        self.write(data)
        redacted = self._redact_code(item)
        redacted["display_once_code"] = code
        return redacted

    def update_code(self, code_id: str, payload: dict, actor: str = "owner") -> dict | None:
        data = self.read()
        for item in data.get("codes", []):
            if item.get("code_id") != code_id:
                continue
            for key in ("label", "group", "status", "expires_at"):
                if key in payload:
                    item[key] = (payload.get(key) or "").strip()
            if "scopes" in payload:
                item["scopes"] = _normalize_scopes(payload.get("scopes"))
            item["updated_at"] = _now()
            self._append_audit(data, "code_updated", item, actor=actor, status="ok")
            self.write(data)
            return self._redact_code(item)
        return None

    def verify(self, code: str, required_scope: str = "demo", request_meta: dict | None = None) -> dict:
        raw_code = (code or "").strip()
        data = self.read()
        for item in data.get("codes", []):
            if not verify_access_code(raw_code, item.get("code_hash", "")):
                continue
            status = self._eligibility(item, required_scope)
            if not status["allowed"]:
                self._append_audit(data, "access_denied", item, status=status["reason"], request_meta=request_meta)
                self.write(data)
                return {"allowed": False, "reason": status["reason"], "code": self._redact_code(item)}
            item["last_used_at"] = _now()
            item["uses"] = int(item.get("uses") or 0) + 1
            self._append_audit(data, "access_granted", item, status="ok", request_meta=request_meta)
            self.write(data)
            return {"allowed": True, "reason": "ok", "code": self._redact_code(item)}
        self._append_audit(data, "access_denied", None, status="unknown_code", request_meta=request_meta)
        self.write(data)
        return {"allowed": False, "reason": "unknown_code", "code": None}

    def audit_log(self, limit: int = 50) -> list[dict]:
        rows = self.read().get("audit_log", [])
        return rows[-limit:][::-1]

    def _eligibility(self, item: dict, required_scope: str) -> dict:
        if item.get("status") != "active":
            return {"allowed": False, "reason": "disabled"}
        expires_at = _parse_time(item.get("expires_at"))
        if expires_at and expires_at < datetime.now(timezone.utc):
            return {"allowed": False, "reason": "expired"}
        scopes = set(item.get("scopes") or ["demo"])
        if "all" not in scopes and required_scope not in scopes and "demo" not in scopes:
            return {"allowed": False, "reason": "scope_not_allowed"}
        return {"allowed": True, "reason": "ok"}

    def _redact_code(self, item: dict) -> dict:
        return {
            "code_id": item.get("code_id"),
            "label": item.get("label"),
            "group": item.get("group"),
            "status": item.get("status"),
            "scopes": item.get("scopes") or [],
            "expires_at": item.get("expires_at") or "",
            "created_at": item.get("created_at") or "",
            "updated_at": item.get("updated_at") or "",
            "last_used_at": item.get("last_used_at") or "",
            "uses": int(item.get("uses") or 0),
        }

    def _append_audit(
        self,
        data: dict,
        action: str,
        item: dict | None,
        actor: str = "access_code",
        status: str = "ok",
        request_meta: dict | None = None,
    ) -> None:
        data.setdefault("audit_log", []).append({
            "event_id": f"evt_{uuid4().hex[:12]}",
            "created_at": _now(),
            "action": action,
            "status": status,
            "actor": actor,
            "code_id": item.get("code_id") if item else "",
            "label": item.get("label") if item else "",
            "group": item.get("group") if item else "",
            "request": request_meta or {},
        })
        data["audit_log"] = data["audit_log"][-500:]


def _normalize_scopes(value) -> list[str]:
    if isinstance(value, str):
        raw_items = [item.strip() for item in value.split(",")]
    elif isinstance(value, list):
        raw_items = [str(item).strip() for item in value]
    else:
        raw_items = ["demo"]
    scopes = [item for item in raw_items if item]
    return scopes or ["demo"]
