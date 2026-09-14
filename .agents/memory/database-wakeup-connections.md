---
name: Database wake-up connections
description: Connection-pool behavior required when the production database suspends between periods of activity.
---

Keep connection health checks enabled for the SQLAlchemy pool when the production database is allowed to suspend between infrequent requests or scheduled jobs.

**Why:** Database suspension closes idle SSL sessions. Reusing one of those stale pooled sessions causes login, registration, and scheduled jobs to fail with `SSL connection has been closed unexpectedly`.

**How to apply:** Any database engine or pooling change must preserve pre-use connection validation and periodic recycling. This is especially important while background checks run less frequently than the database idle-suspension window.