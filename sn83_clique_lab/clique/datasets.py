"""Dataset loaders and synthetic graph generators."""

from __future__ import annotations

import hashlib
import json
import random
import shutil
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from .codec import GraphCodec
from .graph import BitsetGraph

ROOT = Path(__file__).resolve().parent.parent
DATASETS = ROOT / "datasets"
OFFICIAL = DATASETS / "official"
SYNTHETIC = DATASETS / "synthetic"

# Upstream SN83 samples (workspace copy).
WORKSPACE_TEST_DATA = Path("/home/CliqueAI/test_data")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def import_official_samples(
    source_dir: Path | None = None,
    dest_dir: Path | None = None,
) -> List[Dict[str, Any]]:
    """Copy and decode official SN83 test_data graphs."""
    src = source_dir or WORKSPACE_TEST_DATA
    dst = dest_dir or OFFICIAL
    dst.mkdir(parents=True, exist_ok=True)
    codec = GraphCodec()
    records: List[Dict[str, Any]] = []

    for path in sorted(src.glob("*.json")):
        raw = json.loads(path.read_text())
        n = int(raw["number_of_nodes"])
        encoded = raw["encoded_matrix"]
        graph = codec.decode_graph(encoded, name=path.stem)
        out = {
            "name": path.stem,
            "source_file": str(path),
            "source_sha256": _sha256_file(path),
            "n": graph.n,
            "edges": graph.edge_count(),
            "density": graph.density(),
            "dataset": "official",
            "encoded_matrix": encoded,
            "adjacency_list": graph.to_adjacency_list(),
            "graph_hash": graph.content_hash(),
            "label": raw.get("label", ""),
            "timeout_field": raw.get("timeout"),
        }
        out_path = dst / f"{path.stem}.json"
        out_path.write_text(json.dumps(out, indent=2))
        # Also keep a compact adjacency-only solve file.
        (dst / f"{path.stem}.adj.json").write_text(
            json.dumps(
                {
                    "name": path.stem,
                    "n": n,
                    "adjacency_list": out["adjacency_list"],
                    "graph_hash": out["graph_hash"],
                    "density": out["density"],
                    "edges": out["edges"],
                    "dataset": "official",
                }
            )
        )
        records.append(out)
    meta = {
        "count": len(records),
        "source": str(src),
        "graphs": [
            {
                "name": r["name"],
                "n": r["n"],
                "edges": r["edges"],
                "density": r["density"],
                "sha256": r["source_sha256"],
                "graph_hash": r["graph_hash"],
            }
            for r in records
        ],
    }
    (dst / "manifest.json").write_text(json.dumps(meta, indent=2))
    return records


def erdos_renyi(n: int, p: float, seed: int, name: str = "") -> BitsetGraph:
    rng = random.Random(seed)
    g = BitsetGraph.empty(n, name=name or f"er_n{n}_p{p:.2f}_s{seed}")
    for i in range(n):
        for j in range(i + 1, n):
            if rng.random() < p:
                g.add_edge(i, j)
    g.metadata = {
        "generator": "erdos_renyi",
        "n": n,
        "p": p,
        "seed": seed,
        "dataset": "dense_random",
    }
    return g


def planted_clique_graph(
    n: int,
    p: float,
    clique_size: int,
    seed: int,
) -> BitsetGraph:
    rng = random.Random(seed)
    g = erdos_renyi(n, p, seed, name=f"planted_n{n}_k{clique_size}_p{p:.2f}_s{seed}")
    members = rng.sample(range(n), clique_size)
    for i, u in enumerate(members):
        for v in members[i + 1 :]:
            g.add_edge(u, v)
    g.metadata.update(
        {
            "generator": "planted_clique",
            "planted_size": clique_size,
            "planted_members": members,
            "dataset": "planted",
        }
    )
    g.name = f"planted_n{n}_k{clique_size}_p{p:.2f}_s{seed}"
    return g


