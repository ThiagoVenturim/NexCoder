"""Signed authorization documents and cryptographic validation for target scanning and testing."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from pydantic import BaseModel, ConfigDict, Field

from nexcoder_control.approval.target_gate import (
    TargetNotAuthorizedError,
    normalize_target,
    redact_secrets,
)


def _decode_bytes(val: str | bytes) -> bytes:
    """Decode raw bytes from base64, hex, or return bytes as-is."""
    if isinstance(val, bytes):
        return val
    cleaned = val.strip()
    if len(cleaned) in (64, 128):
        try:
            return bytes.fromhex(cleaned)
        except ValueError:
            pass
    try:
        return base64.b64decode(cleaned)
    except Exception as exc:
        raise ValueError(f"Unable to decode key or signature bytes: {exc}") from exc


def generate_keypair() -> tuple[str, str]:
    """Generate a new Ed25519 keypair and return (private_key_b64, public_key_b64)."""
    priv = ed25519.Ed25519PrivateKey.generate()
    pub = priv.public_key()

    priv_raw = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_raw = pub.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    priv_b64 = base64.b64encode(priv_raw).decode("ascii")
    pub_b64 = base64.b64encode(pub_raw).decode("ascii")
    return priv_b64, pub_b64


def compute_scope_hash(scope: list[str]) -> str:
    """Compute deterministic SHA-256 hex digest of sorted normalized scope entries."""
    normalized = sorted(str(s).strip().lower() for s in scope if str(s).strip())
    payload = json.dumps(normalized, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def create_canonical_payload(
    target: str,
    scope_hash: str,
    authorized_by: str,
    contact: str,
    valid_from: datetime,
    valid_until: datetime,
) -> bytes:
    """Construct canonical UTF-8 bytes for cryptographic signing and verification."""
    from_iso = valid_from.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    until_iso = valid_until.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    norm_target = str(target).strip().lower()

    canonical = {
        "authorized_by": str(authorized_by).strip(),
        "contact": str(contact).strip().lower(),
        "scope_hash": str(scope_hash).strip().lower(),
        "target": norm_target,
        "valid_from": from_iso,
        "valid_until": until_iso,
    }
    return json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")


class AuthorizationDocument(BaseModel):
    """Cryptographically signed authorization document permitting target scanning/testing."""

    target: str = Field(alias="alvo")
    scope: list[str] = Field(default_factory=list, alias="escopo")
    authorized_by: str = Field(alias="autorizado_por")
    contact: str = Field(default="", alias="contato")
    valid_from: datetime = Field(alias="valido_de")
    valid_until: datetime = Field(alias="valido_ate")
    scope_hash: str = Field(default="", alias="hash_do_escopo")
    signature: str = Field(default="", alias="assinatura")
    public_key: str | None = Field(default=None, alias="chave_publica")
    algorithm: str = "ed25519"
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(populate_by_name=True)

    def to_dict(self) -> dict[str, Any]:
        """Export document as a clean dictionary with ISO-formatted timestamps."""
        data = self.model_dump(by_alias=False)
        data["valid_from"] = self.valid_from.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        data["valid_until"] = self.valid_until.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        return data

    def to_yaml(self) -> str:
        """Export document formatted as YAML."""
        return yaml.safe_dump(self.to_dict(), sort_keys=False)

    def to_json(self, indent: int = 2) -> str:
        """Export document formatted as JSON."""
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, path: str | Path) -> None:
        """Save authorization document to disk as YAML or JSON based on file extension."""
        p = Path(path)
        content = self.to_json() if p.suffix.lower() == ".json" else self.to_yaml()
        p.write_text(content, encoding="utf-8")


def sign_authorization_document(
    doc_data: dict[str, Any] | AuthorizationDocument,
    private_key: str | bytes | ed25519.Ed25519PrivateKey,
    public_key: str | bytes | None = None,
) -> AuthorizationDocument:
    """Sign an authorization document using Ed25519 and return a signed AuthorizationDocument."""
    if isinstance(doc_data, AuthorizationDocument):
        raw = doc_data.to_dict()
    else:
        raw = dict(doc_data)

    target = raw.get("target") or raw.get("alvo")
    if not target:
        raise ValueError("Document target cannot be empty")

    scope_val = raw.get("scope") or raw.get("escopo") or []
    if isinstance(scope_val, str):
        scope_list = [s.strip() for s in scope_val.split(",") if s.strip()]
    else:
        scope_list = [str(s).strip() for s in scope_val if str(s).strip()]

    authorized_by = raw.get("authorized_by") or raw.get("autorizado_por")
    if not authorized_by:
        raise ValueError("Document authorized_by cannot be empty")

    contact = raw.get("contact") or raw.get("contato") or ""

    v_from_raw = raw.get("valid_from") or raw.get("valido_de")
    v_until_raw = raw.get("valid_until") or raw.get("valido_ate")
    if not v_from_raw or not v_until_raw:
        raise ValueError("Document valid_from and valid_until dates are required")

    temp_doc = AuthorizationDocument(
        target=str(target),
        scope=scope_list,
        authorized_by=str(authorized_by),
        contact=str(contact),
        valid_from=v_from_raw,
        valid_until=v_until_raw,
    )

    if temp_doc.valid_from.tzinfo is None:
        temp_doc.valid_from = temp_doc.valid_from.replace(tzinfo=UTC)
    if temp_doc.valid_until.tzinfo is None:
        temp_doc.valid_until = temp_doc.valid_until.replace(tzinfo=UTC)

    computed_scope_hash = compute_scope_hash(temp_doc.scope)
    temp_doc.scope_hash = computed_scope_hash

    canonical_bytes = create_canonical_payload(
        target=temp_doc.target,
        scope_hash=computed_scope_hash,
        authorized_by=temp_doc.authorized_by,
        contact=temp_doc.contact,
        valid_from=temp_doc.valid_from,
        valid_until=temp_doc.valid_until,
    )

    if isinstance(private_key, ed25519.Ed25519PrivateKey):
        priv_obj = private_key
    else:
        priv_bytes = _decode_bytes(private_key)
        priv_obj = ed25519.Ed25519PrivateKey.from_private_bytes(priv_bytes)

    sig_bytes = priv_obj.sign(canonical_bytes)
    temp_doc.signature = base64.b64encode(sig_bytes).decode("ascii")

    if public_key is not None:
        if isinstance(public_key, bytes):
            temp_doc.public_key = base64.b64encode(public_key).decode("ascii")
        else:
            temp_doc.public_key = str(public_key).strip()
    else:
        pub_raw = priv_obj.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        temp_doc.public_key = base64.b64encode(pub_raw).decode("ascii")

    metadata = raw.get("metadata") or {}
    if isinstance(metadata, dict):
        temp_doc.metadata = redact_secrets(metadata)

    return temp_doc


def load_authorization_document(
    source: str | Path | dict[str, Any] | AuthorizationDocument,
) -> AuthorizationDocument:
    """Load and parse an AuthorizationDocument from a file path, YAML/JSON text, dict, or instance."""
    if isinstance(source, AuthorizationDocument):
        return source

    if isinstance(source, Path):
        content = source.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
        if not isinstance(data, dict):
            raise TargetNotAuthorizedError(
                "unknown",
                reason="Authorization document file does not contain a dictionary",
            )
        return AuthorizationDocument.model_validate(data)

    if isinstance(source, dict):
        return AuthorizationDocument.model_validate(source)

    if isinstance(source, str):
        trimmed = source.strip()
        p = Path(trimmed)
        if p.is_file():
            content = p.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
            if not isinstance(data, dict):
                raise TargetNotAuthorizedError(
                    "unknown",
                    reason=f"Authorization document at {p} is not a valid dictionary",
                )
            return AuthorizationDocument.model_validate(data)

        # Parse string directly as YAML or JSON
        data = yaml.safe_load(trimmed)
        if isinstance(data, dict):
            return AuthorizationDocument.model_validate(data)
        raise TargetNotAuthorizedError(
            "unknown",
            reason="Authorization document string could not be parsed as a dictionary",
        )

    raise TargetNotAuthorizedError(
        "unknown",
        reason=f"Unsupported authorization document source type: {type(source)}",
    )


def is_local_or_owned_target(target: str | Path) -> bool:
    """Check if target represents a local filesystem resource or loopback address."""
    if isinstance(target, Path):
        return True
    raw = str(target).strip()
    if not raw:
        return False
    parsed = urlparse(raw)
    if parsed.scheme in ("http", "https"):
        host = (parsed.hostname or "").lower()
        return host in ("localhost", "127.0.0.1", "::1", "0.0.0.0") or host.endswith(".local")  # noqa: S104
    if parsed.scheme in ("file", ""):
        return True
    return False


def verify_signed_document(
    doc: AuthorizationDocument | dict[str, Any] | str | Path,
    *,
    trusted_public_keys: list[str] | set[str] | None = None,
    target: str | Path | None = None,
    action: str | None = None,
    current_time: datetime | None = None,
) -> AuthorizationDocument:
    """Verify cryptographic signature, scope hash, target match, validity window, and scope coverage."""
    now = current_time or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    target_str = str(target) if target is not None else "unknown"

    try:
        document = load_authorization_document(doc)
    except Exception as exc:
        raise TargetNotAuthorizedError(
            target=target_str,
            reason=f"Failed to load authorization document: {exc}",
        ) from exc

    if document.valid_from.tzinfo is None:
        document.valid_from = document.valid_from.replace(tzinfo=UTC)
    if document.valid_until.tzinfo is None:
        document.valid_until = document.valid_until.replace(tzinfo=UTC)

    doc_target = document.target.strip()
    effective_target = target_str if target is not None else doc_target

    # 1. Verify scope hash integrity
    computed_hash = compute_scope_hash(document.scope)
    if document.scope_hash.lower() != computed_hash.lower():
        raise TargetNotAuthorizedError(
            target=effective_target,
            reason=(
                f"Authorization document scope hash mismatch: expected {computed_hash}, "
                f"found {document.scope_hash}. Scope tampering detected."
            ),
        )

    # 2. Verify validity window
    if now > document.valid_until:
        raise TargetNotAuthorizedError(
            target=effective_target,
            reason=(
                f"Authorization document expired at {document.valid_until.isoformat()} "
                f"(current time: {now.isoformat()})."
            ),
        )
    if now < document.valid_from:
        raise TargetNotAuthorizedError(
            target=effective_target,
            reason=(
                f"Authorization document is not yet valid until {document.valid_from.isoformat()} "
                f"(current time: {now.isoformat()})."
            ),
        )

    # 3. Verify target match
    if target is not None:
        norm_requested = normalize_target(target)
        norm_doc = normalize_target(document.target)
        matched = norm_requested == norm_doc
        if not matched:
            req_parsed = urlparse(norm_requested)
            doc_parsed = urlparse(norm_doc)
            if req_parsed.netloc and doc_parsed.netloc:
                matched = req_parsed.netloc.lower() == doc_parsed.netloc.lower()
            elif req_parsed.path and doc_parsed.path:
                matched = req_parsed.path.rstrip("/\\") == doc_parsed.path.rstrip("/\\")
        if not matched:
            raise TargetNotAuthorizedError(
                target=norm_requested,
                reason=(
                    f"Target mismatch in authorization document: document authorizes '{document.target}', "
                    f"but requested target is '{target}'."
                ),
            )

    # 4. Verify scope coverage
    if action is not None:
        act_clean = action.strip().lower()
        allowed_scopes = [s.strip().lower() for s in document.scope]
        scope_ok = (
            "*" in allowed_scopes
            or act_clean in allowed_scopes
            or any(s.endswith(":*") and act_clean.startswith(s[:-2]) for s in allowed_scopes)
        )
        if not scope_ok:
            raise TargetNotAuthorizedError(
                target=effective_target,
                mode=action,
                reason=(
                    f"Action '{action}' is not permitted by authorization document scope: {document.scope}."
                ),
            )

    # 5. Verify cryptographic signature
    if not document.signature:
        raise TargetNotAuthorizedError(
            target=effective_target,
            reason="Authorization document is missing cryptographic signature.",
        )

    sig_bytes = _decode_bytes(document.signature)
    canonical_bytes = create_canonical_payload(
        target=document.target,
        scope_hash=document.scope_hash,
        authorized_by=document.authorized_by,
        contact=document.contact,
        valid_from=document.valid_from,
        valid_until=document.valid_until,
    )

    trusted_set: set[str] = set()
    if trusted_public_keys:
        for k in trusted_public_keys:
            trusted_set.add(k.strip())

    candidate_keys: list[str] = []
    if trusted_set:
        if document.public_key:
            clean_pub = document.public_key.strip()
            if clean_pub not in trusted_set:
                raise TargetNotAuthorizedError(
                    target=effective_target,
                    reason=(
                        "Public key on authorization document is not present in the trusted public keys list."
                    ),
                )
            candidate_keys = [clean_pub]
        else:
            candidate_keys = list(trusted_set)
    else:
        if document.public_key:
            candidate_keys = [document.public_key.strip()]
        else:
            raise TargetNotAuthorizedError(
                target=effective_target,
                reason="No public key provided or configured to verify document signature.",
            )

    signature_valid = False
    for cand in candidate_keys:
        try:
            pub_bytes = _decode_bytes(cand)
            pub_obj = ed25519.Ed25519PublicKey.from_public_bytes(pub_bytes)
            pub_obj.verify(sig_bytes, canonical_bytes)
            signature_valid = True
            break
        except (InvalidSignature, ValueError):
            continue

    if not signature_valid:
        raise TargetNotAuthorizedError(
            target=effective_target,
            reason="Cryptographic signature verification failed for authorization document.",
        )

    return document
