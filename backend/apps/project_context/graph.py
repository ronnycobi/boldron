"""The Application Graph (spec §4) + Dependency Intelligence (spec §5).

A persistent, machine-readable node+edge model of one application: its features,
screens, APIs, data entities, requirements, business rules, environments and
mobile platforms, with edges that record how they depend on each other
(Checkout requires Payment and a Database; the iOS app runs on the API; …).

Like `intelligence.py`, this builds nothing of its own — it is a read-only
projection COMPOSED from data the platform already keeps:

  - the project's capability map (`Project.capabilities`) → feature / infra /
    integration / security nodes, with honest availability;
  - project context entries (screens, APIs, schema, requirements, business
    rules) → their nodes;
  - the mobile plan (`Project.mobile_plan`) → mobile-platform nodes;
  - screen `data_needs` → observed screen→API edges;
  - the platform's known capability-composition rules → architectural edges
    (deterministic, defensible — not fabricated per-customer data).

It is CUSTOMER-SAFE (spec §30): it never exposes the internal stack, AI
agent/model names, prompts, task ids, infrastructure proposals or a context
entry's `source`. Internal-only context kinds are excluded, exactly as in the
intelligence engine.

Dependency Intelligence (spec §5) is the query layer over the graph: given any
node, `dependency_report` answers "what does this depend on?" and — the one that
matters before a change — "what depends on this, and would be affected if it
changed?".
"""
from __future__ import annotations

from apps.capabilities.registry import get as get_capability
from apps.project_context.models import ContextKind
from apps.project_context.services import ProjectContext

# Internal context kinds that must never surface to a customer (spec §30).
_INTERNAL_KINDS = {
    ContextKind.STACK, ContextKind.INFRASTRUCTURE,
    ContextKind.AGENT_DECISION, ContextKind.REVIEW,
}

# Capability group → the node type we render it as. Application/Business/Growth
# are the app's own features; the rest are the platform surfaces they lean on.
_GROUP_TYPE = {
    "Application": "feature",
    "Business": "feature",
    "Growth": "feature",
    "Infrastructure": "infrastructure",
    "Protect": "security",
    "Integrations": "integration",
}

_PLATFORM_NAMES = {"ios": "iOS", "android": "Android", "huawei": "Huawei AppGallery"}

# The platform's known capability-composition rules: what a given capability
# genuinely depends on, when BOTH capabilities are present in the app. These are
# deterministic architectural facts about how the platform composes capabilities
# (the same relationships impact analysis already relies on), never invented
# per-customer data. edge kind: "requires" (hard), "uses", "notifies",
# "tracked_by". Only edges whose target capability is actually in the app are
# emitted, so nothing is implied that the app doesn't have.
_CAP_DEPENDS: dict[str, list[tuple[str, str]]] = {
    "users": [("database", "requires")],
    "auth": [("users", "requires"), ("database", "requires")],
    "roles": [("users", "requires"), ("auth", "requires")],
    "crm": [("database", "requires")],
    "search": [("database", "requires")],
    "dashboard": [("database", "requires")],
    "forms": [("database", "requires")],
    "files": [("database", "requires")],
    "api": [("database", "requires")],
    "seo": [("database", "requires")],
    "ecommerce": [("database", "requires"), ("payments", "requires"),
                  ("files", "uses"), ("tax", "uses"), ("currency", "uses"),
                  ("email", "notifies"), ("analytics", "tracked_by")],
    "payments": [("database", "requires"), ("email", "notifies"),
                 ("analytics", "tracked_by")],
    "subscriptions": [("payments", "requires"), ("invoicing", "requires"),
                      ("email", "notifies")],
    "invoicing": [("payments", "requires"), ("tax", "uses"), ("currency", "uses"),
                  ("email", "notifies")],
    "campaigns": [("email", "requires"), ("crm", "uses")],
    "analytics": [("database", "requires")],
    "monitoring": [("hosting", "requires")],
    "domains": [("hosting", "requires")],
    "backups": [("database", "requires")],
}


