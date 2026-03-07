from app.orchestration.parsing import extract_final_itinerary_json, extract_json_object


def test_extract_json_object_from_fenced_block() -> None:
    text = """
    draft here
    ```json
    {"destination_city": "Tokyo", "days": []}
    ```
    """
    parsed = extract_json_object(text)
    assert parsed["destination_city"] == "Tokyo"


def test_extract_final_itinerary_json_prefers_marker() -> None:
    messages = [
        "[planner] maybe this {\"foo\": \"bar\"}",
        "[planner] FINAL_ITINERARY_JSON {\"destination_city\": \"Kyoto\", \"destination_country\": \"Japan\", \"summary\": \"ok\", \"assumptions\": [], \"total_estimated_cost_usd\": 1000, \"days\": []}",
    ]
    parsed = extract_final_itinerary_json(messages, "FINAL_ITINERARY_JSON")
    assert parsed["destination_city"] == "Kyoto"


def test_extract_json_object_accepts_python_dict_style() -> None:
    text = (
        "FINAL_ITINERARY_JSON {'destination_city': 'Tokyo', "
        "'destination_country': 'Japan', 'summary': 'ok', 'assumptions': [], "
        "'total_estimated_cost_usd': 1500, 'days': []}"
    )
    parsed = extract_json_object(text)
    assert parsed["destination_city"] == "Tokyo"
