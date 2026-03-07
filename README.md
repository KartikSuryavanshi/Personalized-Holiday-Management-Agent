# Personalized Holiday Management Agent

An autonomous multi-agent travel planner built with **Microsoft AutoGen**, **FastAPI**, and free data/model options.

## What This Project Solves

Standard travel chatbots often hallucinate places and schedules. This project splits reasoning into specialized agents:

- **Planner Agent**: Builds itinerary strategy and day plans.
- **Researcher Agent**: Validates place existence and movement feasibility.

The final output is a structured itinerary with post-generation verification warnings.

## Architecture

1. **Users Layer**

Browser UI (`/` + form submit to `/plan/ui`)
CLI (`main.py`)

1. **API Layer (FastAPI)**

Endpoint: `POST /plan`
Validates `TripRequest` and returns `PlanResponse`

1. **Orchestration Layer (AutoGen)**

`RoundRobinGroupChat` with Planner and Researcher
Termination on `FINAL_ITINERARY_JSON` token or max messages

1. **Support Layer (Free Data Sources)**

Place existence: OpenStreetMap Nominatim
Opening hours (when available): Overpass API
Route duration: OSRM

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

## Step-by-Step Setup (Free Model Path)

1. Clone/open this project and create a virtual environment.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

1. Install and start Ollama.

```bash
brew install ollama
ollama serve
```

1. Pull a free local model (in a second terminal).

```bash
ollama pull llama3.1:8b
```

1. Configure environment variables.

```bash
cp .env.example .env
```

1. Run the API server.

```bash
uvicorn app:app --reload
```

1. Open browser UI: <http://127.0.0.1:8000>

1. Run CLI mode.

```bash
python main.py "I want a 7-day trip to Japan focused on anime and food"
```

## API Usage

`POST /plan`

Example JSON body:

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

## Notes

- The architecture is provider-agnostic and uses an OpenAI-compatible endpoint.
- Defaults are configured for free local inference via Ollama.
- Public APIs may rate-limit; warnings are returned when validation cannot complete.

## Next Upgrade Ideas

- Add a `BudgetAgent` and `WeatherAgent`.
- Cache external API responses in Redis.
- Add persistent trip history storage.
- Stream intermediate planner/researcher turns to UI.