def _clip(text: str, n: int = 160) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


class _Graph:
    """Accumulates nodes + edges, de-duplicating and only keeping edges whose
    endpoints both exist (so nothing implies a surface the app doesn't have)."""

    def __init__(self):
        self._nodes: dict[str, dict] = {}
        self._edges: list[dict] = []
        self._seen_edges: set[tuple[str, str, str]] = set()

    def node(self, node_id, node_type, label, **extra):
        if node_id not in self._nodes:
            node = {"id": node_id, "type": node_type, "label": label}
            node.update({k: v for k, v in extra.items() if v not in (None, "", [])})
            self._nodes[node_id] = node
        return node_id

    def edge(self, source, target, kind):
        key = (source, target, kind)
        if source == target or key in self._seen_edges:
            return
        # Only connect nodes that genuinely exist in the graph.
        if source not in self._nodes or target not in self._nodes:
            return
        self._seen_edges.add(key)
        self._edges.append({"source": source, "target": target, "kind": kind})

    @property
    def nodes(self):
        return list(self._nodes.values())

    @property
    def edges(self):
        return list(self._edges)


def build_graph(project) -> dict:
    """The application's node+edge graph (spec §4), composed from real data and
    customer-safe."""
    g = _Graph()

    # --- the application root -------------------------------------------------
    app_id = "app"
    g.node(app_id, "application", project.name or "Application")

    # --- capability nodes (features / infra / integrations / security) --------
    cap_ids = list(project.capabilities or [])
    present = set(cap_ids)
    for cid in cap_ids:
        cap = get_capability(cid)
        if cap is None:
            continue
        node_type = _GROUP_TYPE.get(cap.group, "feature")
        g.node(f"cap:{cid}", node_type, cap.name,
               group=cap.group, status=cap.status,
               available=cap.is_available, summary=_clip(cap.description))
        g.edge(app_id, f"cap:{cid}", "has")

    # Architectural dependency edges between capabilities the app actually has.
    for cid in cap_ids:
        for dep_id, kind in _CAP_DEPENDS.get(cid, []):
            if dep_id in present:
                g.edge(f"cap:{cid}", f"cap:{dep_id}", kind)

    # --- context-entry nodes (screens, APIs, entities, requirements, rules) ---
    entries = [e for e in ProjectContext(project).all() if e.kind not in _INTERNAL_KINDS]

    api_by_token: dict[str, str] = {}   # lowered title/key → api node id, for matching
    for e in entries:
        if e.kind != ContextKind.API:
            continue
        nid = g.node(f"api:{e.key}", "api", e.title or e.key, summary=_clip(e.content))
        for token in filter(None, {(e.title or "").lower().strip(), e.key.lower().strip()}):
            api_by_token[token] = nid
        if "cap:api" in {f"cap:{c}" for c in present} or "api" in present:
            g.edge(f"api:{e.key}", "cap:api", "part_of")

    for e in entries:
        if e.kind == ContextKind.SCHEMA:
            g.node(f"entity:{e.key}", "entity", e.title or e.key, summary=_clip(e.content))
            if "database" in present:
                g.edge(f"entity:{e.key}", "cap:database", "stored_in")
        elif e.kind == ContextKind.REQUIREMENT:
            g.node(f"req:{e.key}", "requirement", e.title or e.key, summary=_clip(e.content))
            g.edge(app_id, f"req:{e.key}", "satisfies")
        elif e.kind == ContextKind.BUSINESS_RULE:
            g.node(f"rule:{e.key}", "business_rule", e.title or e.key, summary=_clip(e.content))
            g.edge(app_id, f"rule:{e.key}", "governed_by")

    # Screens (web + mobile, split by platform exactly as intelligence does).
    for e in entries:
        if e.kind != ContextKind.SCREEN:
            continue
        data = e.data or {}
        is_mobile = data.get("platform") == "mobile"
        node_type = "mobile_screen" if is_mobile else "screen"
        prefix = "mscreen" if is_mobile else "screen"
        nid = g.node(f"{prefix}:{e.key}", node_type, e.title or e.key,
                     summary=_clip(e.content))
        g.edge(app_id, nid, "has")
        # Observed screen→API edges from what the screen declares it consumes.
        needs = data.get("data_needs") or []
        linked_specific = False
        for need in needs if isinstance(needs, list) else []:
            token = str(need).lower().strip()
            if token in api_by_token:
                g.edge(nid, api_by_token[token], "uses")
                linked_specific = True
        # If it needs data but named no entry we know, it still uses the API.
        if needs and not linked_specific and "api" in present:
            g.edge(nid, "cap:api", "uses")

    # --- environments ---------------------------------------------------------
    if present & {"environments", "hosting"}:
        for env_key, env_label in (("development", "Development"),
                                   ("staging", "Staging"),
                                   ("production", "Production")):
            g.node(f"env:{env_key}", "environment", env_label)
            g.edge(app_id, f"env:{env_key}", "deploys_to")

    # --- mobile platforms -----------------------------------------------------
    for p in (project.mobile_plan or {}).get("platforms", []):
        nid = g.node(f"platform:{p}", "mobile_platform", _PLATFORM_NAMES.get(p, p))
        g.edge(app_id, nid, "ships_as")
        # The mobile apps run on the shared API.
        if "api" in present:
            g.edge(nid, "cap:api", "runs_on")

    nodes, edges = g.nodes, g.edges
    by_type: dict[str, int] = {}
    for n in nodes:
        by_type[n["type"]] = by_type.get(n["type"], 0) + 1

    return {
        "project": {"id": project.id, "name": project.name},
        "nodes": nodes,
        "edges": edges,
        "stats": {"nodes": len(nodes), "edges": len(edges), "by_type": by_type},
    }


