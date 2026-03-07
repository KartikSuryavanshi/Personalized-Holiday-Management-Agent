from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.config import get_settings
from app.orchestration import HolidayTeam
from app.schemas import PlanResponse, TripRequest


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="1.0.0")

    templates = Jinja2Templates(directory="app/templates")
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    team = HolidayTeam(settings)

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "result": None,
                "error": None,
            },
        )

    @app.post("/plan", response_model=PlanResponse)
    async def plan_trip(payload: TripRequest) -> PlanResponse:
        try:
            return await team.plan(payload)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Planning failed: {exc}") from exc

    @app.post("/plan/ui", response_class=HTMLResponse)
    async def plan_trip_from_form(
        request: Request,
        prompt: str = Form(...),
        days: int = Form(7),
        budget_level: str = Form("medium"),
        pace: str = Form("balanced"),
        start_city: str = Form(""),
        notes: str = Form(""),
    ) -> HTMLResponse:
        try:
            payload = TripRequest(
                prompt=prompt,
                days=days,
                budget_level=budget_level,
                pace=pace,
                start_city=start_city.strip() or None,
                notes=notes.strip() or None,
            )
            result = await team.plan(payload)
            return templates.TemplateResponse(
                "index.html",
                {
                    "request": request,
                    "result": result.model_dump(),
                    "error": None,
                },
            )
        except ValidationError as exc:
            return templates.TemplateResponse(
                "index.html",
                {
                    "request": request,
                    "result": None,
                    "error": f"Invalid input: {exc.errors()}",
                },
                status_code=422,
            )
        except Exception as exc:
            return templates.TemplateResponse(
                "index.html",
                {
                    "request": request,
                    "result": None,
                    "error": f"Planning failed: {exc}",
                },
                status_code=500,
            )

    return app
