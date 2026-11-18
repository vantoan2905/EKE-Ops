"""Generate a large, deterministic synthetic fixture for load, authorization, and evaluation tests.

The output uses the same tables as ``schema.sql`` and the same access rule as the
``eke_demo.authorized_chunks`` view: a user can read a document when both belong to the
same organization, and each non-empty ``projects``/``departments`` list on the document
overlaps the user's list. Evaluation ground truth is computed with that rule, so
``authorized_relevant_chunk_ids`` is correct for every case.

Usage:
    python mock_data/generate.py --scale large
    psql -X -v ON_ERROR_STOP=1 "$DATABASE_URL" -f mock_data/schema.sql
    psql -X -v ON_ERROR_STOP=1 "$DATABASE_URL" -f mock_data/generated/large/load.sql

All generated IDs start with ``gen-``, so the output can coexist with ``demo.json``.
Loading again replaces the previous generated rows. All names and contents are invented.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

SCALES = {
    #         orgs, users/org, docs/org, cases/org, runs/config
    "small": (2, 25, 80, 40, 1),
    "medium": (5, 200, 600, 300, 1),
    "large": (10, 1000, 2500, 1000, 2),
    "xlarge": (20, 5000, 5000, 2000, 2),
}

ORG_NAMES = [
    "Northwind Robotics", "Bluefin Analytics", "Cedar Peak Health", "Ironleaf Logistics",
    "Lumen Grid Energy", "Quarry Bay Finance", "Silverline Media", "Tamarack Foods",
    "Vantage Orbital", "Willowmere Retail", "Granite Arc Insurance", "Kestrel Mobility",
    "Mossway Biotech", "Obsidian Rail", "Pinecrest Education", "Redwater Shipping",
    "Saltmarsh Telecom", "Thornfield Legal", "Umber Steelworks", "Zephyr Aviation",
]
WORKSPACE_NAMES = ["Internal Knowledge", "Research", "Operations Hub", "Partner Portal"]
PROJECTS = [
    "atlas", "orion", "tidal", "nimbus", "quartz", "harbor", "falcon", "ember", "summit",
    "cobalt", "aurora", "meridian", "beacon", "cascade", "zenith", "polaris", "drift",
    "ridge", "sable", "vector",
]
DEPARTMENTS = [
    "engineering", "finance", "operations", "security", "legal",
    "hr", "sales", "research", "product", "support",
]
CORE_DEPARTMENTS = DEPARTMENTS[:4]
ROLES = [  # (role, weight)
    ("Employee", 76), ("Knowledge Manager", 8), ("AI Engineer", 7), ("Evaluator", 6),
    ("Organization Admin", 3),
]
FIRST = [
    "Avery", "Blake", "Cameron", "Dakota", "Emerson", "Finley", "Harper", "Jordan", "Kai",
    "Logan", "Marlowe", "Noel", "Oakley", "Parker", "Quinn", "Reese", "Rowan", "Sage",
    "Skyler", "Tatum", "Wren", "Ari", "Bao", "Chidi", "Dev", "Eun", "Farah", "Goran",
    "Hiro", "Ines", "Jun", "Kofi", "Lena", "Mateo", "Nadia", "Omar", "Priya", "Ravi",
    "Sana", "Tomas", "Uma", "Viktor", "Yara", "Zane", "Linh", "Minh", "Thao", "An",
]
LAST = [
    "Abbott", "Barros", "Castillo", "Dubois", "Eriksen", "Fontaine", "Garcia", "Haddad",
    "Ivanova", "Jensen", "Kowalski", "Larsen", "Mendes", "Nakamura", "Okafor", "Petrov",
    "Quintero", "Rossi", "Sato", "Tran", "Underwood", "Vasquez", "Whitlock", "Xu",
    "Yilmaz", "Zielinski", "Nguyen", "Pham", "Le", "Hoang", "Moreau", "Lindqvist",
]
FEATURES = [
    "SSO", "document search", "audit logging", "graph search", "offline mode",
    "usage analytics", "source synchronization", "answer citations", "bulk export",
    "role management", "mobile access", "scheduled reports",
]
SECURITY_CHECKS = [
    "tenant isolation", "document-level access checks", "audit event completeness",
    "secret rotation", "prompt injection handling", "encryption at rest",
    "session timeout enforcement", "least-privilege service accounts",
]
VENDORS = [
    "Brightpath Hosting", "Corvid Data Services", "Delta Ledger Systems",
    "Evergreen Translation", "Fathom Monitoring", "Gridlock Security Audits",
]
ACTIONS = [
    "draft the rollout checklist", "update the risk register", "confirm vendor pricing",
    "schedule the user interviews", "publish the test report", "review the access policy",
    "prepare the budget variance summary", "fix the indexing backlog",
    "share the onboarding deck", "validate the latency dashboard",
    "collect pilot feedback", "close the open audit findings",
]
FILLER = [
    "Status updates for {P} are shared in the weekly program sync.",
    "Questions about this document should go to the {P} project channel.",
    "This page is reviewed at the end of each quarter and archived after two years.",
    "Earlier drafts of this page are kept in the document history.",
    "Terminology follows the {org} internal glossary.",
    "Links to related {P} material are listed in the project index.",
]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
ABSTAIN = "I cannot answer from the information available to you."


@dataclass
class Fact:
    chunk_id: str
    question: str
    answer: str
    label: str  # e.g. "approved budget", used for partial answers
    department: str | None
    project: str | None


@dataclass
class Org:
    idx: int
    id: str
    name: str
    workspaces: list[dict] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    departments: list[str] = field(default_factory=list)
    users: list[dict] = field(default_factory=list)
    documents: list[dict] = field(default_factory=list)
    facts: list[Fact] = field(default_factory=list)
    bulk_facts: list[Fact] = field(default_factory=list)
    project_facts: dict[tuple[str, str], list[Fact]] = field(default_factory=dict)


def can_read(user: dict, doc: dict) -> bool:
    """Mirror of the eke_demo.authorized_chunks view."""
    if user["organization_id"] != doc["organization_id"]:
        return False
    if doc["projects"] and not set(doc["projects"]) & set(user["projects"]):
        return False
    if doc["departments"] and not set(doc["departments"]) & set(user["departments"]):
        return False
    return True


def fmt_date(d: date) -> str:
    return f"{d.day} {d:%B %Y}"


def money(n: int) -> str:
    return f"USD {n:,}"


class Generator:
    def __init__(self, seed: int, orgs: int, users_per_org: int, docs_per_org: int,
                 cases_per_org: int, runs_per_config: int) -> None:
        self.rng = random.Random(seed)
        self.seed = seed
        self.n_orgs = orgs
        self.users_per_org = users_per_org
        self.docs_per_org = docs_per_org
        self.cases_per_org = cases_per_org
        self.runs_per_config = runs_per_config
        self.orgs: list[Org] = []
        self.chunk_text: dict[str, str] = {}
        self.chunk_doc: dict[str, dict] = {}
        self._user_pool: dict[str, list[str]] = {}

    # ---------- helpers ----------
    def day(self, start: date = date(2027, 1, 4), span: int = 540) -> date:
        return start + timedelta(days=self.rng.randrange(span))

    def person(self) -> str:
        return f"{self.rng.choice(FIRST)} {self.rng.choice(LAST)}"

    # ---------- identity ----------
    def build_orgs(self) -> None:
        if self.n_orgs > len(ORG_NAMES):
            raise SystemExit(f"--orgs is limited to {len(ORG_NAMES)}")
        n_projects = max(3, min(len(PROJECTS), self.docs_per_org // 200 + 3))
        for i in range(self.n_orgs):
            org = Org(i, f"gen-org-{i + 1:03d}", ORG_NAMES[i])
            # Project names repeat across tenants on purpose: tenant checks must not rely on them.
            org.projects = sorted(self.rng.sample(PROJECTS, n_projects))
            extra = self.rng.sample(DEPARTMENTS[4:], self.rng.randint(2, len(DEPARTMENTS) - 4))
            org.departments = CORE_DEPARTMENTS + sorted(extra)
            for w in range(1 + (self.users_per_org >= 100)):
                org.workspaces.append({
                    "id": f"{org.id}-ws-{w + 1}", "organization_id": org.id,
                    "name": WORKSPACE_NAMES[w],
                })
            self.build_users(org)
            self.orgs.append(org)

    def build_users(self, org: Org) -> None:
        roles, weights = zip(*ROLES)
        for u in range(self.users_per_org):
            if u == 0:
                role = "Organization Admin"
            elif org.idx == 0 and u == 1:
                role = "Platform Admin"
            else:
                role = self.rng.choices(roles, weights)[0]
            n_dept = 2 if self.rng.random() < 0.15 else 1
            if role in ("Organization Admin", "Platform Admin", "Knowledge Manager") and self.rng.random() < 0.5:
                n_dept = 3
            depts = sorted(self.rng.sample(org.departments, n_dept))
            r = self.rng.random()
            n_proj = 0 if r < 0.08 else 1 if r < 0.55 else 2 if r < 0.85 else 3
            projs = sorted(self.rng.sample(org.projects, min(n_proj, len(org.projects))))
            org.users.append({
                "id": f"gen-user-{org.idx + 1:03d}-{u + 1:05d}",
                "organization_id": org.id,
                "name": self.person(),
                "role": role,
                "departments": depts,
                "projects": projs,
            })

    # ---------- knowledge ----------
    def owner_for(self, org: Org, dept: str | None) -> str:
        key = f"{org.id}:{dept}"
        if key not in self._user_pool:
            pool = [u["id"] for u in org.users if dept is None or dept in u["departments"]]
            self._user_pool[key] = pool or [u["id"] for u in org.users]
        return self.rng.choice(self._user_pool[key])

    def add_doc(self, org: Org, title: str, depts: list[str], projs: list[str],
                chunks: list[tuple[str, tuple[str, str, str] | None]],
                classification: str | None = None, bulk: bool = False) -> None:
        n = len(org.documents) + 1
        doc_id = f"gen-doc-{org.idx + 1:03d}-{n:05d}"
        P = projs[0].title() if projs else ""
        for _ in range(self.rng.choices([0, 1, 2, 3], [35, 35, 20, 10])[0]):
            chunks.append((self.rng.choice(FILLER).format(P=P or org.name, org=org.name), None))
        doc = {
            "id": doc_id, "organization_id": org.id,
            "workspace_id": self.rng.choice(org.workspaces)["id"],
            "title": title, "version": self.rng.choices([1, 2, 3, 4], [55, 25, 12, 8])[0],
            "owner_user_id": self.owner_for(org, depts[0] if depts else None),
            "classification": classification or (
                "confidential" if set(depts) & {"finance", "security", "legal", "hr"}
                else self.rng.choice(["internal", "internal", "public"])),
            "departments": sorted(depts), "projects": sorted(projs), "chunks": [],
        }
        for c, (text, fact) in enumerate(chunks, 1):
            chunk_id = f"{doc_id}-c{c}"
            doc["chunks"].append({"id": chunk_id, "text": text})
            self.chunk_text[chunk_id] = text
            self.chunk_doc[chunk_id] = doc
            if fact:
                q, a, label = fact
                f = Fact(chunk_id, q, a, label, depts[0] if depts else None, projs[0] if projs else None)
                if bulk:
                    org.bulk_facts.append(f)
                    continue
                org.facts.append(f)
                if projs:
                    org.project_facts.setdefault((projs[0], f.department or "*"), []).append(f)
        org.documents.append(doc)

    def project_docs(self, org: Org, p: str) -> None:
        P, R = p.title(), self.rng
        feats = R.sample(FEATURES, 4)
        review, release = sorted([self.day(), self.day()])
        if review == release:
            release += timedelta(days=14)
        budget = R.randrange(40, 900) * 1000
        reserve = budget // R.choice([5, 6, 8, 10])
        h1, h2 = R.choice([7, 8, 9]), R.choice([16, 17, 18])
        checks = R.sample(SECURITY_CHECKS, 3)
        sponsor = self.person()
        T = {
            "engineering": [
                (f"{P} release plan", [
                    (f"The {P} release is scheduled for {fmt_date(release)}. Engineering will finish the security review by {fmt_date(review)}.",
                     (f"When is the {P} release scheduled?", f"The {P} release is scheduled for {fmt_date(release)}.", "release date")),
                    (f"The release includes {feats[0]}, {feats[1]}, and {feats[2]}. {feats[3][0].upper() + feats[3][1:]} is excluded from the release.",
                     (f"Which feature is excluded from the {P} release?", f"{feats[3][0].upper() + feats[3][1:]} is excluded from the {P} release.", "excluded feature")),
                ]),
                (f"{P} engineering runbook", [
                    (f"Deploy {P} to staging on {(wd := R.choice(WEEKDAYS))}s. Run the smoke tests before promoting a release.",
                     (f"On which day is {P} deployed to staging?", f"{P} is deployed to staging on {wd}s.", "staging deploy day")),
                    (f"If search latency exceeds {(ms := R.choice([500, 600, 800, 1000, 1200]))} ms for {(mins := R.choice([5, 10, 15, 30]))} minutes, roll back the latest index build and notify the on-call engineer.",
                     (f"What latency condition triggers a {P} rollback?", f"Search latency above {ms} ms for {mins} minutes triggers a rollback.", "rollback threshold")),
                ]),
            ],
            "finance": [
                (f"{P} budget", [
                    (f"The approved {P} budget is {money(budget)}. Finance reserved {money(reserve)} of that total for security testing.",
                     (f"What is the approved {P} budget?", f"The approved {P} budget is {money(budget)}.", "approved budget")),
                    (f"The {P} budget covers work through {fmt_date(release + timedelta(days=30))}. Expansion funding requires a separate approval.", None),
                ]),
                (f"{P} cost forecast", [
                    (f"Finance forecasts {money((m := R.randrange(2, 40) * 500))} per month for {P} hosting. This operating forecast is separate from the approved budget.",
                     (f"What is the monthly hosting forecast for {P}?", f"Finance forecasts {money(m)} per month for {P} hosting.", "hosting forecast")),
                    (f"The forecast assumes {(nu := R.randrange(50, 5000, 50)):,} users and {nu * R.randint(50, 200):,} document searches per month.", None),
                ]),
            ],
            "operations": [
                (f"{P} operations FAQ", [
                    (f"The {P} help desk is staffed on weekdays from {h1:02d}:00 to {h2:02d}:00. Report access problems through the internal service portal.",
                     (f"When is the {P} help desk staffed?", f"The {P} help desk is staffed on weekdays from {h1:02d}:00 to {h2:02d}:00.", "help desk hours")),
                    ("The help desk cannot grant access to restricted documents.", None),
                ]),
            ],
            "security": [
                (f"{P} security review checklist", [
                    (f"The {P} security review must verify {checks[0]}, {checks[1]}, and {checks[2]} by {fmt_date(review)}.",
                     (f"What must the {P} security review verify?", f"It must verify {checks[0]}, {checks[1]}, and {checks[2]} by {fmt_date(review)}.", "security review scope")),
                    ("Reviewers should test cross-tenant search attempts and confirm that denied chunks never enter model context.", None),
                ]),
            ],
            "legal": [
                (f"{P} vendor contract summary", [
                    (f"The {P} contract with {(v := R.choice(VENDORS))} renews on {fmt_date(self.day())}. The notice period is {(nd := R.choice([30, 60, 90]))} days.",
                     (f"How long is the notice period for the {P} vendor contract?", f"The notice period for the {P} contract with {v} is {nd} days.", "contract notice period")),
                ]),
            ],
            "hr": [
                (f"{P} staffing plan", [
                    (f"The {P} team plans to hire {(nh := R.randint(2, 25))} people by {fmt_date(self.day())}. Onboarding takes {(wk := R.randint(2, 8))} weeks.",
                     (f"How many people does the {P} team plan to hire?", f"The {P} team plans to hire {nh} people.", "hiring plan")),
                ]),
            ],
            "sales": [
                (f"{P} go-to-market plan", [
                    (f"Sales targets {(nc := R.randint(3, 60))} pilot customers for {P} by {fmt_date(self.day())}.",
                     (f"How many pilot customers does Sales target for {P}?", f"Sales targets {nc} pilot customers for {P}.", "pilot customer target")),
                ]),
            ],
            "research": [
                (f"{P} research plan", [
                    (f"The {P} research team records prototype findings every {(rd := R.choice(WEEKDAYS))}. Researchers must attach a test log before closing an experiment.",
                     (f"When does the {P} research team record prototype findings?", f"The {P} research team records findings every {rd}.", "research cadence")),
                ]),
            ],
            "product": [
                (f"{P} product requirements", [
                    (f"The {P} launch requires {feats[0]} and {feats[1]}. The product owner is {(po := self.person())}.",
                     (f"Who is the {P} product owner?", f"The {P} product owner is {po}.", "product owner")),
                ]),
            ],
            "support": [
                (f"{P} support SLA", [
                    (f"{P} priority-one tickets require a first response within {(sla := R.choice([15, 30, 60, 120]))} minutes, around the clock.",
                     (f"What is the first-response target for {P} priority-one tickets?", f"{P} priority-one tickets require a first response within {sla} minutes.", "priority-one SLA")),
                ]),
            ],
        }
        for dept in org.departments:
            for title, chunks in T[dept]:
                self.add_doc(org, title, [dept], [p], list(chunks))
        # Project-wide document: no department restriction.
        self.add_doc(org, f"{P} project overview", [], [p], [
            (f"{P} is an internal program at {org.name}. Its executive sponsor is {sponsor}.",
             (f"Who is the executive sponsor of {P}?", f"The executive sponsor of {P} is {sponsor}.", "executive sponsor")),
        ], classification="internal")

    def org_docs(self, org: Org) -> None:
        R = self.rng
        self.add_doc(org, "Travel and expense policy", [], [], [
            (f"Employees must submit expense reports within {(n := R.choice([14, 30, 45]))} days of travel.",
             ("How many days do employees have to submit expense reports?", f"Expense reports must be submitted within {n} days of travel.", "expense deadline")),
        ], classification="internal")
        self.add_doc(org, "Remote work policy", [], [], [
            (f"Employees may work remotely up to {(n := R.randint(2, 5))} days per week with manager approval.",
             ("How many days per week may employees work remotely?", f"Employees may work remotely up to {n} days per week.", "remote work allowance")),
        ], classification="public")
        for dept in org.departments:
            self.add_doc(org, f"{dept.title()} onboarding guide", [dept], [], [
                (f"New {dept} staff complete onboarding within {(n := R.randint(5, 30))} working days. Their onboarding buddy is assigned by the {dept} lead.",
                 (f"How long does {dept} onboarding take?", f"New {dept} staff complete onboarding within {n} working days.", "onboarding length")),
            ])

    def meeting_notes(self, org: Org) -> None:
        """Bulk documents with unique facts, to reach docs_per_org."""
        while len(org.documents) < self.docs_per_org:
            p = self.rng.choice(org.projects)
            P = p.title()
            depts = self.rng.sample(org.departments, 2 if self.rng.random() < 0.1 else 1)
            meet = self.day(date(2026, 6, 1), 700)
            due = meet + timedelta(days=self.rng.randint(5, 45))
            owner = self.person()
            action = self.rng.choice(ACTIONS)
            dlabel = " and ".join(d.title() for d in depts)
            self.add_doc(org, f"{P} {dlabel} sync notes, {meet.isoformat()}", depts, [p], [
                (f"On {fmt_date(meet)}, the {P} {dlabel.lower()} team agreed that {owner} will {action} by {fmt_date(due)}.",
                 (f"According to the {fmt_date(meet)} {P} {dlabel.lower()} sync, who will {action}?",
                  f"{owner} will {action} by {fmt_date(due)}.", f"{fmt_date(meet)} action owner")),
            ], bulk=True)

    # ---------- evaluation ----------
    def readers(self, users: list[dict], doc: dict, allowed: bool) -> list[dict]:
        return [u for u in users if can_read(u, doc) == allowed]

    def build_cases(self, org: Org) -> list[dict]:
        R, cases = self.rng, []
        others = [o for o in self.orgs if o is not org]
        pairs = [(p, a, b) for p in org.projects for a in org.departments for b in org.departments
                 if a < b and org.project_facts.get((p, a)) and org.project_facts.get((p, b))]
        attempts = 0
        while len(cases) < self.cases_per_org and attempts < self.cases_per_org * 20:
            attempts += 1
            kind = R.choices(["authorized", "denied", "cross_tenant", "compound"], [55, 15, 5, 25])[0]
            case_id = f"gen-case-{org.idx + 1:03d}-{len(cases) + 1:05d}"
            if kind == "compound" and pairs:
                p, a, b = R.choice(pairs)
                fa, fb = R.choice(org.project_facts[(p, a)]), R.choice(org.project_facts[(p, b)])
                da, db = self.chunk_doc[fa.chunk_id], self.chunk_doc[fb.chunk_id]
                some = [u for u in org.users if can_read(u, da) or can_read(u, db)]
                user = R.choice(some if some and R.random() < 0.85 else org.users)
                q = f"{fa.question[:-1]}, and {fb.question[0].lower()}{fb.question[1:]}"
                ok = [f for f in (fa, fb) if can_read(user, self.chunk_doc[f.chunk_id])]
                missing = [f for f in (fa, fb) if f not in ok]
                if not ok:
                    answer = ABSTAIN
                else:
                    answer = " ".join(f.answer for f in ok)
                    answer += "".join(f" The {f.label} is not available to this user." for f in missing)
                cases.append(self.case(case_id, user, q, ok, answer, [fa, fb], kind))
                continue
            fact = R.choice(org.bulk_facts if org.bulk_facts and R.random() < 0.35 else org.facts)
            doc = self.chunk_doc[fact.chunk_id]
            if kind == "cross_tenant" and others:
                user = R.choice(R.choice(others).users)
            else:
                pool = self.readers(org.users, doc, kind == "authorized")
                if not pool:
                    continue
                user = R.choice(pool)
            ok = [fact] if can_read(user, doc) else []
            cases.append(self.case(case_id, user, fact.question, ok,
                                   fact.answer if ok else ABSTAIN, [fact], kind))
        return cases

    @staticmethod
    def case(case_id: str, user: dict, q: str, ok: list[Fact], answer: str,
             targets: list[Fact], kind: str) -> dict:
        ids = [f.chunk_id for f in ok]
        return {
            "id": case_id, "user_id": user["id"], "question": q,
            "authorized_relevant_chunk_ids": ids, "expected_answer": answer,
            "expected_citation_chunk_ids": ids,
            # Not loaded into SQL; kept in JSON for test selection and leak checks.
            "case_type": kind, "target_chunk_ids": [f.chunk_id for f in targets],
        }

    # ---------- experiments ----------
    def build_experiment(self, org: Org, dataset: dict, user_index: dict[str, dict],
                         docs_by_org: dict[str, list[dict]]) -> dict:
        exp_id = f"gen-exp-{org.idx + 1:03d}"
        configs = [
            {"id": f"{exp_id}-dense", "retriever": "dense", "top_k": 5},
            {"id": f"{exp_id}-bm25", "retriever": "bm25", "top_k": 5},
            {"id": f"{exp_id}-hybrid", "retriever": "hybrid", "top_k": 5},
            # Deliberately broken baseline: ignores access rules so leak detectors have positives.
            {"id": f"{exp_id}-dense-unfiltered", "retriever": "dense-unfiltered", "top_k": 5},
        ]
        profile = {  # recall, base latency ms
            "dense": (0.82, 380), "bm25": (0.74, 160), "hybrid": (0.91, 520), "dense-unfiltered": (0.84, 360),
        }
        cache: dict[str, list[str]] = {}

        def pool_for(user: dict) -> list[str]:
            if user["id"] not in cache:
                cache[user["id"]] = [c["id"] for d in docs_by_org[user["organization_id"]]
                                     if can_read(user, d) for c in d["chunks"]]
            return cache[user["id"]]

        org_chunks = [c["id"] for d in org.documents for c in d["chunks"]]
        runs = []
        for config in configs:
            recall, base = profile[config["retriever"]]
            leaky = config["retriever"] == "dense-unfiltered"
            for r in range(self.runs_per_config):
                results = []
                for case in dataset["cases"]:
                    user = user_index[case["user_id"]]
                    pool = pool_for(user)
                    relevant = case["authorized_relevant_chunk_ids"]
                    found = [c for c in relevant if self.rng.random() < recall]
                    if leaky:
                        found += [c for c in case["target_chunk_ids"]
                                  if c not in relevant and self.rng.random() < 0.6]
                    k = config["top_k"]
                    source = org_chunks if leaky else pool
                    distractors = []
                    if source:
                        for c in self.rng.sample(source, min(len(source), k * 2)):
                            if c not in found and c not in relevant and len(distractors) < k - len(found):
                                distractors.append(c)
                    retrieved = found + distractors
                    # Rank relevant evidence near the top most of the time.
                    if self.rng.random() < 0.3:
                        self.rng.shuffle(retrieved)
                    retrieved = retrieved[:k]
                    cited = [c for c in retrieved if c in relevant and self.rng.random() < 0.95]
                    if leaky:
                        cited += [c for c in retrieved if c in case["target_chunk_ids"] and c not in relevant]
                    if retrieved and self.rng.random() < 0.04:
                        cited.append(self.rng.choice(retrieved))  # occasional wrong citation
                    cited = list(dict.fromkeys(cited))
                    ctx = sum(len(self.chunk_text[c]) for c in retrieved) // 4
                    results.append({
                        "case_id": case["id"],
                        "retrieved_chunk_ids": retrieved,
                        "answer_citation_chunk_ids": cited,
                        "latency_ms": max(20, int(self.rng.lognormvariate(0, 0.35) * base + 40 * len(retrieved))),
                        "input_tokens": 90 + len(case["question"]) // 4 + ctx,
                        "output_tokens": self.rng.randint(12, 24) if not cited else self.rng.randint(20, 90),
                    })
                runs.append({
                    "id": f"{config['id']}-run-{r + 1}", "configuration_id": config["id"],
                    "status": "completed", "evaluator_version": "gen-1", "results": results,
                })
        return {"id": exp_id, "dataset_id": dataset["id"], "dataset_version": dataset["version"],
                "configurations": configs, "runs": runs}

    # ---------- main ----------
    def build(self) -> dict:
        self.build_orgs()
        for org in self.orgs:
            for p in org.projects:
                self.project_docs(org, p)
            self.org_docs(org)
            self.meeting_notes(org)
        user_index = {u["id"]: u for o in self.orgs for u in o.users}
        docs_by_org = {o.id: o.documents for o in self.orgs}
        datasets, experiments = [], []
        for org in self.orgs:
            ds = {"id": f"gen-dataset-{org.idx + 1:03d}", "version": 1,
                  "organization_id": org.id, "cases": self.build_cases(org)}
            datasets.append(ds)
            experiments.append(self.build_experiment(org, ds, user_index, docs_by_org))
        return {
            "fixture_version": "gen-1.0",
            "description": "Generated synthetic records for load, authorization, retrieval, and evaluation tests. No real people or company data.",
            "generator": {"seed": self.seed, "orgs": self.n_orgs, "users_per_org": self.users_per_org,
                          "docs_per_org": self.docs_per_org, "cases_per_org": self.cases_per_org,
                          "runs_per_config": self.runs_per_config},
            "organizations": [{"id": o.id, "name": o.name} for o in self.orgs],
            "workspaces": [w for o in self.orgs for w in o.workspaces],
            "users": [u for o in self.orgs for u in o.users],
            "documents": [d for o in self.orgs for d in o.documents],
            "evaluation_datasets": datasets,
            "experiments": experiments,
        }


# ---------- validation ----------
def validate(fx: dict) -> None:
    users = {u["id"]: u for u in fx["users"]}
    chunk_doc = {c["id"]: d for d in fx["documents"] for c in d["chunks"]}
    case_ids = set()
    for ds in fx["evaluation_datasets"]:
        for case in ds["cases"]:
            assert case["id"] not in case_ids, case["id"]
            case_ids.add(case["id"])
            user = users[case["user_id"]]
            for cid in case["authorized_relevant_chunk_ids"]:
                assert can_read(user, chunk_doc[cid]), (case["id"], cid)
            for cid in case["target_chunk_ids"]:
                if cid not in case["authorized_relevant_chunk_ids"]:
                    assert not can_read(user, chunk_doc[cid]), (case["id"], cid)
    for exp in fx["experiments"]:
        for run in exp["runs"]:
            for res in run["results"]:
                assert res["case_id"] in case_ids
                assert all(c in chunk_doc for c in res["retrieved_chunk_ids"])


# ---------- SQL output ----------
def copy_value(v: object) -> str:
    if isinstance(v, list):
        v = "{" + ",".join('"' + str(e).replace("\\", "\\\\").replace('"', '\\"') + '"' for e in v) + "}"
    s = str(v)
    return s.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")


TABLE_ORDER = [
    "organizations", "workspaces", "users", "documents", "document_chunks", "evaluation_datasets",
    "evaluation_cases", "experiments", "experiment_configurations", "experiment_runs", "experiment_results",
]


def table_rows(fx: dict) -> dict[str, tuple[list[str], list[list]]]:
    def rows(cols, items):
        return cols, [[it[c] for c in cols] for it in items]

    docs = fx["documents"]
    cases = [{**c, "dataset_id": ds["id"]} for ds in fx["evaluation_datasets"] for c in ds["cases"]]
    configs = [{**c, "experiment_id": e["id"]} for e in fx["experiments"] for c in e["configurations"]]
    runs = [{**r, "experiment_id": e["id"]} for e in fx["experiments"] for r in e["runs"]]
    results = [{**res, "run_id": r["id"]} for r in runs for res in r["results"]]
    return {
        "organizations": rows(["id", "name"], fx["organizations"]),
        "workspaces": rows(["id", "organization_id", "name"], fx["workspaces"]),
        "users": rows(["id", "organization_id", "name", "role", "departments", "projects"], fx["users"]),
        "documents": rows(["id", "organization_id", "workspace_id", "title", "version", "owner_user_id",
                           "classification", "departments", "projects"], docs),
        "document_chunks": rows(["id", "document_id", "text"],
                                [{**c, "document_id": d["id"]} for d in docs for c in d["chunks"]]),
        "evaluation_datasets": rows(["id", "version", "organization_id"], fx["evaluation_datasets"]),
        "evaluation_cases": rows(["id", "dataset_id", "user_id", "question", "authorized_relevant_chunk_ids",
                                  "expected_answer", "expected_citation_chunk_ids"], cases),
        "experiments": rows(["id", "dataset_id", "dataset_version"], fx["experiments"]),
        "experiment_configurations": rows(["id", "experiment_id", "retriever", "top_k"], configs),
        "experiment_runs": rows(["id", "experiment_id", "configuration_id", "status", "evaluator_version"], runs),
        "experiment_results": rows(["run_id", "case_id", "retrieved_chunk_ids", "answer_citation_chunk_ids",
                                    "latency_ms", "input_tokens", "output_tokens"], results),
    }


def write_sql(fx: dict, path: Path) -> dict[str, int]:
    tables = table_rows(fx)
    counts = {}
    with path.open("w", encoding="utf-8") as f:
        f.write("-- Generated by mock_data/generate.py. Replaces all rows whose IDs start with 'gen-'.\n")
        f.write("BEGIN;\n")
        for t in reversed(TABLE_ORDER):
            key = "run_id" if t == "experiment_results" else "id"
            f.write(f"DELETE FROM eke_demo.{t} WHERE {key} LIKE 'gen-%';\n")
        for t in TABLE_ORDER:
            cols, rows = tables[t]
            counts[t] = len(rows)
            f.write(f"COPY eke_demo.{t} ({', '.join(cols)}) FROM stdin;\n")
            for row in rows:
                f.write("\t".join(copy_value(v) for v in row) + "\n")
            f.write("\\.\n")
        f.write("ANALYZE eke_demo.users; ANALYZE eke_demo.documents; ANALYZE eke_demo.document_chunks;\n")
        f.write("COMMIT;\n")
    return counts


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scale", choices=SCALES, default="medium")
    ap.add_argument("--seed", type=int, default=2027)
    ap.add_argument("--orgs", type=int)
    ap.add_argument("--users-per-org", type=int)
    ap.add_argument("--docs-per-org", type=int)
    ap.add_argument("--cases-per-org", type=int)
    ap.add_argument("--runs-per-config", type=int)
    ap.add_argument("--out", type=Path, help="output directory (default: mock_data/generated/<scale>)")
    a = ap.parse_args()

    orgs, upo, dpo, cpo, rpc = SCALES[a.scale]
    gen = Generator(a.seed, a.orgs or orgs, a.users_per_org or upo, a.docs_per_org or dpo,
                    a.cases_per_org or cpo, a.runs_per_config or rpc)
    fx = gen.build()
    validate(fx)

    out = a.out or Path(__file__).with_name("generated") / a.scale
    out.mkdir(parents=True, exist_ok=True)
    (out / "fixture.json").write_text(json.dumps(fx, ensure_ascii=False), encoding="utf-8")
    counts = write_sql(fx, out / "load.sql")
    kinds = Counter(c["case_type"] for ds in fx["evaluation_datasets"] for c in ds["cases"])
    print(f"Wrote {out}/fixture.json and {out}/load.sql")
    for t, n in counts.items():
        print(f"  {t:<27}{n:>10,}")
    print("  case types: " + ", ".join(f"{k}={v:,}" for k, v in sorted(kinds.items())))


if __name__ == "__main__":
    main()
