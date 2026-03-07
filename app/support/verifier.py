import difflib
from typing import Any

import httpx

from app.config import Settings
from app.schemas import PlaceValidation, RouteValidation

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_API_URL = "https://overpass-api.de/api/interpreter"
OSRM_ROUTE_BASE_URL = "https://router.project-osrm.org/route/v1"


class TravelDataVerifier:
    """Verify places and estimate routes using free public data services."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.request_timeout_seconds),
            headers={"User-Agent": settings.user_agent},
        )
        self._place_cache: dict[tuple[str, str, str, bool], PlaceValidation] = {}

    async def close(self) -> None:
        await self._client.aclose()

    async def verify_place(
        self,
        place_name: str,
        city: str,
        country: str,
        include_opening_hours: bool = True,
    ) -> PlaceValidation:
        cache_key = (
            place_name.strip().lower(),
            city.strip().lower(),
            country.strip().lower(),
            include_opening_hours,
        )
        if cache_key in self._place_cache:
            return self._place_cache[cache_key]

        query = f"{place_name}, {city}, {country}"
        params = {"q": query, "format": "jsonv2", "limit": 5}

        try:
            response = await self._client.get(NOMINATIM_SEARCH_URL, params=params)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            validation = PlaceValidation(
                place_name=place_name,
                requested_city=city,
                requested_country=country,
                exists=False,
                notes=f"Nominatim lookup failed: {exc.__class__.__name__}",
            )
            self._place_cache[cache_key] = validation
            return validation

        if not payload:
            validation = PlaceValidation(
                place_name=place_name,
                requested_city=city,
                requested_country=country,
                exists=False,
                notes="No location match found in Nominatim.",
            )
            self._place_cache[cache_key] = validation
            return validation

        top_result = payload[0]
        lat = _safe_float(top_result.get("lat"))
        lon = _safe_float(top_result.get("lon"))

        canonical_name = top_result.get("name")
        if not canonical_name and top_result.get("display_name"):
            canonical_name = str(top_result["display_name"]).split(",")[0].strip()

        confidence = _name_similarity(place_name, canonical_name or "")
        opening_hours = None
        if include_opening_hours and lat is not None and lon is not None:
            opening_hours = await self._fetch_opening_hours(place_name, lat, lon)

        validation = PlaceValidation(
            place_name=place_name,
            requested_city=city,
            requested_country=country,
            exists=True,
            canonical_name=canonical_name,
            display_name=top_result.get("display_name"),
            latitude=lat,
            longitude=lon,
            opening_hours=opening_hours,
            confidence=confidence,
            notes="Opening hours unavailable in OSM data." if not opening_hours else None,
        )
        self._place_cache[cache_key] = validation
        return validation

    async def estimate_route(
        self,
        origin: str,
        destination: str,
        city: str,
        country: str,
        mode: str = "driving",
    ) -> RouteValidation:
        normalized_mode = mode if mode in {"driving", "walking", "cycling"} else "driving"

        origin_info = await self.verify_place(
            place_name=origin,
            city=city,
            country=country,
            include_opening_hours=False,
        )
        destination_info = await self.verify_place(
            place_name=destination,
            city=city,
            country=country,
            include_opening_hours=False,
        )

        if not origin_info.exists or not destination_info.exists:
            return RouteValidation(
                origin=origin,
                destination=destination,
                mode=normalized_mode,
                notes="Route skipped because one or more places could not be geocoded.",
            )

        if origin_info.latitude is None or origin_info.longitude is None:
            return RouteValidation(
                origin=origin,
                destination=destination,
                mode=normalized_mode,
                notes="Origin geocode is incomplete.",
            )

        if destination_info.latitude is None or destination_info.longitude is None:
            return RouteValidation(
                origin=origin,
                destination=destination,
                mode=normalized_mode,
                notes="Destination geocode is incomplete.",
            )

        coordinates = (
            f"{origin_info.longitude},{origin_info.latitude};"
            f"{destination_info.longitude},{destination_info.latitude}"
        )
        route_url = f"{OSRM_ROUTE_BASE_URL}/{normalized_mode}/{coordinates}"

        try:
            response = await self._client.get(
                route_url,
                params={"overview": "false", "steps": "false"},
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            return RouteValidation(
                origin=origin,
                destination=destination,
                mode=normalized_mode,
                notes=f"OSRM route lookup failed: {exc.__class__.__name__}",
            )

        routes = payload.get("routes", [])
        if not routes:
            return RouteValidation(
                origin=origin,
                destination=destination,
                mode=normalized_mode,
                notes="No route found by OSRM.",
            )

        best_route = routes[0]
        duration_minutes = int(round(float(best_route.get("duration", 0.0)) / 60.0))
        distance_km = round(float(best_route.get("distance", 0.0)) / 1000.0, 1)

        return RouteValidation(
            origin=origin,
            destination=destination,
            mode=normalized_mode,
            duration_minutes=duration_minutes,
            distance_km=distance_km,
        )

    async def _fetch_opening_hours(
        self,
        place_name: str,
        latitude: float,
        longitude: float,
    ) -> str | None:
        query = (
            "[out:json][timeout:20];"
            "("
            f"node(around:300,{latitude},{longitude})[\"name\"];"
            f"way(around:300,{latitude},{longitude})[\"name\"];"
            f"relation(around:300,{latitude},{longitude})[\"name\"];"
            ");"
            "out tags;"
        )

        try:
            response = await self._client.post(OVERPASS_API_URL, data={"data": query})
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return None

        best_match_hours: str | None = None
        best_match_score = 0.0

        for element in payload.get("elements", []):
            tags = element.get("tags", {})
            candidate_name = tags.get("name")
            if not candidate_name:
                continue
            score = _name_similarity(place_name, candidate_name)
            if score > best_match_score:
                best_match_score = score
                best_match_hours = tags.get("opening_hours")

        if best_match_score < 0.55:
            return None
        return best_match_hours


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _name_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    ratio = difflib.SequenceMatcher(None, left.lower().strip(), right.lower().strip()).ratio()
    return round(ratio, 2)
