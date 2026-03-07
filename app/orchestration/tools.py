from typing import Any

from app.support.verifier import TravelDataVerifier


class ResearchTools:
    """Tool wrappers exposed to the Researcher Agent."""

    def __init__(self, verifier: TravelDataVerifier) -> None:
        self._verifier = verifier

    async def verify_place(
        self,
        place_name: str,
        city: str,
        country: str,
    ) -> dict[str, Any]:
        """Verify whether a place exists and return canonical metadata."""

        result = await self._verifier.verify_place(
            place_name=place_name,
            city=city,
            country=country,
        )
        return result.model_dump()

    async def estimate_route(
        self,
        origin: str,
        destination: str,
        city: str,
        country: str,
        mode: str = "driving",
    ) -> dict[str, Any]:
        """Estimate travel time between two places in the same city."""

        result = await self._verifier.estimate_route(
            origin=origin,
            destination=destination,
            city=city,
            country=country,
            mode=mode,
        )
        return result.model_dump()