def structured_communities(
    n: int,
    community_size: int,
    num_communities: int,
    inter_p: float,
    seed: int,
) -> BitsetGraph:
    rng = random.Random(seed)
    g = BitsetGraph.empty(
        n, name=f"comm_n{n}_c{num_communities}_s{community_size}_seed{seed}"
    )
    # Dense communities (near-cliques).
    for c in range(num_communities):
        start = (c * community_size) % max(n - community_size, 1)
        members = list(range(start, min(start + community_size, n)))
        for i, u in enumerate(members):
            for v in members[i + 1 :]:
                if rng.random() < 0.95:
                    g.add_edge(u, v)
    # Inter edges + high-degree decoys.
    for i in range(n):
        for j in range(i + 1, n):
            if rng.random() < inter_p:
                g.add_edge(i, j)
    decoys = min(10, n // 10)
    for d in range(decoys):
        v = rng.randrange(n)
        for u in range(n):
            if u != v and rng.random() < 0.85:
                g.add_edge(u, v)
    g.metadata = {
        "generator": "structured_communities",
        "n": n,
        "community_size": community_size,
        "num_communities": num_communities,
        "inter_p": inter_p,
        "seed": seed,
        "dataset": "structured",
    }
    return g


def overlapping_cliques(
    n: int,
    clique_sizes: List[int],
    seed: int,
    background_p: float = 0.2,
) -> BitsetGraph:
    rng = random.Random(seed)
    g = erdos_renyi(n, background_p, seed, name=f"overlap_n{n}_s{seed}")
    for k in clique_sizes:
        members = rng.sample(range(n), min(k, n))
        for i, u in enumerate(members):
            for v in members[i + 1 :]:
                g.add_edge(u, v)
    g.metadata.update(
        {
            "generator": "overlapping_cliques",
            "clique_sizes": clique_sizes,
            "dataset": "structured",
        }
    )
    g.name = f"overlap_n{n}_s{seed}"
    return g


def save_graph(graph: BitsetGraph, path: Path) -> Dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "name": graph.name,
        "n": graph.n,
        "edges": graph.edge_count(),
        "density": graph.density(),
        "adjacency_list": graph.to_adjacency_list(),
        "graph_hash": graph.content_hash(),
        "metadata": graph.metadata,
        "dataset": graph.metadata.get("dataset", "synthetic"),
    }
    path.write_text(json.dumps(rec))
    return rec


def load_graph_record(path: Path) -> BitsetGraph:
    data = json.loads(path.read_text())
    g = BitsetGraph.from_adjacency_list(
        data["adjacency_list"],
        name=data.get("name", path.stem),
        metadata=data.get("metadata", {}),
    )
    if "dataset" in data:
        g.metadata.setdefault("dataset", data["dataset"])
    return g


def generate_synthetic_suite(split: str = "dev") -> List[Path]:
    """
    Generate reproducible synthetic graphs into datasets/synthetic/{split}.

    split: dev | tune | eval — use different seed offsets; do not tune on eval.
    """
    base = {"dev": 1000, "tune": 2000, "eval": 3000}[split]
    out_dir = SYNTHETIC / split
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []

    # Dense ER graphs.
    for n in (50, 100, 300, 500, 700, 900):
        for p in (0.60, 0.75, 0.85):
            for k in range(2 if n >= 300 else 1):
                seed = base + n + int(p * 100) + k * 17
                # Keep full suite lighter for large n in dev.
                if split == "dev" and n >= 700 and k > 0:
                    continue
                g = erdos_renyi(n, p, seed)
                path = out_dir / f"{g.name}.json"
                save_graph(g, path)
                paths.append(path)

    # Structured.
    for n, cs, nc in ((120, 25, 4), (300, 40, 5), (500, 50, 6)):
        seed = base + 5000 + n
        g = structured_communities(n, cs, nc, inter_p=0.15, seed=seed)
        path = out_dir / f"{g.name}.json"
        save_graph(g, path)
        paths.append(path)
        g2 = overlapping_cliques(n, [20, 25, 30], seed=seed + 1)
        path2 = out_dir / f"{g2.name}.json"
        save_graph(g2, path2)
        paths.append(path2)

    # Planted.
    for n, k, p in ((100, 15, 0.5), (300, 25, 0.55), (500, 35, 0.55)):
        seed = base + 9000 + n + k
        g = planted_clique_graph(n, p, k, seed)
        path = out_dir / f"{g.name}.json"
        save_graph(g, path)
        paths.append(path)

    manifest = {
        "split": split,
        "count": len(paths),
        "files": [p.name for p in paths],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return paths


def iter_quick_benchmark_graphs() -> Iterator[BitsetGraph]:
    """Graphs for quick mode: official + selected 300/500."""
    import_official_samples()
    for path in sorted(OFFICIAL.glob("*.adj.json")):
        yield load_graph_record(path)

    out = SYNTHETIC / "dev"
    if not out.exists() or not any(out.glob("er_n300*.json")):
        generate_synthetic_suite("dev")

    patterns = [
        "er_n300_p0.60*.json",
        "er_n300_p0.75*.json",
        "er_n500_p0.60*.json",
        "er_n500_p0.75*.json",
        "comm_n300*.json",
        "planted_n300*.json",
    ]
    seen = set()
    for pat in patterns:
        for path in sorted(out.glob(pat)):
            if path.name in seen:
                continue
            seen.add(path.name)
            yield load_graph_record(path)
