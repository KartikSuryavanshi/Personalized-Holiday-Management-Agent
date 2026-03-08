from app.config import Settings
from app.orchestration.workflow import HolidayTeam
from app.schemas import DayItinerary, ItineraryPlan, PlaceItem, PlaceValidation, TripRequest


def test_enrich_itinerary_fills_missing_place_fields() -> None:
    team = HolidayTeam(Settings())

    itinerary = ItineraryPlan(
        destination_city="Mumbai",
        destination_country="India",
        summary="Two-day city highlights.",
        days=[
            DayItinerary(
                day=1,
                title="Day 1",
                focus="South Mumbai",
                places=[
                    PlaceItem(name="Gateway of India", area="Colaba", category="Landmark"),
                    PlaceItem(name="Marine Drive", area="South Mumbai", category="Beach"),
                ],
            )
        ],
    )

    request = TripRequest(prompt="Plan a realistic 1-day Mumbai trip.", days=1)
    validations = [
        PlaceValidation(
            place_name="Gateway of India",
            requested_city="Mumbai",
            requested_country="India",
            exists=True,
            confidence=0.95,
            opening_hours="10:00-18:00",
        ),
        PlaceValidation(
            place_name="Marine Drive",
            requested_city="Mumbai",
            requested_country="India",
            exists=True,
            confidence=0.95,
            opening_hours=None,
        ),
    ]

    warnings = team._enrich_itinerary(
        itinerary=itinerary,
        request=request,
        place_validations=validations,
    )

    first_place = itinerary.days[0].places[0]
    second_place = itinerary.days[0].places[1]

    assert warnings
    assert first_place.start_time == "09:00"
    assert first_place.duration_hours is not None
    assert first_place.estimated_cost_usd is not None
    assert first_place.opening_hours == "10:00-18:00"

    assert second_place.start_time is not None
    assert second_place.duration_hours is not None
    assert second_place.estimated_cost_usd is not None
    assert second_place.opening_hours is not None

    assert itinerary.total_estimated_cost_usd is not None
