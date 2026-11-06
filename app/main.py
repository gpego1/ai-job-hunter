import html
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, Query
from sqlalchemy import DateTime, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session

app = FastAPI(title="AI Job Hunter (local)", version="0.1.0")
engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)

class Base(DeclarativeBase):
    pass

class Job(Base):
    __tablename__ = "job_posts"
    key: Mapped[str] = mapped_column(String(250), primary_key=True)
    company: Mapped[str] = mapped_column(String(250))
    title: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(Text)
    location: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    description: Mapped[str] = mapped_column(Text)
    requirements: Mapped[str] = mapped_column(Text, default="[]")
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda:datetime.now(timezone.utc))

Base.metadata.create_all(engine)

TECHS = ["Java", "Spring Boot", "Spring Security", "JPA", "Hibernate", "SQL", "PostgreSQL", "MySQL", "Docker", "AWS", "Kafka", "REST", "JUnit", "Git", "Maven", "Gradle", "Python", "FastAPI","Django","Flask"]
JUNIOR = re.compile(r"\b(junior|júnior|jr|trainee|entry.level|est[aá]gio|intern(ship)?)\b", re.I)
SENIOR = re.compile(r"\b(senior|sênior|sr|staff|principal|lead|pleno|mid.level)\b", re.I)
BACKEND = re.compile(r"back[\s-]?end|software engineer|software developer|desenvolvedor|developer|engenheiro de software", re.I)


def cleaned(value: str | None) -> str:
    return BeautifulSoup(html.unescape(value or ""), "html.parser").get_text(" ", strip=True)


def parsedate(value):
    if not value:
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000, timezone.utc)
        date = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return date.replace(tzinfo=timezone.utc) if date.tzinfo is None else date
    except (ValueError, TypeError, OverflowError):
        return None


def qualifies(j, max_age_days):
    title = j["title"]
    description = j["description"]
    if not JUNIOR.search(title) or SENIOR.search(title):
        return False
    if not BACKEND.search(title):
        return False
    if not re.search(r"\bjava\b", f"{title} {description}", re.I):
        return False
    date = parsedate(j.get("published_at"))
    # Unknown original publication date is excluded from the recent-only MVP.
    if date is None or not (datetime.now(timezone.utc)-timedelta(days=max_age_days) <= date <= datetime.now(timezone.utc)+timedelta(minutes=5)):
        return False
    return True


def detected(text):
    return [name for name in TECHS if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text, re.I)]


def greenhouse(board, client):
    r = client.get(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs", params={"content":"true"})
    r.raise_for_status()
    for item in r.json().get("jobs", []):
        yield {"key":f"greenhouse:{board}:{item['id']}", "company":board, "title":item.get("title", ""), "url":item.get("absolute_url", ""), "location":(item.get("location") or {}).get("name", ""), "published_at":item.get("first_published"), "description":cleaned(item.get("content"))}


def lever(board, client):
    r = client.get(f"https://api.lever.co/v0/postings/{board}", params={"mode":"json"})
    r.raise_for_status()
    for item in r.json():
        fields = item.get("categories") or {}
        text = " ".join([cleaned(item.get("descriptionPlain") or item.get("description")), cleaned(item.get("additionalPlain") or item.get("additional"))] + [cleaned(x.get("content")) for x in item.get("lists", [])])
        yield {"key":f"lever:{board}:{item['id']}", "company":board, "title":item.get("text", ""), "url":item.get("hostedUrl", ""), "location":fields.get("location", ""), "published_at":item.get("createdAt"), "description":text}


@app.get("/health")
def health():
    return {"status":"ok"}


@app.get("/jobs/search")
def search_jobs(days: int = Query(7, ge=1, le=30)):
    boards = json.loads(Path("config/companies.json").read_text(encoding="utf-8"))
    results = []
    errors = []

    timeout = httpx.Timeout(
        connect=10.0,
        read=45.0,
        write=10.0,
        pool=10.0
    )
    transport = httpx.HTTPTransport(
        retries=2
    )

    with httpx.Client(
        timeout=timeout,
        transport=transport,
        follow_redirects=False,
        headers={
            "User-Agent":"AIJobHunter/0.1 (personal research)"
            }) as client, Session(engine) as db:
        for source, scraper in (("greenhouse",greenhouse),("lever",lever)):
            for board in boards.get(source, []):
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", board):
                    errors.append(f"Invalid board token for {source}")
                    continue
                try:
                    for j in scraper(board, client):
                        if not j["url"].startswith("https://") or not qualifies(j, days):
                            continue
                        j["requirements_detected"] = detected(j["description"])
                        existing = db.get(Job, j["key"])
                        if existing is None:
                            db.add(Job(key=j["key"], company=j["company"], title=j["title"], url=j["url"], location=j["location"], published_at=parsedate(j["published_at"]), description=j["description"], requirements=json.dumps(j["requirements_detected"])))
                        else:
                            existing.description = j["description"]
                            existing.requirements = json.dumps(j["requirements_detected"])
                        results.append(j)
                except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                    errors.append(f"{source}/{board}: {type(exc).__name__}: {str(exc)[:160]}")
        db.commit()
    return {"count":len(results), "jobs":results, "errors":errors}


@app.get("/jobs")
def list_jobs(limit: int = Query(50, ge=1, le=500)):
    with Session(engine) as db:
        rows = db.scalars(select(Job).order_by(Job.seen_at.desc()).limit(limit)).all()
        return [{"key":row.key,"title":row.title,"company":row.company,"url":row.url,"location":row.location,"published_at":row.published_at,"requirements_detected":json.loads(row.requirements)} for row in rows]
