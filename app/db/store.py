"""SQLite schema v1. Refuse unknown schema versions; never silently drop tables."""

import json
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Text, create_engine, delete, select
from sqlalchemy.orm import DeclarativeBase, Session

from app.core.config import DATA


class Base(DeclarativeBase):
    pass


class Schema(Base):
    __tablename__ = "schema_version"
    version = Column(Integer, primary_key=True)


class Run(Base):
    __tablename__ = "runs"
    id = Column(String, primary_key=True)
    created = Column(String, nullable=False)
    benchmark = Column(String, nullable=False)
    status = Column(String, nullable=False)
    project = Column(String, nullable=False)
    payload = Column(Text, nullable=False)


class Profile(Base):
    __tablename__ = "profiles"
    name = Column(String, primary_key=True)
    payload = Column(Text, nullable=False)


class Usage(Base):
    __tablename__ = "usage"
    id = Column(Integer, primary_key=True)
    provider = Column(String, nullable=False)
    payload = Column(Text, nullable=False)


class Store:
    def __init__(self, path=None):
        self.engine = create_engine(
            f"sqlite:///{path or DATA / 'verifier.sqlite3'}",
            connect_args={"check_same_thread": False, "timeout": 30},
        )
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            versions = list(session.scalars(select(Schema.version)))
            if not versions:
                session.add(Schema(version=1))
                session.commit()
            elif versions != [1]:
                raise RuntimeError(
                    "Unsupported database schema: backup DB and run documented migration"
                )

    def save_run(self, payload):
        with Session(self.engine) as session:
            session.add(
                Run(
                    id=payload["id"],
                    created=datetime.now(timezone.utc).isoformat(),
                    benchmark=payload["request"]["benchmark"],
                    status=payload["status"],
                    project=payload["request"]["project"],
                    payload=json.dumps(payload, default=str),
                )
            )
            session.commit()

    def get(self, run_id):
        with Session(self.engine) as session:
            row = session.get(Run, run_id)
            return json.loads(row.payload) if row else None

    def history(self):
        with Session(self.engine) as session:
            return [
                {
                    "id": r.id,
                    "created": r.created,
                    "benchmark": r.benchmark,
                    "status": r.status,
                    "project": r.project,
                    "provider": json.loads(r.payload)["request"]["provider"],
                    "model": json.loads(r.payload)["request"]["model"],
                    "passed": json.loads(r.payload)["passed"],
                    "failed": json.loads(r.payload)["failed"],
                    "accuracy": json.loads(r.payload)["accuracy"],
                    "reference_failures": json.loads(r.payload)["reference_failures"],
                    "generation_latency": (
                        json.loads(r.payload)["request"].get("generation") or {}
                    ).get("latency_seconds"),
                    "generation_usage": (
                        json.loads(r.payload)["request"].get("generation") or {}
                    ).get("usage"),
                    "estimated_cost_usd": (
                        json.loads(r.payload)["request"].get("generation") or {}
                    ).get("estimated_cost_usd"),
                }
                for r in session.scalars(select(Run).order_by(Run.created.desc()).limit(1000))
            ]

    def counterexamples(self):
        groups = {}
        with Session(self.engine) as session:
            for row in session.scalars(select(Run).order_by(Run.created.desc()).limit(1000)):
                result = json.loads(row.payload)
                failure = result.get("counterexample")
                if not failure:
                    continue
                fingerprint = failure["fingerprint"]
                if fingerprint not in groups:
                    groups[fingerprint] = {
                        "fingerprint": fingerprint,
                        "benchmark": row.benchmark,
                        "candidate": result["request"]["candidate"],
                        "expected": failure["expected"],
                        "actual": failure["actual"],
                        "representative_run": row.id,
                        "run_ids": [],
                        "occurrences": 0,
                    }
                groups[fingerprint]["run_ids"].append(row.id)
                groups[fingerprint]["occurrences"] += 1
        return list(groups.values())

    def remove(self, run_id):
        with Session(self.engine) as session:
            session.execute(delete(Run).where(Run.id == run_id))
            session.commit()

    def profiles(self):
        with Session(self.engine) as session:
            return [json.loads(r.payload) for r in session.scalars(select(Profile))]

    def profile(self, name):
        return next((p for p in self.profiles() if p["name"] == name), None)

    def save_profile(self, profile):
        with Session(self.engine) as session:
            if profile.get("default"):
                for row in session.scalars(select(Profile)):
                    p = json.loads(row.payload)
                    p["default"] = False
                    row.payload = json.dumps(p)
            session.merge(Profile(name=profile["name"], payload=json.dumps(profile)))
            session.commit()

    def usage(self, name):
        with Session(self.engine) as session:
            return [
                json.loads(r.payload)
                for r in session.scalars(select(Usage).where(Usage.provider == name))
            ]

    def record_usage(self, name, payload):
        with Session(self.engine) as session:
            session.add(Usage(provider=name, payload=json.dumps(payload)))
            session.commit()
