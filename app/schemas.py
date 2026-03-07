from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TripRequest(BaseModel):
    prompt: str = Field(
        min_length=10,
        max_length=1000,
        description="Natural language request for the trip.",
    )
    days: int = Field(default=7, ge=1, le=21)
    budget_level: Literal["low", "medium", "high"] = "medium"
    pace: Literal["relaxed", "balanced", "intense"] = "balanced"
    start_city: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=500)


class PlaceItem(BaseModel):
    name: str
    area: str
    category: str
    start_time: str | None = None
    duration_hours: float | None = Field(default=None, ge=0.5, le=12.0)
    estimated_cost_usd: float | None = Field(default=None, ge=0.0)
    reason: str | None = None


class DayItinerary(BaseModel):
    day: int = Field(ge=1)
    title: str
    focus: str
    places: list[PlaceItem]
    food_recommendations: list[str] = Field(default_factory=list)
    transit_notes: list[str] = Field(default_factory=list)


class ItineraryPlan(BaseModel):
    destination_city: str
    destination_country: str
    summary: str
    assumptions: list[str] = Field(default_factory=list)
    total_estimated_cost_usd: float | None = Field(default=None, ge=0.0)
    days: list[DayItinerary]


class PlaceValidation(BaseModel):
    place_name: str
    requested_city: str
    requested_country: str
    exists: bool
    canonical_name: str | None = None
    display_name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    opening_hours: str | None = None
    source: str = "nominatim/overpass"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    notes: str | None = None


class RouteValidation(BaseModel):
    origin: str
    destination: str
    mode: str = "driving"
    duration_minutes: int | None = None
    distance_km: float | None = None
    source: str = "osrm"
    notes: str | None = None


class PlanResponse(BaseModel):
    request: TripRequest
    itinerary: ItineraryPlan
    place_validations: list[PlaceValidation]
    route_validations: list[RouteValidation]
    warnings: list[str] = Field(default_factory=list)
    conversation_log: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)
