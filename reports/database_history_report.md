# TruthLens AI — Phase 10 Database, Analysis History & Persistence Report

## 1. Database Technology
- **Database Engine**: SQLite 3 (relational, zero-configuration, lightweight prototype persistence)
- **ORM / Abstraction**: Flask-SQLAlchemy 3.1.1 (SQLAlchemy 2.x declarative core)
- **Connection Model**: Application-scoped session management with thread-safe request lifecycles, pooled connections, and automatic rollback on transaction errors.

## 2. Database Location
- **Canonical Database Path**: `database/truthlens.db` (resolved relative to `truthlens-ai` base directory: `truthlens-ai/database/truthlens.db`)
- **Config Management**: Parameterized via `Config.SQLALCHEMY_DATABASE_URI` with environment variable override (`DATABASE_URL`).
- **Isolation Constraint**: The database resides in the dedicated `database/` directory and is strictly isolated from source code, model checkpoints (`models/`), and raw datasets (`data/`).
- **Automated Testing Isolation**: Automated test suites dynamically configure `sqlite:///:memory:`, guaranteeing zero mutation or pollution of production database records.

## 3. Database Schema

The persistence model is standardized in the `Analysis` class (`database.py`), mapped to the `analysis` table:

```sql
CREATE TABLE analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at DATETIME NOT NULL,
    input_text TEXT NOT NULL,
    predicted_label VARCHAR(50) NOT NULL,
    confidence FLOAT NOT NULL,
    verification_status VARCHAR(50) NOT NULL DEFAULT 'UNVERIFIED',
    evidence_status VARCHAR(50) NOT NULL DEFAULT 'insufficient',
    class_probabilities JSON NOT NULL,
    important_phrases JSON,
    explanation_summary TEXT,
    evidence_summary TEXT,
    evidence_sources JSON,
    final_assessment TEXT,
    conflict_detected BOOLEAN DEFAULT 0
);
```

### Attribute Index:
| Column Name | Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `id` | Integer | No (PK) | Unique auto-incremented analysis record identifier |
| `created_at` | DateTime(tz=True) | No | Timezone-aware UTC timestamp indexed for efficient reverse-chronological sorting |
| `input_text` | Text | No | Original verbatim claim or text excerpt submitted by user |
| `predicted_label` | String(50) | No | Classifier prediction (`False`, `Misleading`, or `Reliable`) |
| `confidence` | Float | No | Softmax probability score associated with the predicted class |
| `verification_status`| String(50) | No | External verification verdict (`SUPPORTED`, `CONTRADICTED`, `UNVERIFIED`) |
| `evidence_status` | String(50) | No | Evidence retrieval outcome (`supporting`, `contradicting`, `insufficient`) |
| `class_probabilities`| JSON | No | Full probability distribution across all three classes |
| `important_phrases` | JSON | Yes | Token attribution list (`phrase`, `importance`, `direction`) |
| `explanation_summary`| Text | Yes | Human-readable explanation of why the model made the prediction |
| `evidence_summary` | Text | Yes | Synthesis of corroborating/refuting external evidence |
| `evidence_sources` | JSON | Yes | Serialized list of retrieved citations (`title`, `source`, `url`, `snippet`, `relation`, `relevance_score`) |
| `final_assessment` | Text | Yes | Integrated final recommendation reconciling prediction and evidence |
| `conflict_detected` | Boolean | Yes | Flag indicating whether model prediction contradicts authoritative evidence |

## 4. Persistence Flow

```
User Form (POST /analyze)   OR   API Client (POST /api/analyze)
                     │
                     ▼
             validate_input_text()
                     │
                     ▼
           verify_claim() (AI Engine)
    ├─ DistilBERT Classifier & Probabilities
    ├─ Integrated Gradients Attribution Phrases
    ├─ Live Evidence Retrieval & Fact-Check Match
    └─ Synthesis & Conflict Detection
                     │
                     ▼
             Analysis DB Record
    db.session.add(record) -> db.session.commit()
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
   Web Flow:                 API Flow:
Redirect to /result/<id>    Return JSON:
                            {
                              "success": true,
                              "analysis_id": <id>,
                              "analysis": {...},
                              "data": {...}
                            }
```

Neither the web detail view (`/result/<id>`, `/history/<id>`) nor subsequent history queries trigger re-inference or rerun DistilBERT; all data is reconstituted faithfully from SQLite.

## 5. History Route (`GET /history`)
- **URL**: `GET /history`
- **Controller**: `history()` in `app.py`
- **Query**: `Analysis.query.order_by(Analysis.created_at.desc()).all()`
- **Presentation**: `templates/history.html`
- **Features**:
  - Displays records ordered strictly newest first.
  - Summarizes each analysis with ID (`#123`), readable UTC timestamp, shortened claim snippet (`claim[:90]...`), prediction badge, confidence percentage, and verification status.
  - Displays an informative empty state if no analyses exist yet.
  - Links directly to `/history/<id>` for full drill-down analysis inspection.

