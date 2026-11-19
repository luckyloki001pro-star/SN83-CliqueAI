"""Historical SN83 challenge record model, validation, and I/O."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .codec import GraphCodec
from .graph import BitsetGraph

REQUIRED_FIELDS = [
    "timestamp",
    "uuid",
    "label",
    "difficulty",
    "time_limit",
    "number_of_nodes",
    "adjacency_list",
    "encoded_matrix",
    "miner_uids",
    "miner_hotkeys",
    "miner_coldkeys",
    "miner_ans",
    "miner_rel",
    "miner_pr",
    "miner_omega",
    "miner_optimality",
    "miner_diversity",
    "miner_rewards",
]

MINER_ARRAY_FIELDS = [
    "miner_uids",
    "miner_hotkeys",
    "miner_coldkeys",
    "miner_ans",
    "miner_rel",
    "miner_pr",
    "miner_omega",
    "miner_optimality",
    "miner_diversity",
    "miner_rewards",
]


@dataclass
class CompletenessReport:
    ok: bool
    missing_fields: List[str] = field(default_factory=list)
    length_mismatches: Dict[str, int] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)


def _as_list(x: Any) -> list:
    if x is None:
        return []
    try:
        import numpy as np

        if isinstance(x, np.ndarray):
            return x.tolist()
    except Exception:
        pass
    if isinstance(x, (list, tuple)):
        return list(x)
    return list(x) if hasattr(x, "__iter__") and not isinstance(x, (str, bytes, dict)) else x


def normalize_record(raw: Dict[str, Any], provenance: Dict[str, Any] | None = None) -> Dict[str, Any]:
    rec = dict(raw)
    # Unwrap nested WandbRunLogData-like payloads.
    if "data" in rec and isinstance(rec["data"], dict):
        inner = dict(rec["data"])
        for k, v in rec.items():
            if k != "data" and k not in inner:
                inner[f"_outer_{k}"] = v
        rec = inner
    for f in MINER_ARRAY_FIELDS + ["adjacency_list"]:
        if f in rec:
            rec[f] = _as_list(rec[f])
            if f == "miner_ans":
                rec[f] = [_as_list(ans) for ans in rec[f]]
            if f == "adjacency_list":
                rec[f] = [_as_list(row) for row in rec[f]]
    for f in (
        "miner_rel",
        "miner_pr",
        "miner_omega",
        "miner_optimality",
        "miner_diversity",
        "miner_rewards",
    ):
        if f in rec:
            rec[f] = [float(x) for x in rec[f]]
    if "miner_uids" in rec:
        rec["miner_uids"] = [int(x) for x in rec["miner_uids"]]
    if "number_of_nodes" in rec:
        rec["number_of_nodes"] = int(rec["number_of_nodes"])
    if "difficulty" in rec:
        rec["difficulty"] = float(rec["difficulty"])
    if "time_limit" in rec:
        rec["time_limit"] = float(rec["time_limit"])
    if "timestamp" in rec:
        rec["timestamp"] = float(rec["timestamp"])
    rec["_provenance"] = provenance or raw.get("_provenance", {})
    return rec


def check_completeness(rec: Dict[str, Any]) -> CompletenessReport:
    missing = [f for f in REQUIRED_FIELDS if f not in rec or rec[f] is None]
    notes: List[str] = []
    length_mismatches: Dict[str, int] = {}
    if missing:
        return CompletenessReport(False, missing, {}, ["missing required fields"])

    n = len(rec["miner_uids"])
    if n == 0:
        notes.append("no miners recorded")
        return CompletenessReport(False, [], {}, notes)

    for f in MINER_ARRAY_FIELDS:
        ln = len(rec[f])
        if ln != n:
            length_mismatches[f] = ln

    if len(rec["adjacency_list"]) != rec["number_of_nodes"]:
        notes.append("adjacency_list length != number_of_nodes")
    if not rec["encoded_matrix"]:
        notes.append("empty encoded_matrix")
    if not rec["uuid"]:
        notes.append("empty uuid")

    ok = not length_mismatches and not notes
    if length_mismatches:
        notes.append("miner array length mismatches")
    return CompletenessReport(ok, [], length_mismatches, notes)


def graph_checks(rec: Dict[str, Any]) -> Dict[str, Any]:
    codec = GraphCodec()
    n = rec["number_of_nodes"]
    adj = rec["adjacency_list"]
    out: Dict[str, Any] = {
        "n": n,
        "adj_len": len(adj),
        "symmetric": True,
        "no_self_loops": True,
        "index_ok": True,
        "codec_match": None,
        "edges": 0,
        "density": 0.0,
        "graph_hash": "",
        "errors": [],
    }
    edges = 0
    for u, nbrs in enumerate(adj):
        for v in nbrs:
            if not (0 <= v < n):
                out["index_ok"] = False
                out["errors"].append(f"neighbor {v} out of range at u={u}")
            if v == u:
                out["no_self_loops"] = False
            if u < v:
                edges += 1
            if u not in adj[v] if 0 <= v < n else True:
                # check symmetry carefully
                pass
        for v in nbrs:
            if 0 <= v < n and u not in adj[v]:
                out["symmetric"] = False
    # recount undirected edges properly
    undirected = 0
    for u in range(n):
        for v in adj[u]:
            if u < v:
                undirected += 1
    out["edges"] = undirected
    out["density"] = (2.0 * undirected) / (n * (n - 1)) if n > 1 else 0.0

    try:
        decoded = codec.decode_matrix(rec["encoded_matrix"])
        decoded_list = codec.matrix_to_list(decoded)
        if len(decoded) != n:
            out["codec_match"] = False
            out["errors"].append("decoded n mismatch")
        else:
            # Compare as sets per row
            match = True
            for i in range(n):
                if set(decoded_list[i]) != set(adj[i]):
                    match = False
                    break
            out["codec_match"] = match
            if not match:
                out["errors"].append("encoded_matrix != adjacency_list")
    except Exception as e:
        out["codec_match"] = False
        out["errors"].append(f"codec decode failed: {e}")

    g = BitsetGraph.from_adjacency_list(adj, name=rec.get("uuid", ""))
    out["graph_hash"] = g.content_hash() if n <= 1200 else hashlib.sha256(
        json.dumps(adj, separators=(",", ":")).encode()
    ).hexdigest()
    return out


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def save_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")


def select_latest_complete(
    records: Sequence[Dict[str, Any]],
    limit: int = 20,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Deduplicate by UUID keeping newest timestamp; return top `limit` complete
    records and a list of conflict warnings.
    """
    by_uuid: Dict[str, Dict[str, Any]] = {}
    conflicts: List[Dict[str, Any]] = []
    for rec in records:
        uid = rec.get("uuid")
        if not uid:
            continue
        prev = by_uuid.get(uid)
        if prev is None:
            by_uuid[uid] = rec
            continue
        # Conflict if graph or score arrays differ
        same_graph = (
            prev.get("encoded_matrix") == rec.get("encoded_matrix")
            and prev.get("adjacency_list") == rec.get("adjacency_list")
        )
        same_scores = prev.get("miner_rewards") == rec.get("miner_rewards")
        if not same_graph or not same_scores:
            conflicts.append(
                {
                    "uuid": uid,
                    "reason": "conflicting duplicate uuid",
                    "same_graph": same_graph,
                    "same_scores": same_scores,
                    "timestamps": [prev.get("timestamp"), rec.get("timestamp")],
                }
            )
            # Keep newer but flag.
        if float(rec.get("timestamp") or 0) >= float(prev.get("timestamp") or 0):
            by_uuid[uid] = rec

    complete = []
    for rec in by_uuid.values():
        if check_completeness(rec).ok:
            complete.append(rec)
    complete.sort(key=lambda r: float(r.get("timestamp") or 0), reverse=True)
    return complete[:limit], conflicts


def write_manifest(
    path: Path,
    *,
    selected: List[Dict[str, Any]],
    retrieved_count: int,
    complete_count: int,
    run_ids: List[str],
    warnings: List[Any],
    source: str,
    source_urls: List[str],
    access_status: str,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    manifest = {
        "source_project": "toptensor-ai/CliqueAI",
        "source": source,
        "source_urls": source_urls,
        "retrieval_timestamp_utc": now,
        "wandb_run_ids": run_ids,
        "retrieved_records": retrieved_count,
        "complete_records": complete_count,
        "selected_count": len(selected),
        "selected_uuids": [r.get("uuid") for r in selected],
        "source_timestamps": [r.get("timestamp") for r in selected],
        "timestamp_range": {
            "min": min((r.get("timestamp") for r in selected), default=None),
            "max": max((r.get("timestamp") for r in selected), default=None),
        },
        "access_status": access_status,
        "warnings": warnings,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2))
