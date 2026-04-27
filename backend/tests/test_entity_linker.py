from unittest.mock import MagicMock, patch

import pytest
import requests

from backend.entity_linker import fetch_properties, is_food_entity, link_ingredient, search_candidates
from backend.models import WikidataEntity


# --- helpers ---

def _mock_response(json_data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.headers = {}
    resp.raise_for_status = MagicMock()
    return resp


def _session(*responses):
    s = MagicMock(spec=requests.Session)
    s.get.side_effect = list(responses)
    return s


# --- fixtures ---

SEARCH_HIT = {"id": "Q192628", "label": "chicken thigh", "description": "cut of chicken"}
SEARCH_RESPONSE = {"search": [SEARCH_HIT, {"id": "Q9345", "label": "chicken", "description": "bird"}]}
ASK_TRUE = {"boolean": True}
ASK_FALSE = {"boolean": False}

PROPS_RESPONSE = {
    "results": {
        "bindings": [
            {
                "foodCategoryLabel": {"value": "poultry"},
                "originCountryLabel": {"value": "United States"},
            }
        ]
    }
}

DIETARY_RESPONSE = {
    "results": {
        "bindings": [
            {"foodCategoryLabel": {"value": "legume"}, "dietaryFlag": {"value": "vegan"}},
            {"foodCategoryLabel": {"value": "legume"}, "dietaryFlag": {"value": "vegetarian"}},
        ]
    }
}

EMPTY_BINDINGS = {"results": {"bindings": []}}


# --- search_candidates ---

def test_search_candidates_returns_list():
    s = _session(_mock_response(SEARCH_RESPONSE))
    result = search_candidates("chicken thigh", s)
    assert isinstance(result, list)
    assert len(result) == 2


def test_search_candidates_contains_qids():
    s = _session(_mock_response(SEARCH_RESPONSE))
    result = search_candidates("chicken thigh", s)
    assert result[0]["id"] == "Q192628"


def test_search_candidates_sends_user_agent():
    s = _session(_mock_response(SEARCH_RESPONSE))
    search_candidates("chicken thigh", s)
    headers = s.get.call_args.kwargs.get("headers", {})
    assert "User-Agent" in headers


def test_search_candidates_returns_empty_for_no_matches():
    s = _session(_mock_response({"search": []}))
    assert search_candidates("xyzzy", s) == []


def test_search_candidates_includes_ingredient_in_request():
    s = _session(_mock_response(SEARCH_RESPONSE))
    search_candidates("tahini", s)
    params = s.get.call_args.kwargs.get("params", {})
    assert params.get("search") == "tahini"


# --- is_food_entity ---

def test_is_food_entity_true_for_food():
    s = _session(_mock_response(ASK_TRUE))
    assert is_food_entity("Q192628", s) is True


def test_is_food_entity_false_for_non_food():
    s = _session(_mock_response(ASK_FALSE))
    assert is_food_entity("Q999999", s) is False


def test_is_food_entity_sends_user_agent():
    s = _session(_mock_response(ASK_TRUE))
    is_food_entity("Q192628", s)
    headers = s.get.call_args.kwargs.get("headers", {})
    assert "User-Agent" in headers


def test_is_food_entity_sends_sparql_query_containing_qid():
    s = _session(_mock_response(ASK_TRUE))
    is_food_entity("Q192628", s)
    params = s.get.call_args.kwargs.get("params", {})
    assert "Q192628" in params.get("query", "")


# --- fetch_properties ---

def test_fetch_properties_returns_wikidata_entity():
    s = _session(_mock_response(PROPS_RESPONSE))
    entity = fetch_properties("Q192628", "chicken thigh", s)
    assert isinstance(entity, WikidataEntity)


def test_fetch_properties_sets_qid_and_label():
    s = _session(_mock_response(PROPS_RESPONSE))
    entity = fetch_properties("Q192628", "chicken thigh", s)
    assert entity.qid == "Q192628"
    assert entity.label == "chicken thigh"


def test_fetch_properties_sets_uri():
    s = _session(_mock_response(PROPS_RESPONSE))
    entity = fetch_properties("Q192628", "chicken thigh", s)
    assert entity.uri == "http://www.wikidata.org/entity/Q192628"


def test_fetch_properties_extracts_food_category():
    s = _session(_mock_response(PROPS_RESPONSE))
    entity = fetch_properties("Q192628", "chicken thigh", s)
    assert entity.food_category == "poultry"


def test_fetch_properties_extracts_origin_country():
    s = _session(_mock_response(PROPS_RESPONSE))
    entity = fetch_properties("Q192628", "chicken thigh", s)
    assert entity.origin_country == "United States"


def test_fetch_properties_extracts_dietary_flags():
    s = _session(_mock_response(DIETARY_RESPONSE))
    entity = fetch_properties("Q23768", "chickpea", s)
    assert "vegan" in entity.dietary_flags
    assert "vegetarian" in entity.dietary_flags


def test_fetch_properties_deduplicates_dietary_flags():
    duped = {
        "results": {
            "bindings": [
                {"dietaryFlag": {"value": "vegan"}},
                {"dietaryFlag": {"value": "vegan"}},
            ]
        }
    }
    s = _session(_mock_response(duped))
    entity = fetch_properties("Q23768", "chickpea", s)
    assert entity.dietary_flags.count("vegan") == 1


def test_fetch_properties_handles_empty_bindings():
    s = _session(_mock_response(EMPTY_BINDINGS))
    entity = fetch_properties("Q99", "unknown", s)
    assert entity.food_category is None
    assert entity.origin_country is None
    assert entity.dietary_flags == []


def test_fetch_properties_sends_user_agent():
    s = _session(_mock_response(PROPS_RESPONSE))
    fetch_properties("Q192628", "chicken thigh", s)
    headers = s.get.call_args.kwargs.get("headers", {})
    assert "User-Agent" in headers


# --- retry logic ---

def test_retries_on_429_then_succeeds():
    rate_limited = _mock_response({}, status_code=429)
    rate_limited.headers = {"Retry-After": "0"}
    ok = _mock_response(SEARCH_RESPONSE)

    s = MagicMock(spec=requests.Session)
    s.get.side_effect = [rate_limited, ok]

    with patch("backend.entity_linker.time.sleep"):
        result = search_candidates("chicken thigh", s)

    assert s.get.call_count == 2
    assert len(result) == 2


def test_retries_on_503_then_succeeds():
    unavailable = _mock_response({}, status_code=503)
    ok = _mock_response(SEARCH_RESPONSE)

    s = MagicMock(spec=requests.Session)
    s.get.side_effect = [unavailable, ok]

    with patch("backend.entity_linker.time.sleep"):
        result = search_candidates("chicken thigh", s)

    assert s.get.call_count == 2
    assert len(result) == 2


def test_raises_after_max_retries_exceeded():
    always_429 = _mock_response({}, status_code=429)
    always_429.headers = {}

    s = MagicMock(spec=requests.Session)
    s.get.return_value = always_429

    with patch("backend.entity_linker.time.sleep"):
        with pytest.raises(requests.HTTPError):
            search_candidates("chicken thigh", s)


def test_exponential_backoff_increases_delay():
    r429 = _mock_response({}, status_code=429)
    r429.headers = {}
    ok = _mock_response(SEARCH_RESPONSE)

    s = MagicMock(spec=requests.Session)
    s.get.side_effect = [r429, r429, ok]

    sleep_calls = []
    with patch("backend.entity_linker.time.sleep", side_effect=sleep_calls.append):
        search_candidates("chicken thigh", s)

    assert len(sleep_calls) == 2
    assert sleep_calls[1] > sleep_calls[0]


# --- link_ingredient ---

def test_link_ingredient_returns_entity_for_known_food():
    s = _session(
        _mock_response(SEARCH_RESPONSE),
        _mock_response(ASK_TRUE),
        _mock_response(PROPS_RESPONSE),
    )
    entity = link_ingredient("chicken thigh", s)
    assert isinstance(entity, WikidataEntity)
    assert entity.qid == "Q192628"


def test_link_ingredient_returns_none_when_no_candidates():
    s = _session(_mock_response({"search": []}))
    assert link_ingredient("xyzzy", s) is None


def test_link_ingredient_skips_non_food_candidates():
    two_candidates = {
        "search": [
            {"id": "Q999", "label": "not food"},
            SEARCH_HIT,
        ]
    }
    s = _session(
        _mock_response(two_candidates),
        _mock_response(ASK_FALSE),   # Q999 fails food check
        _mock_response(ASK_TRUE),    # Q192628 passes
        _mock_response(PROPS_RESPONSE),
    )
    entity = link_ingredient("chicken thigh", s)
    assert entity is not None
    assert entity.qid == "Q192628"


def test_link_ingredient_returns_none_when_no_candidate_is_food():
    s = _session(
        _mock_response(SEARCH_RESPONSE),
        _mock_response(ASK_FALSE),
        _mock_response(ASK_FALSE),
    )
    assert link_ingredient("chicken thigh", s) is None