# --------------------------------------------------------------------------- #
# Dependency Intelligence (spec §5) — queries over the graph.
# --------------------------------------------------------------------------- #

# Edge kinds that mean "source genuinely depends on target" for impact purposes.
# Structural ownership edges (has/satisfies/…) are not dependencies.
_DEPENDENCY_KINDS = {"requires", "uses", "runs_on", "part_of", "stored_in"}


def _adjacency(graph):
    """forward[x] = targets x depends on; reverse[x] = nodes that depend on x."""
    forward: dict[str, set] = {}
    reverse: dict[str, set] = {}
    for edge in graph["edges"]:
        if edge["kind"] not in _DEPENDENCY_KINDS:
            continue
        forward.setdefault(edge["source"], set()).add(edge["target"])
        reverse.setdefault(edge["target"], set()).add(edge["source"])
    return forward, reverse


def _reachable(start, adj):
    """Breadth-first transitive closure from `start` (excluding start itself)."""
    seen, stack = set(), list(adj.get(start, set()))
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        stack.extend(adj.get(n, set()))
    return seen


def dependency_report(project, node_id: str) -> dict | None:
    """Dependency Intelligence for one node (spec §5): what it depends on, and —
    the question to ask before changing it — everything that depends on it and
    would be affected if it changed. Returns None if the node isn't in the graph.
    """
    graph = build_graph(project)
    index = {n["id"]: n for n in graph["nodes"]}
    if node_id not in index:
        return None

    forward, reverse = _adjacency(graph)

    def _brief(nid):
        n = index[nid]
        return {"id": n["id"], "type": n["type"], "label": n["label"]}

    depends_on = sorted(_reachable(node_id, forward), key=lambda i: index[i]["label"])
    dependents = sorted(_reachable(node_id, reverse), key=lambda i: index[i]["label"])

    return {
        "project": graph["project"],
        "node": _brief(node_id),
        "depends_on": [_brief(i) for i in depends_on],
        "dependents": [_brief(i) for i in dependents],
        "impact_count": len(dependents),
        "direct_dependents": [_brief(i) for i in
                              sorted(reverse.get(node_id, set()),
                                     key=lambda i: index[i]["label"])],
    }
