"""Local web app for the compiled renal treatment query index."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import mimetypes
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from email.utils import format_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse, urlsplit, urlunparse

from query_treatment_index import (
    DEFAULT_COMPILED_DIR,
    SECTION_LABELS_CN,
    SECTION_ORDER,
    compact_text,
    empty_intent_message,
    find_registry_matches,
    load_display_translations,
    query_treatment,
    render_markdown,
    slim_card,
)


APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
API_CONTRACT_ID = "renal_treatment_query_api"
API_CONTRACT_VERSION = "1.0.0"
PUBLIC_COMPILED_FILENAMES = [
    "manifest.json",
    "disease_registry.json",
    "diseases.json",
    "treatment_cards.json",
    "evidence.json",
    "payer.json",
    "search_index.json",
]
PUBLIC_EVIDENCE_FIELDS = [
    "disease_key",
    "study_id",
    "study_name",
    "title",
    "year",
    "journal",
    "pmid",
    "doi",
    "evidence_tier",
    "study_design",
    "population",
    "intervention",
    "comparator",
    "primary_endpoint",
    "result_summary",
    "safety_summary",
    "treatment_impact",
    "structured_summary_cn",
    "linked_regimen_ids",
    "randomized",
]
PUBLIC_PAYER_FIELDS = [
    "disease_key",
    "drug_id",
    "jurisdiction",
    "payer_status",
    "payer_scope_summary",
    "local_caveat",
    "check_date",
]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_domain(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if not value:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    return [str(value)]


def safe_int(value: str | None, default: int, minimum: int = 1, maximum: int = 500) -> int:
    try:
        parsed = int(value or "")
    except ValueError:
        return default
    return max(minimum, min(maximum, parsed))


def env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def public_row(row: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    return {field: row.get(field) for field in fields if field in row and row.get(field) is not None}


def remote_data_base_url() -> str:
    return (
        os.environ.get("COMPILED_DATA_URL_BASE")
        or os.environ.get("RENAL_TREATMENT_DATA_BASE_URL")
        or os.environ.get("OSS_DATA_BASE_URL")
        or ""
    ).strip()


def compiled_data_oss_prefix() -> str:
    return (
        os.environ.get("COMPILED_DATA_OSS_PREFIX")
        or os.environ.get("RENAL_TREATMENT_OSS_PREFIX")
        or ""
    ).strip().strip("/")


def aliyun_oss_missing_required_values() -> list[str]:
    required = {
        "ALIYUN_OSS_ACCESS_KEY_ID": os.environ.get("ALIYUN_OSS_ACCESS_KEY_ID", "").strip(),
        "ALIYUN_OSS_ACCESS_KEY_SECRET": os.environ.get("ALIYUN_OSS_ACCESS_KEY_SECRET", "").strip(),
        "ALIYUN_OSS_REGION": os.environ.get("ALIYUN_OSS_REGION", "").strip(),
        "ALIYUN_OSS_BUCKET": os.environ.get("ALIYUN_OSS_BUCKET", "").strip(),
        "COMPILED_DATA_OSS_PREFIX": compiled_data_oss_prefix(),
    }
    return [key for key, value in required.items() if not value]


def aliyun_oss_config_is_complete() -> bool:
    return not aliyun_oss_missing_required_values()


def aliyun_oss_config_has_partial_values() -> bool:
    values = [
        os.environ.get("ALIYUN_OSS_ACCESS_KEY_ID", "").strip(),
        os.environ.get("ALIYUN_OSS_ACCESS_KEY_SECRET", "").strip(),
        os.environ.get("ALIYUN_OSS_SECURITY_TOKEN", "").strip(),
        os.environ.get("ALIYUN_OSS_REGION", "").strip(),
        os.environ.get("ALIYUN_OSS_BUCKET", "").strip(),
        compiled_data_oss_prefix(),
    ]
    return any(values) and not aliyun_oss_config_is_complete()


def remote_data_source() -> str:
    if remote_data_base_url():
        return "remote_oss_url"
    if aliyun_oss_config_is_complete():
        return "remote_oss_signed"
    return "local_compiled"


def sync_remote_compiled_data(compiled_dir: Path) -> None:
    base_url = remote_data_base_url()
    if base_url:
        compiled_dir.mkdir(parents=True, exist_ok=True)
        for filename in PUBLIC_COMPILED_FILENAMES:
            url = f"{base_url.rstrip('/')}/{filename}"
            data = fetch_remote_bytes(url=url)
            write_synced_file(compiled_dir, filename, data)
        return

    if aliyun_oss_config_has_partial_values():
        missing = ", ".join(aliyun_oss_missing_required_values())
        raise RuntimeError(f"Incomplete Aliyun OSS data source configuration; missing: {missing}")

    if not aliyun_oss_config_is_complete():
        return

    compiled_dir.mkdir(parents=True, exist_ok=True)
    for filename in PUBLIC_COMPILED_FILENAMES:
        url, headers = build_aliyun_oss_get_request(filename)
        data = fetch_remote_bytes(url=url, headers=headers)
        write_synced_file(compiled_dir, filename, data)


def fetch_remote_bytes(url: str, headers: dict[str, str] | None = None) -> bytes:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.read()
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to fetch public data file from OSS: {url}") from exc


def write_synced_file(compiled_dir: Path, filename: str, data: bytes) -> None:
    target = compiled_dir / filename
    tmp_target = compiled_dir / f".{filename}.tmp"
    tmp_target.write_bytes(data)
    tmp_target.replace(target)


def build_aliyun_oss_get_request(filename: str) -> tuple[str, dict[str, str]]:
    region = os.environ["ALIYUN_OSS_REGION"].strip()
    bucket = os.environ["ALIYUN_OSS_BUCKET"].strip()
    endpoint = os.environ.get("ALIYUN_OSS_ENDPOINT", "").strip() or f"https://oss-{region}.aliyuncs.com"
    object_key = f"{compiled_data_oss_prefix()}/{filename}"
    url = build_aliyun_oss_object_url(endpoint, bucket, object_key)
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    headers = {
        "Date": format_datetime(now, usegmt=True),
        "x-oss-content-sha256": "UNSIGNED-PAYLOAD",
        "x-oss-date": timestamp,
    }
    security_token = os.environ.get("ALIYUN_OSS_SECURITY_TOKEN", "").strip()
    if security_token:
        headers["x-oss-security-token"] = security_token
    headers["Authorization"] = build_aliyun_oss_v4_authorization(
        method="GET",
        canonical_uri=aliyun_oss_uri_encode(f"/{bucket}/{object_key}", encode_slash=False),
        canonical_query="",
        headers=headers,
        additional_header_names=[],
        payload_hash="UNSIGNED-PAYLOAD",
        access_key_id=os.environ["ALIYUN_OSS_ACCESS_KEY_ID"].strip(),
        access_key_secret=os.environ["ALIYUN_OSS_ACCESS_KEY_SECRET"].strip(),
        region=region,
        timestamp=timestamp,
    )
    return url, headers


def build_aliyun_oss_object_url(endpoint: str, bucket: str, object_key: str) -> str:
    parsed = urlsplit(endpoint.strip().rstrip("/"))
    if not parsed.scheme:
        parsed = urlsplit(f"https://{endpoint.strip().rstrip('/')}")
    if not parsed.netloc:
        raise ValueError("ALIYUN_OSS_ENDPOINT must include a valid host")
    host = parsed.netloc
    netloc = host if host == bucket or host.startswith(f"{bucket}.") else f"{bucket}.{host}"
    path = "/" + aliyun_oss_uri_encode(object_key, encode_slash=False)
    return urlunparse((parsed.scheme or "https", netloc, path, "", "", ""))


def build_aliyun_oss_v4_authorization(
    *,
    method: str,
    canonical_uri: str,
    canonical_query: str,
    headers: dict[str, str],
    additional_header_names: list[str],
    payload_hash: str,
    access_key_id: str,
    access_key_secret: str,
    region: str,
    timestamp: str,
) -> str:
    date = timestamp[:8]
    additional_header_names = sorted({name.lower() for name in additional_header_names})
    lower_headers = {name.lower(): normalize_aliyun_oss_header_value(value) for name, value in headers.items()}
    signed_header_names = sorted(
        name
        for name in lower_headers
        if name.startswith("x-oss-")
        or name in {"content-type", "content-md5"}
        or name in additional_header_names
    )
    canonical_headers = "".join(f"{name}:{lower_headers[name]}\n" for name in signed_header_names)
    canonical_additional_headers = ";".join(additional_header_names)
    canonical_request = (
        f"{method.upper()}\n"
        f"{canonical_uri}\n"
        f"{canonical_query}\n"
        f"{canonical_headers}\n"
        f"{canonical_additional_headers}\n"
        f"{payload_hash}"
    )
    hashed_request = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    scope = f"{date}/{region}/oss/aliyun_v4_request"
    string_to_sign = f"OSS4-HMAC-SHA256\n{timestamp}\n{scope}\n{hashed_request}"
    signing_key = aliyun_oss_v4_signing_key(access_key_secret, date, region)
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    authorization = f"OSS4-HMAC-SHA256 Credential={access_key_id}/{scope}"
    if canonical_additional_headers:
        authorization += f",AdditionalHeaders={canonical_additional_headers}"
    return f"{authorization},Signature={signature}"


def aliyun_oss_v4_signing_key(access_key_secret: str, date: str, region: str) -> bytes:
    key = hmac.new(f"aliyun_v4{access_key_secret}".encode("utf-8"), date.encode("utf-8"), hashlib.sha256).digest()
    key = hmac.new(key, region.encode("utf-8"), hashlib.sha256).digest()
    key = hmac.new(key, b"oss", hashlib.sha256).digest()
    return hmac.new(key, b"aliyun_v4_request", hashlib.sha256).digest()


def aliyun_oss_uri_encode(value: str, encode_slash: bool) -> str:
    safe = "-_.~" if encode_slash else "/-_.~"
    return quote(value, safe=safe)


def normalize_aliyun_oss_header_value(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


class TreatmentCatalog:
    def __init__(self, compiled_dir: Path = DEFAULT_COMPILED_DIR, public_mode: bool = False) -> None:
        self.compiled_dir = compiled_dir
        self.public_mode = public_mode
        self.load()

    def load(self) -> None:
        sync_remote_compiled_data(self.compiled_dir)
        if not self.compiled_dir.exists():
            raise FileNotFoundError(f"Compiled directory not found: {self.compiled_dir}")

        self.manifest = load_json(self.compiled_dir / "manifest.json")
        self.registry = load_json(self.compiled_dir / "disease_registry.json")
        self.diseases = load_json(self.compiled_dir / "diseases.json")
        self.cards = load_json(self.compiled_dir / "treatment_cards.json")
        self.evidence = load_json(self.compiled_dir / "evidence.json")
        self.payer = load_json(self.compiled_dir / "payer.json")
        self.search_index = load_json(self.compiled_dir / "search_index.json")
        self.display_translations = load_display_translations(self.compiled_dir)

        self.diseases_by_key = {row["disease_key"]: row for row in self.diseases}
        self.registry_by_id = {row["registry_id"]: row for row in self.registry}
        self.cards_by_id = {row["card_id"]: row for row in self.cards}
        self.cards_by_disease: dict[str, list[dict[str, Any]]] = {}
        for card in self.cards:
            self.cards_by_disease.setdefault(card["disease_key"], []).append(card)

    def health(self) -> dict[str, Any]:
        counts = dict(self.manifest.get("counts") or {})
        return {
            "ok": True,
            "mode": "public" if self.public_mode else "internal",
            "compiled_dir": "compiled_public" if self.public_mode else str(self.compiled_dir),
            "data_source": remote_data_source(),
            "schema_id": self.manifest.get("schema_id"),
            "generated_at": self.manifest.get("generated_at"),
            "api_contract": {
                "id": API_CONTRACT_ID,
                "version": API_CONTRACT_VERSION,
                "language": "zh-CN",
            },
            "counts": counts,
            "disease_count": len(self.registry),
            "card_count": len(self.cards),
            "section_labels": SECTION_LABELS_CN,
        }

    def disease_summary(self, registry_row: dict[str, Any]) -> dict[str, Any]:
        key = registry_row.get("disease_key") or registry_row.get("treatment_module")
        disease = self.diseases_by_key.get(key, {})
        cards = self.cards_by_disease.get(key, [])
        section_counts: dict[str, int] = {}
        for card in cards:
            sections = card.get("query_sections") or ["special_scenarios"]
            section = min(sections, key=lambda item: SECTION_ORDER.get(item, 99))
            section_counts[section] = section_counts.get(section, 0) + 1

        summary = {
            "disease_key": key,
            "registry_id": registry_row.get("registry_id"),
            "requested_name": registry_row.get("requested_name"),
            "name_cn": disease.get("name_cn") or registry_row.get("requested_name"),
            "name_en": disease.get("name_en"),
            "aliases": registry_row.get("query_aliases") or disease.get("aliases") or [],
            "domain": parse_domain(registry_row.get("domain")) or disease.get("kidney_category") or [],
            "coverage_status": registry_row.get("coverage_status"),
            "is_query_ready": bool(registry_row.get("is_compiled_query_ready")),
            "has_immunosuppressive_treatment": disease.get("has_immunosuppressive_treatment"),
            "immunosuppressive_treatment_role": disease.get("immunosuppressive_treatment_role"),
            "card_count": len(cards),
            "section_counts": section_counts,
            "clinical_counts": disease.get("clinical_counts") or {},
        }
        if not self.public_mode:
            summary["qa_summary"] = disease.get("qa_summary") or {}
            summary["match_score"] = registry_row.get("match_score")
        return summary

    def list_diseases(self, query: str = "", limit: int = 120) -> list[dict[str, Any]]:
        if query.strip():
            rows = find_registry_matches(
                query,
                self.registry,
                limit=limit,
                diseases_by_key=self.diseases_by_key,
            )
        else:
            rows = sorted(self.registry, key=lambda row: str(row.get("requested_name") or row.get("registry_id")))
            rows = rows[:limit]
        return [self.disease_summary(row) for row in rows]

    def query(self, text: str, limit_cards: int | None = None) -> dict[str, Any]:
        result = query_treatment(
            text,
            self.compiled_dir,
            card_limit_per_module=limit_cards,
        )
        selected_key = None
        if result["matches"]:
            modules = result["matches"][0].get("treatment_modules") or []
            selected_key = modules[0] if modules else result["matches"][0].get("treatment_module")
        selected_disease = (
            self.disease_summary(self.registry_by_id[selected_key])
            if selected_key in self.registry_by_id
            else None
        )
        markdown = render_markdown(result)
        contract_payload = self.query_contract(
            text=text,
            result=result,
            selected_key=selected_key,
            selected_disease=selected_disease,
            markdown=markdown,
            limit_cards=limit_cards,
        )
        if self.public_mode:
            return contract_payload
        return {
            **contract_payload,
            # Backward-compatible fields used by the first UI.
            "query": text,
            "selected_disease": selected_disease,
            "result": result,
            "markdown": markdown,
        }

    def query_contract(
        self,
        text: str,
        result: dict[str, Any],
        selected_key: str | None,
        selected_disease: dict[str, Any] | None,
        markdown: str,
        limit_cards: int | None,
    ) -> dict[str, Any]:
        warnings: list[dict[str, Any]] = []
        matches = result.get("matches") or []
        route_matches = matches
        if self.public_mode:
            route_matches = [
                {key: value for key, value in row.items() if key != "match_score"}
                for row in matches
            ]
        matched = bool(matches)
        if not matched:
            warnings.append(
                {
                    "code": "no_registry_match",
                    "message": "未匹配到 query-ready 病种入口。",
                    "severity": "info",
                }
            )

        modules: list[dict[str, Any]] = []
        flat_cards: list[dict[str, Any]] = []
        for module in result.get("modules") or []:
            module_key = module.get("module_key")
            module_summary = (
                self.disease_summary(self.registry_by_id[module_key])
                if module_key in self.registry_by_id
                else {
                    "disease_key": module_key,
                    "registry_id": module_key,
                    "name_cn": (self.diseases_by_key.get(module_key) or {}).get("name_cn"),
                }
            )
            section_payloads: list[dict[str, Any]] = []
            for section in module.get("sections") or []:
                section_key = section.get("query_section")
                label = section.get("label_cn") or SECTION_LABELS_CN.get(section_key, section_key)
                section_cards = []
                for card in section.get("cards") or []:
                    card_payload = {
                        **card,
                        "module_key": module_key,
                        "query_section": section_key,
                        "section_label_cn": label,
                    }
                    section_cards.append(card_payload)
                    flat_cards.append(card_payload)
                section_payloads.append(
                    {
                        "section_key": section_key,
                        "query_section": section_key,
                        "label_cn": label,
                        "card_count": len(section_cards),
                        "cards": section_cards,
                    }
                )
            empty_message = None
            if not section_payloads:
                empty_message = empty_intent_message(result, module)
                warnings.append(
                    {
                        "code": "no_cards_for_intent",
                        "message": empty_message,
                        "severity": "info",
                        "module_key": module_key,
                    }
                )
            modules.append(
                {
                    "module_key": module_key,
                    "disease": module_summary,
                    "card_count_total": module.get("card_count", 0),
                    "card_count_visible": module.get("filtered_card_count", 0),
                    "available_sections": [
                        {
                            "section_key": section,
                            "label_cn": SECTION_LABELS_CN.get(section, section),
                        }
                        for section in module.get("available_sections") or []
                    ],
                    "sections": section_payloads,
                    "empty_message": empty_message,
                }
            )

        related_endpoints = {}
        if selected_key:
            related_endpoints = {
                "disease_detail": f"/api/diseases/{selected_key}",
                "evidence": f"/api/evidence?disease={selected_key}",
                "payer": f"/api/payer?disease={selected_key}",
            }
        payload = {
            "contract": {
                "id": API_CONTRACT_ID,
                "version": API_CONTRACT_VERSION,
                "language": "zh-CN",
                "schema_id": self.manifest.get("schema_id"),
                "schema_version": self.manifest.get("schema_version"),
                "compiled_build_date": self.manifest.get("build_date"),
            },
            "query_context": {
                "text": text,
                "detected_intents": result.get("detected_intents") or [],
                "detected_intent_labels": result.get("detected_intent_labels") or [],
                "card_limit_per_module": limit_cards,
            },
            "route": {
                "matched": matched,
                "selected_registry": result.get("selected_registry"),
                "selected_disease_key": selected_key,
                "is_fanout": bool(result.get("is_fanout")),
                "matches": route_matches,
            },
            "disease": selected_disease,
            "modules": modules,
            "cards": flat_cards,
            "counts": {
                "matched_registry_count": len(matches),
                "module_count": len(modules),
                "visible_card_count": len(flat_cards),
                "total_module_card_count": sum(module.get("card_count_total", 0) for module in modules),
                "registry_total": len(self.registry),
                "treatment_card_total": len(self.cards),
            },
            "warnings": warnings,
            "related_endpoints": related_endpoints,
        }
        if not self.public_mode:
            payload["rendered"] = {
                "markdown": markdown,
            }
        return payload

    def disease_detail(self, disease_key: str) -> dict[str, Any] | None:
        key = disease_key.strip()
        if key not in self.diseases_by_key:
            return None
        registry_row = self.registry_by_id.get(key)
        query_result = query_treatment(key, self.compiled_dir)
        detail = {
            "summary": self.disease_summary(registry_row or {"registry_id": key, "disease_key": key}),
            "query_result": query_result,
            "evidence_count": len(self.evidence_for_disease(key)),
            "payer_count": len(self.payer_for_disease(key)),
        }
        if not self.public_mode:
            detail["disease"] = self.diseases_by_key[key]
        return detail

    def card_detail(self, card_id: str) -> dict[str, Any] | None:
        card = self.cards_by_id.get(card_id)
        if not card:
            return None
        drug_ids = set(card.get("drug_ids") or [])
        disease_key = card.get("disease_key")
        payer_rows = [
            row
            for row in self.payer
            if row.get("disease_key") == disease_key and row.get("drug_id") in drug_ids
        ]
        display = slim_card(card, self.display_translations)
        if self.public_mode:
            return {
                "card": display,
                "display": display,
                "payer": [public_row(row, PUBLIC_PAYER_FIELDS) for row in payer_rows],
            }
        return {
            "card": card,
            "display": display,
            "payer": payer_rows,
            "markdown_query": render_markdown(query_treatment(f"{disease_key} 证据", self.compiled_dir)),
        }

    def evidence_for_disease(self, disease_key: str) -> list[dict[str, Any]]:
        rows = [row for row in self.evidence if row.get("disease_key") == disease_key]
        if self.public_mode:
            return [public_row(row, PUBLIC_EVIDENCE_FIELDS) for row in rows]
        return rows

    def payer_for_disease(self, disease_key: str) -> list[dict[str, Any]]:
        rows = [row for row in self.payer if row.get("disease_key") == disease_key]
        if self.public_mode:
            return [public_row(row, PUBLIC_PAYER_FIELDS) for row in rows]
        return rows

    def resolve_disease_key(self, query: str) -> str | None:
        if query in self.diseases_by_key:
            return query
        matches = find_registry_matches(query, self.registry, limit=1, diseases_by_key=self.diseases_by_key)
        if not matches:
            return None
        modules = matches[0].get("treatment_modules") or []
        return modules[0] if modules else matches[0].get("treatment_module")

    def search(self, query: str, limit: int = 40) -> list[dict[str, Any]]:
        query = query.strip()
        if not query:
            return [
                {
                    "type": "disease_registry",
                    "id": row["registry_id"],
                    "disease_key": row["disease_key"],
                    "title": row.get("requested_name"),
                    "subtitle": row.get("coverage_status"),
                    "score": 0,
                }
                for row in self.registry[:limit]
            ]

        q_compact = compact_text(query)
        terms = [term for term in re.split(r"\s+", compact_text(query)) if term]
        scored: list[tuple[int, dict[str, Any]]] = []
        for row in self.search_index:
            haystack = compact_text(
                " ".join(
                    str(item)
                    for item in [
                        row.get("title"),
                        row.get("subtitle"),
                        row.get("search_text"),
                        row.get("id"),
                    ]
                    if item
                )
            )
            score = 0
            title = compact_text(row.get("title"))
            if q_compact and q_compact == title:
                score += 140
            if q_compact and q_compact in title:
                score += 110
            if q_compact and q_compact in haystack:
                score += 70
            for term in terms:
                if term and term in haystack:
                    score += 15
            if score:
                scored.append((score, row))
        scored.sort(key=lambda item: (-item[0], str(item[1].get("type")), str(item[1].get("title"))))
        return [
            {
                "type": row.get("type"),
                "id": row.get("id"),
                "disease_key": row.get("disease_key"),
                "title": row.get("title"),
                "subtitle": row.get("subtitle"),
                "score": score,
            }
            for score, row in scored[:limit]
        ]


class TreatmentHandler(BaseHTTPRequestHandler):
    server_version = "RenalTreatmentQuery/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        path = parsed.path

        try:
            if path == "/api/health":
                self.write_json(self.server.catalog.health())
                return
            if path == "/api/reload":
                self.server.catalog.load()
                self.write_json(self.server.catalog.health())
                return
            if path == "/api/diseases":
                query = params.get("q", [""])[0]
                limit = safe_int(params.get("limit", ["120"])[0], 120)
                self.write_json({"query": query, "items": self.server.catalog.list_diseases(query, limit)})
                return
            if path == "/api/query":
                query = params.get("q", [""])[0]
                limit_value = params.get("limit_cards", [None])[0]
                limit_cards = None if limit_value in (None, "", "all") else safe_int(limit_value, 100)
                self.write_json(self.server.catalog.query(query, limit_cards))
                return
            if path == "/api/search":
                query = params.get("q", [""])[0]
                limit = safe_int(params.get("limit", ["40"])[0], 40)
                self.write_json({"query": query, "items": self.server.catalog.search(query, limit)})
                return
            if path == "/api/evidence":
                disease = params.get("disease", [""])[0]
                key = self.server.catalog.resolve_disease_key(disease) if disease else None
                if not key:
                    self.write_json({"error": "Disease not found"}, status=404)
                    return
                self.write_json({"disease_key": key, "items": self.server.catalog.evidence_for_disease(key)})
                return
            if path == "/api/payer":
                disease = params.get("disease", [""])[0]
                key = self.server.catalog.resolve_disease_key(disease) if disease else None
                if not key:
                    self.write_json({"error": "Disease not found"}, status=404)
                    return
                self.write_json({"disease_key": key, "items": self.server.catalog.payer_for_disease(key)})
                return
            if path.startswith("/api/diseases/"):
                disease_key = unquote(path.removeprefix("/api/diseases/")).strip("/")
                detail = self.server.catalog.disease_detail(disease_key)
                if not detail:
                    self.write_json({"error": "Disease not found"}, status=404)
                    return
                self.write_json(detail)
                return
            if path.startswith("/api/cards/"):
                card_id = unquote(path.removeprefix("/api/cards/")).strip("/")
                detail = self.server.catalog.card_detail(card_id)
                if not detail:
                    self.write_json({"error": "Treatment card not found"}, status=404)
                    return
                self.write_json(detail)
                return
            self.serve_static(path)
        except Exception as exc:  # pragma: no cover - keeps browser failures readable.
            self.write_json({"error": str(exc)}, status=500)

    def serve_static(self, request_path: str) -> None:
        if request_path in ("", "/"):
            target = STATIC_DIR / "index.html"
        else:
            target = (STATIC_DIR / unquote(request_path.lstrip("/"))).resolve()
            try:
                target.relative_to(STATIC_DIR.resolve())
            except ValueError:
                self.send_error(403)
                return
        if not target.exists() or not target.is_file():
            self.send_error(404)
            return
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def write_json(self, payload: Any, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:
        return


class TreatmentServer(ThreadingHTTPServer):
    catalog: TreatmentCatalog


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local renal treatment query app.")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8785")))
    parser.add_argument(
        "--compiled-dir",
        type=Path,
        default=Path(os.environ.get("COMPILED_DIR", str(DEFAULT_COMPILED_DIR))),
    )
    parser.add_argument("--public-mode", action="store_true", default=env_flag("PUBLIC_MODE"))
    args = parser.parse_args()

    server = TreatmentServer((args.host, args.port), TreatmentHandler)
    server.catalog = TreatmentCatalog(args.compiled_dir, public_mode=args.public_mode)
    print(f"Renal treatment query app: http://{args.host}:{args.port}")
    print(
        "Loaded "
        f"{len(server.catalog.registry)} treatment packages and "
        f"{len(server.catalog.cards)} treatment cards from {args.compiled_dir}"
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