## 6. Analysis Detail Routes (`GET /result/<id>` & `GET /history/<id>`)
- **Unified Controller**: `_render_analysis_detail(analysis_id)` in `app.py`.
- **Consistency Guarantee**: Both `GET /result/<analysis_id>` and `GET /history/<analysis_id>` call the identical helper function and render `templates/result.html` with data from `record.to_dict()`.
- **Zero Rerun Guarantee**: Stored attributes (claim, prediction, confidence, full probabilities, attribution tokens, evidence snippets, URLs, and warnings) are restored from the database record without re-executing DistilBERT or re-querying external APIs.
- **Error Handling**: Non-existent or non-integer IDs immediately trigger HTTP 404 Not Found.

## 7. JSON Serialization & Safe Deserialization
Structured fields (`class_probabilities`, `important_phrases`, `evidence_sources`) are stored using SQLAlchemy `JSON` types.
- **Defensive Parsing (`Analysis.to_dict()`)**:
  - Encapsulated `safe_json()` parses strings, dicts, or lists, returning safe fallbacks on corrupt or empty values.
  - Probabilities are validated and coerced to ensure all three keys (`False`, `Misleading`, `Reliable`) exist with float values.
  - Each item in `important_phrases` is normalized with `phrase`, `importance`, and `direction`.
  - Each item in `evidence_sources` is normalized with `title`, `source`, `relation`, `relevance_score`, `snippet`, and `url`.
  - Missing optional fields do not crash template rendering or cause Jinja `UndefinedError`.

## 8. Timestamp Handling
- **Timezone-Aware Generation**: Replaced deprecated `datetime.utcnow()` with `datetime.now(timezone.utc)` via helper `utc_now()`.
- **Database Column**: `DateTime(timezone=True)` with index on `created_at` for high-performance sorting.
- **Serialization**: Formatted cleanly as ISO-like UTC strings (`YYYY-MM-DD HH:MM:SS UTC` for detail views, `YYYY-MM-DD HH:MM UTC` for history lists).

## 9. Error Handling
- **Rollback on Error**: All write operations wrap database commits in try/except blocks with explicit `db.session.rollback()`.
- **Input Validation**: Text length validation (5 to 10,000 characters) prevents invalid rows.
- **Database Integrity**: Missing mandatory fields violate database constraints and raise `IntegrityError`, caught and logged safely.
- **No Path Leakage**: SQLite database paths, secret keys, and internal tracebacks are masked from public responses.

## 10. Tests Performed

### Database Unit Tests (`tests/test_database.py`):
1. **Database Initialization**: Verified database connection and initialization inside Flask application context.
2. **Table Creation**: Inspected schema tables and verified all 14 mandatory columns exist in `analysis`.
3. **Insert Analysis**: Verified complete end-to-end insertion of an analysis record.
4. **Retrieve Analysis**: Verified bulk querying of persisted records.
5. **Retrieve by ID**: Verified lookup via primary key ID.
6. **History Ordering**: Inserted records with staggered timestamps; verified strict reverse-chronological ordering.
7. **JSON Serialization Roundtrip**: Verified dictionary/list serialization and deserialization of probabilities, phrases, and evidence citations.
8. **Missing Optional Fields**: Verified safe default fallbacks when phrases, sources, or summaries are null.
9. **Persistence Across Contexts**: Verified record persistence across independent application context lifecycles.
10. **Integrity Constraints**: Verified that null values in required non-nullable columns trigger `IntegrityError`.

### Route & Integration Tests (`tests/test_app.py` & `tests/test_api.py`):
1. **GET /history**: Verified empty state and populated reverse-chronological history list.
2. **GET /history/<valid_id>**: Verified rendering of full saved report without inference.
3. **GET /history/<invalid_id>**: Verified HTTP 404 response.
4. **Result / History Route Consistency**: Verified `/result/<id>` and `/history/<id>` produce identical HTML responses.
5. **POST /analyze Persistence**: Verified redirection to `/result/<id>` and presence of persisted record.
6. **POST /api/analyze Persistence**: Verified returning `analysis_id` and successful retrieval from database.

## 11. Test Results Summary

| Test Suite | Total Tests | Passed | Failed |
| :--- | :---: | :---: | :---: |
| `tests/test_database.py` | 10 | 10 | 0 |
| `tests/test_app.py` | 12 | 12 | 0 |
| `tests/test_api.py` | 8 | 8 | 0 |
| **Total Automated Tests** | **30** | **30** | **0** |

All 30 unit and integration tests passed cleanly in 7.03 seconds with zero regressions.
