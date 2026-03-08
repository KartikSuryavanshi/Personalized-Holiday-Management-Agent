import json
import inspect
import re
from typing import Any

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import MaxMessageTermination, TextMentionTermination
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_core.models import SystemMessage, UserMessage
from pydantic import ValidationError

from app.config import Settings
from app.schemas import (
    ItineraryPlan,
    PlanResponse,
    PlaceValidation,
    RouteValidation,
    TripRequest,
)
from app.support.verifier import TravelDataVerifier

from .llm import build_model_client
from .parsing import extract_final_itinerary_json
from .prompts import PLANNER_SYSTEM_PROMPT, RESEARCHER_SYSTEM_PROMPT
from .tools import ResearchTools

FINAL_TOKEN = "FINAL_ITINERARY_JSON"
DEFAULT_DAY_START_MINUTES = 9 * 60
DEFAULT_TRANSFER_MINUTES = 30

PACE_DURATION_MULTIPLIER = {
    "relaxed": 1.15,
    "balanced": 1.0,
    "intense": 0.85,
}

BUDGET_COST_MULTIPLIER = {
    "low": 0.75,
    "medium": 1.0,
    "high": 1.35,
}

CATEGORY_DURATION_HOURS = {
    "landmark": 1.5,
    "museum": 2.5,
    "beach": 2.0,
    "park": 1.5,
    "market": 2.0,
    "shopping": 2.0,
    "temple": 1.0,
    "mosque": 1.0,
    "church": 1.0,
    "fort": 2.0,
    "station": 1.0,
    "neighborhood": 2.0,
    "food": 1.25,
    "restaurant": 1.5,
    "cafe": 1.0,
    "default": 1.75,
}

CATEGORY_COST_USD = {
    "landmark": 8.0,
    "museum": 15.0,
    "beach": 3.0,
    "park": 3.0,
    "market": 12.0,
    "shopping": 25.0,
    "temple": 4.0,
    "mosque": 3.0,
    "church": 3.0,
    "fort": 10.0,
    "station": 2.0,
    "neighborhood": 8.0,
    "food": 12.0,
    "restaurant": 20.0,
    "cafe": 8.0,
    "default": 10.0,
}

CATEGORY_OPENING_HOURS = {
    "landmark": "09:00-18:00 (typical)",
    "museum": "10:00-18:00 (typical)",
    "beach": "06:00-22:00 (typical)",
    "park": "06:00-20:00 (typical)",
    "market": "10:00-21:00 (typical)",
    "shopping": "10:00-22:00 (typical)",
    "temple": "06:00-21:00 (typical)",
    "mosque": "05:00-22:00 (typical)",
    "church": "07:00-20:00 (typical)",
    "fort": "09:00-17:30 (typical)",
    "station": "Open 24 hours",
    "neighborhood": "Open area (no fixed hours)",
    "food": "11:00-23:00 (typical)",
    "restaurant": "12:00-23:00 (typical)",
    "cafe": "08:00-22:00 (typical)",
    "default": "09:00-20:00 (typical)",
}


