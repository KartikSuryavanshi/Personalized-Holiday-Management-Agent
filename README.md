# Personalized Holiday Management Agent

An autonomous multi-agent travel planner built with **Microsoft AutoGen**, **FastAPI**, and free model services.

## What This Project Solves

Many travel assistants generate attractive but impractical plans. This project separates planning and factual validation, then hardens the final result so users always get complete itinerary details.

- **Planner Agent** creates the day-by-day trip draft.
- **Researcher Agent** verifies place feasibility and movement realism.
- **Validation + Enrichment layer** fills missing time, duration, cost, and opening-hours fields.

## End-to-End Project Flow

1. User submits a trip request from web UI (`/`) or CLI (`main.py`).
2. FastAPI receives input at `POST /plan` (or `/plan/ui`) and validates `TripRequest`.
3. `HolidayTeam` starts a `RoundRobinGroupChat` with Planner + Researcher agents.
4. Planner and Researcher collaborate until `FINAL_ITINERARY_JSON` or max rounds.
5. Raw model output is parsed into strict JSON (`ItineraryPlan`).
6. If planner JSON is malformed, the recovery formatter rewrites transcript output into schema-valid JSON.
7. Post-validation runs against free public data services: place existence via Nominatim, opening hours (when available) via Overpass, and inter-place travel duration/distance via OSRM.
8. Deterministic enrichment fills missing itinerary fields: `start_time` (normalized and auto-scheduled), `duration_hours` (category + pace defaults), `estimated_cost_usd` (category + budget defaults), `opening_hours` (verified value or category fallback), and `total_estimated_cost_usd` (computed if missing).
9. Final `PlanResponse` is returned to API clients and rendered in UI with warnings and validation snapshots.

## Architecture Layers

1. **Users Layer**: Browser UI (`/` + form submit to `/plan/ui`) and CLI (`main.py`).
2. **API Layer (FastAPI)**: Routes in `app/api.py` with input/output validation via Pydantic schemas.
3. **Orchestration Layer (AutoGen)**: Planner + Researcher in `RoundRobinGroupChat` with flow control and recovery in `app/orchestration/workflow.py`.
4. **Support/Validation Layer**: Free API verification in `app/support/verifier.py`.
5. **Presentation Layer**: Jinja template in `app/templates/index.html` and styling in `app/static/styles.css`.

## Key File Responsibilities

- `app/config.py`: environment-driven runtime settings.
- `app/schemas.py`: Pydantic contracts (`TripRequest`, `ItineraryPlan`, `PlanResponse`, validations).
- `app/orchestration/prompts.py`: Planner/Researcher behavior contracts.
- `app/orchestration/parsing.py`: robust final-JSON extraction.
- `app/orchestration/workflow.py`: team orchestration, recovery, validation, and enrichment.
- `app/support/verifier.py`: Nominatim/Overpass/OSRM integrations.
- `app/api.py`: HTTP routes and UI rendering.
- `main.py`: CLI entrypoint.

## Project Structure

```text
app/
  api.py
  config.py
  schemas.py
  orchestration/
    llm.py
    parsing.py
    prompts.py
    tools.py
    workflow.py
  support/
    verifier.py
  templates/
    index.html
  static/
    styles.css
main.py
requirements.txt
.env.example
tests/
```

## Setup (Free Local Model Path)

1. Create and activate virtual environment.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Install and start Ollama.

```bash
brew install --cask ollama
ollama serve
```

3. Pull the default local model.

```bash
ollama pull llama3.2:3b
```

4. Create local environment file.

```bash
cp .env.example .env
```

5. Start API server.

```bash
uvicorn app:app --reload
```

6. Open web UI at <http://127.0.0.1:8000>

7. Optional CLI run.

```bash
python main.py "I want a 7-day trip to Japan focused on anime and food"
```

## API Usage

`POST /plan`

Example request:

```json
{
  "prompt": "I want a 7-day trip to Japan focused on anime and food",
  "days": 7,
  "budget_level": "medium",
  "pace": "balanced",
  "start_city": "Mumbai",
  "notes": "No nightlife after 10 PM"
}
```

Example response highlights:

- `itinerary.days[].places[]` always includes `start_time`, `duration_hours`, `estimated_cost_usd`, `opening_hours`.
- `place_validations` and `route_validations` provide factual checks.
- `warnings` explains recoveries, data gaps, or long transfers.

## Testing

```bash
PYTHONPATH=. pytest -q
```

## UI Preview

The web UI is designed to make itinerary generation and verification easy to follow.

### 1. Trip Input Form-

Users can enter prompt, days, budget, pace, and notes from a single form.

![Trip input form](https://github.com/user-attachments/assets/6ea875a1-ada0-436d-8fc2-b2f4271a6d28)

### 2. Generated Itinerary View-

The app returns day-wise cards with timings, duration, cost, and opening-hours details.

![Generated itinerary view](https://github.com/user-attachments/assets/69707f03-d51b-4b4a-a291-4b490bcd672c)

### 3. Validation and Warnings Snapshot-

Users can inspect validation warnings and factual checks for places and routes.

![Validation and warnings snapshot](https://github.com/user-attachments/assets/61afbf65-152c-420f-820a-be92af2d3cac)