class HolidayTeam:
    """Coordinates multi-agent planning and factual verification."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def plan(self, request: TripRequest) -> PlanResponse:
        model_client = build_model_client(self._settings)
        verifier = TravelDataVerifier(self._settings)

        try:
            planner = AssistantAgent(
                name="planner_agent",
                model_client=model_client,
                system_message=PLANNER_SYSTEM_PROMPT,
            )

            researcher_tools = ResearchTools(verifier)
            researcher = AssistantAgent(
                name="researcher_agent",
                model_client=model_client,
                system_message=RESEARCHER_SYSTEM_PROMPT,
                tools=[researcher_tools.verify_place, researcher_tools.estimate_route],
            )

            termination = (
                MaxMessageTermination(self._settings.max_round_messages)
                | TextMentionTermination(FINAL_TOKEN)
            )

            team = RoundRobinGroupChat([planner, researcher], termination_condition=termination)
            result = await team.run(task=self._build_task_prompt(request))

            conversation_log = [self._stringify_message(message) for message in result.messages]
            recovery_warning: str | None = None
            try:
                raw_itinerary = extract_final_itinerary_json(conversation_log, FINAL_TOKEN)
                itinerary = self._validate_itinerary(raw_itinerary)
            except ValueError as parse_error:
                itinerary = await self._recover_itinerary_from_transcript(
                    model_client=model_client,
                    request=request,
                    conversation_log=conversation_log,
                    parse_error=parse_error,
                )
                recovery_warning = (
                    "Planner output was not valid JSON on first pass. "
                    "Recovered itinerary using strict schema formatting."
                )

            place_validations, route_validations, warnings = await self._post_validate(
                itinerary=itinerary,
                verifier=verifier,
            )
            warnings.extend(
                self._enrich_itinerary(
                    itinerary=itinerary,
                    request=request,
                    place_validations=place_validations,
                )
            )

            if recovery_warning:
                warnings.insert(0, recovery_warning)

            if len(itinerary.days) != request.days:
                warnings.insert(
                    0,
                    (
                        f"Requested {request.days} days but planner produced "
                        f"{len(itinerary.days)} days."
                    ),
                )

            return PlanResponse(
                request=request,
                itinerary=itinerary,
                place_validations=place_validations,
                route_validations=route_validations,
                warnings=warnings,
                conversation_log=conversation_log,
            )
        finally:
            await verifier.close()
            await _close_model_client(model_client)

    def _build_task_prompt(self, request: TripRequest) -> str:
        notes = request.notes if request.notes else "None"
        start_city = request.start_city if request.start_city else "Not specified"

        return "\n".join(
            [
                "Build a realistic travel itinerary.",
                "",
                "User request:",
                f"- Prompt: {request.prompt}",
                f"- Number of days: {request.days}",
                f"- Budget: {request.budget_level}",
                f"- Pace: {request.pace}",
                f"- Start city: {start_city}",
                f"- Additional notes: {notes}",
                "",
                "Collaboration protocol:",
                "1) Planner drafts itinerary.",
                "2) Researcher validates facts and route realism using tools.",
                "3) Planner updates the itinerary.",
                f"4) Planner ends with {FINAL_TOKEN} and valid JSON.",
                "",
                "Keep data concrete: named districts, realistic time blocks, and practical movement.",
            ]
        )

    def _validate_itinerary(self, payload: dict[str, Any]) -> ItineraryPlan:
        try:
            itinerary = ItineraryPlan.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(f"Planner output does not match itinerary schema: {exc}") from exc

        if not itinerary.days:
            raise ValueError("Planner output included zero itinerary days.")
        return itinerary

    async def _recover_itinerary_from_transcript(
        self,
        model_client: Any,
        request: TripRequest,
        conversation_log: list[str],
        parse_error: Exception,
    ) -> ItineraryPlan:
        """Recover itinerary JSON when the multi-agent output is not machine-parsable."""

        transcript = self._truncate_transcript(conversation_log)
        schema_snippet = json.dumps(ItineraryPlan.model_json_schema(), ensure_ascii=True)

        recovery_messages = [
            SystemMessage(
                content=(
                    "You are a strict JSON formatter. Return only one JSON object that matches "
                    "the requested schema. No markdown, no explanations, no code fences."
                )
            ),
            UserMessage(
                source="holiday_orchestrator",
                content="\n".join(
                    [
                        "The planner/researcher conversation failed strict JSON extraction.",
                        f"Original parsing error: {parse_error}",
                        "",
                        "Trip constraints:",
                        f"- Prompt: {request.prompt}",
                        f"- Days: {request.days}",
                        f"- Budget: {request.budget_level}",
                        f"- Pace: {request.pace}",
                        f"- Start city: {request.start_city or 'Not specified'}",
                        f"- Notes: {request.notes or 'None'}",
                        "",
                        "Schema (JSON Schema):",
                        schema_snippet,
                        "",
                        "Conversation transcript (possibly noisy):",
                        transcript,
                        "",
                        "Output requirements:",
                        "1) Output valid JSON object only.",
                        f"2) Must contain exactly {request.days} days.",
                        "3) Keep destination and places realistic.",
                    ]
                ),
            ),
        ]

        repaired_content = await self._request_recovery_content(
            model_client=model_client,
            recovery_messages=recovery_messages,
        )

        try:
            return ItineraryPlan.model_validate_json(repaired_content)
        except ValidationError:
            repaired_payload = extract_final_itinerary_json([repaired_content], FINAL_TOKEN)
            return self._validate_itinerary(repaired_payload)

    async def _request_recovery_content(
        self,
        model_client: Any,
        recovery_messages: list[Any],
    ) -> str:
        """Ask the model to produce repair JSON with graceful compatibility fallbacks."""

        attempts: list[dict[str, Any]] = [
            {"json_output": ItineraryPlan},
            {"json_output": True},
            {},
        ]
        last_error: Exception | None = None

        for options in attempts:
            try:
                repair_result = await model_client.create(
                    messages=recovery_messages,
                    tool_choice="none",
                    **options,
                )
            except Exception as exc:
                last_error = exc
                continue

            repaired_content = repair_result.content
            if isinstance(repaired_content, str) and repaired_content.strip():
                return repaired_content

            last_error = ValueError("Recovery model returned empty or non-text content.")

        if last_error is None:
            last_error = ValueError("Recovery model call produced no usable output.")

        hint = (
            "Model backend unavailable or incompatible. "
            f"Check LLM_BASE_URL='{self._settings.llm_base_url}' and ensure model "
            f"'{self._settings.llm_model}' is running."
        )
        raise ValueError(f"{hint} Root cause: {last_error}") from last_error

    @staticmethod
    def _truncate_transcript(conversation_log: list[str], max_chars: int = 12000) -> str:
        if not conversation_log:
            return "(no transcript available)"

        transcript = "\n".join(conversation_log)
        if len(transcript) <= max_chars:
            return transcript
        return transcript[-max_chars:]

    async def _post_validate(
        self,
        itinerary: ItineraryPlan,
        verifier: TravelDataVerifier,
    ) -> tuple[list[PlaceValidation], list[RouteValidation], list[str]]:
        place_validations: list[PlaceValidation] = []
        route_validations: list[RouteValidation] = []
        warnings: list[str] = []

        for day in itinerary.days:
            for place in day.places:
                place_result = await verifier.verify_place(
                    place_name=place.name,
                    city=itinerary.destination_city,
                    country=itinerary.destination_country,
                )
                place_validations.append(place_result)

                if not place_result.exists:
                    warnings.append(
                        (
                            f"Day {day.day}: place '{place.name}' could not be verified "
                            "in open data sources."
                        )
                    )

            for index in range(len(day.places) - 1):
                origin = day.places[index].name
                destination = day.places[index + 1].name
                route_result = await verifier.estimate_route(
                    origin=origin,
                    destination=destination,
                    city=itinerary.destination_city,
                    country=itinerary.destination_country,
                    mode="driving",
                )
                route_validations.append(route_result)

                if route_result.duration_minutes is None:
                    warnings.append(
                        (
                            f"Day {day.day}: route validation missing for "
                            f"'{origin}' -> '{destination}'."
                        )
                    )
                elif route_result.duration_minutes > 120:
                    warnings.append(
                        (
                            f"Day {day.day}: long transfer detected ({route_result.duration_minutes} min) "
                            f"between '{origin}' and '{destination}'."
                        )
                    )

        return place_validations, route_validations, warnings

    def _enrich_itinerary(
        self,
        itinerary: ItineraryPlan,
        request: TripRequest,
        place_validations: list[PlaceValidation],
    ) -> list[str]:
        """Backfill missing itinerary fields for reliable UI output."""

        best_validation_by_name: dict[str, PlaceValidation] = {}
        for validation in place_validations:
            key = validation.place_name.strip().lower()
            existing = best_validation_by_name.get(key)
            if existing is None:
                best_validation_by_name[key] = validation
                continue

            candidate_score = (
                1 if validation.opening_hours else 0,
                validation.confidence,
            )
            existing_score = (
                1 if existing.opening_hours else 0,
                existing.confidence,
            )
            if candidate_score > existing_score:
                best_validation_by_name[key] = validation

        budget_multiplier = BUDGET_COST_MULTIPLIER.get(request.budget_level, 1.0)
        pace_multiplier = PACE_DURATION_MULTIPLIER.get(request.pace, 1.0)
        auto_filled_fields = 0

        for day in itinerary.days:
            if day.places:
                clock_minutes = self._parse_clock(day.places[0].start_time)
            else:
                clock_minutes = None

            if clock_minutes is None:
                clock_minutes = DEFAULT_DAY_START_MINUTES

            for place in day.places:
                category_key = self._categorize(place.category)

                if place.duration_hours is None:
                    base_duration = CATEGORY_DURATION_HOURS.get(
                        category_key,
                        CATEGORY_DURATION_HOURS["default"],
                    )
                    place.duration_hours = round(
                        min(12.0, max(0.5, base_duration * pace_multiplier)),
                        1,
                    )
                    auto_filled_fields += 1

                if place.estimated_cost_usd is None:
                    base_cost = CATEGORY_COST_USD.get(
                        category_key,
                        CATEGORY_COST_USD["default"],
                    )
                    place.estimated_cost_usd = round(
                        max(0.0, base_cost * budget_multiplier),
                        2,
                    )
                    auto_filled_fields += 1

                if not place.opening_hours:
                    validation = best_validation_by_name.get(place.name.strip().lower())
                    if validation and validation.opening_hours:
                        place.opening_hours = validation.opening_hours
                    else:
                        place.opening_hours = CATEGORY_OPENING_HOURS.get(
                            category_key,
                            CATEGORY_OPENING_HOURS["default"],
                        )
                    auto_filled_fields += 1

                parsed_time = self._parse_clock(place.start_time)
                if parsed_time is None:
                    place.start_time = self._format_clock(clock_minutes)
                    parsed_time = clock_minutes
                    auto_filled_fields += 1
                else:
                    # Normalize planner time string for consistent rendering.
                    place.start_time = self._format_clock(parsed_time)

                duration_hours = place.duration_hours or CATEGORY_DURATION_HOURS["default"]
                stay_minutes = int(round(duration_hours * 60))
                clock_minutes = parsed_time + stay_minutes + DEFAULT_TRANSFER_MINUTES

        if itinerary.total_estimated_cost_usd is None:
            total_cost = sum(
                (place.estimated_cost_usd or 0.0)
                for day in itinerary.days
                for place in day.places
            )
            if total_cost > 0.0:
                itinerary.total_estimated_cost_usd = round(total_cost, 2)
                auto_filled_fields += 1

        if auto_filled_fields == 0:
            return []

        return [
            (
                "Planner omitted some fields. Auto-filled schedule, duration, cost, "
                "and opening-hours values for complete output."
            )
        ]

    @staticmethod
    def _categorize(raw_category: str) -> str:
        normalized = raw_category.strip().lower()

        keyword_map = {
            "museum": "museum",
            "gallery": "museum",
            "beach": "beach",
            "park": "park",
            "garden": "park",
            "market": "market",
            "bazaar": "market",
            "shopping": "shopping",
            "mall": "shopping",
            "temple": "temple",
            "mosque": "mosque",
            "church": "church",
            "cathedral": "church",
            "fort": "fort",
            "palace": "fort",
            "station": "station",
            "neighborhood": "neighborhood",
            "district": "neighborhood",
            "food": "food",
            "restaurant": "restaurant",
            "cafe": "cafe",
            "landmark": "landmark",
            "monument": "landmark",
        }

        for keyword, category in keyword_map.items():
            if keyword in normalized:
                return category

        return "default"

    @staticmethod
    def _parse_clock(value: str | None) -> int | None:
        if value is None:
            return None

        text = value.strip().lower()
        if not text:
            return None

        twenty_four_hour_match = re.match(r"^([01]?\d|2[0-3]):([0-5]\d)$", text)
        if twenty_four_hour_match:
            hour = int(twenty_four_hour_match.group(1))
            minute = int(twenty_four_hour_match.group(2))
            return (hour * 60) + minute

        am_pm_match = re.match(r"^(\d{1,2})(?::([0-5]\d))?\s*([ap]m)$", text)
        if am_pm_match:
            hour = int(am_pm_match.group(1))
            minute = int(am_pm_match.group(2) or "0")
            suffix = am_pm_match.group(3)
            if hour < 1 or hour > 12:
                return None
            if suffix == "pm" and hour != 12:
                hour += 12
            if suffix == "am" and hour == 12:
                hour = 0
            return (hour * 60) + minute

        return None

    @staticmethod
    def _format_clock(total_minutes: int) -> str:
        normalized = total_minutes % (24 * 60)
        hours = normalized // 60
        minutes = normalized % 60
        return f"{hours:02d}:{minutes:02d}"

    @staticmethod
    def _stringify_message(message: Any) -> str:
        source = (
            getattr(message, "source", None)
            or getattr(message, "name", None)
            or getattr(message, "sender", None)
            or "agent"
        )
        content = getattr(message, "content", "")
        thought = getattr(message, "thought", None)
        content_text = HolidayTeam._normalize_message_content(content)
        if thought:
            content_text = f"{content_text}\n[thought] {thought}" if content_text else f"[thought] {thought}"
        return f"[{source}] {content_text}"

    @staticmethod
    def _normalize_message_content(content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, dict):
            return json.dumps(content, ensure_ascii=True)
        if isinstance(content, list):
            parts = [HolidayTeam._normalize_message_content(part) for part in content]
            return "\n".join(part for part in parts if part)

        for attribute in ("text", "content"):
            value = getattr(content, attribute, None)
            if isinstance(value, str):
                return value

        return str(content)


async def _close_model_client(model_client: Any) -> None:
    """Close model clients across SDK versions without raising cleanup errors."""

    for method_name in ("aclose", "close"):
        method = getattr(model_client, method_name, None)
        if method is None:
            continue
        try:
            outcome = method()
            if inspect.isawaitable(outcome):
                await outcome
        except Exception:
            pass
        break
