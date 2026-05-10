from unittest.mock import MagicMock, patch

import pytest
import requests

from backend.entity_linker import (
    fetch_properties,
    filter_food_entities,
    is_food_entity,
    link_ingredient,
    search_candidates,
)
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

PROPS_RESPONSE_P279_FALLBACK = {
    "results": {
        "bindings": [
            {
                "subclassCategoryLabel": {"value": "poultry"},
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

# Batch SELECT response: Q192628 is a food entity
FILTER_Q192628 = {
    "results": {
        "bindings": [
            {"entity": {"value": "http://www.wikidata.org/entity/Q192628"}}
        ]
    }
}
FILTER_EMPTY = {"results": {"bindings": []}}


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


def test_fetch_properties_uses_p279_when_p31_absent():
    s = _session(_mock_response(PROPS_RESPONSE_P279_FALLBACK))
    entity = fetch_properties("Q192628", "chicken thigh", s)
    assert entity.food_category == "poultry"


def test_fetch_properties_prefers_p31_over_p279():
    both = {
        "results": {
            "bindings": [
                {
                    "foodCategoryLabel": {"value": "meat"},
                    "subclassCategoryLabel": {"value": "animal product"},
                }
            ]
        }
    }
    s = _session(_mock_response(both))
    entity = fetch_properties("Q192628", "chicken thigh", s)
    assert entity.food_category == "meat"


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

    # sleep_calls[0] is the unconditional rate-limit sleep before the retry loop;
    # sleep_calls[1] and [2] are the exponential backoff sleeps after each 429.
    assert len(sleep_calls) == 3
    assert sleep_calls[2] > sleep_calls[1]


# --- filter_food_entities ---

def test_filter_food_entities_returns_matching_qids():
    s = _session(_mock_response(FILTER_Q192628))
    result = filter_food_entities(["Q192628", "Q999"], s)
    assert result == {"Q192628"}


def test_filter_food_entities_returns_empty_for_no_food():
    s = _session(_mock_response(FILTER_EMPTY))
    result = filter_food_entities(["Q999"], s)
    assert result == set()


def test_filter_food_entities_returns_empty_for_no_qids():
    s = MagicMock(spec=requests.Session)
    result = filter_food_entities([], s)
    assert result == set()
    s.get.assert_not_called()


def test_filter_food_entities_sends_user_agent():
    s = _session(_mock_response(FILTER_Q192628))
    filter_food_entities(["Q192628"], s)
    headers = s.get.call_args.kwargs.get("headers", {})
    assert "User-Agent" in headers


# --- link_ingredient ---

def test_link_ingredient_returns_entity_for_known_food():
    # search → batch filter (Q192628 is food) → fetch_properties
    s = _session(
        _mock_response(SEARCH_RESPONSE),
        _mock_response(FILTER_Q192628),
        _mock_response(PROPS_RESPONSE),
    )
    entity = link_ingredient("chicken thigh", s)
    assert isinstance(entity, WikidataEntity)
    assert entity.qid == "Q192628"


def test_link_ingredient_returns_none_when_no_candidates():
    # Both search attempts return empty lists — filter is never called
    s = _session(_mock_response({"search": []}), _mock_response({"search": []}))
    assert link_ingredient("xyzzy", s) is None


def test_link_ingredient_skips_non_food_candidates():
    two_candidates = {
        "search": [
            {"id": "Q999", "label": "not food"},
            SEARCH_HIT,
        ]
    }
    # Batch filter returns only Q192628 — Q999 is skipped
    s = _session(
        _mock_response(two_candidates),
        _mock_response(FILTER_Q192628),
        _mock_response(PROPS_RESPONSE),
    )
    entity = link_ingredient("chicken thigh", s)
    assert entity is not None
    assert entity.qid == "Q192628"


def test_link_ingredient_returns_none_when_no_candidate_is_food():
    # First search: no food entities; second (fallback) search: empty
    s = _session(
        _mock_response(SEARCH_RESPONSE),
        _mock_response(FILTER_EMPTY),        # no candidates are food
        _mock_response({"search": []}),      # fallback search empty
    )
    assert link_ingredient("chicken thigh", s) is None


def test_link_ingredient_sorts_candidates_by_sitelinks():
    # High-sitelinks entity is second in API response but picked first from the food set
    low_sitelinks = {"id": "Q999", "label": "not food", "sitelinks": 5}
    high_sitelinks = {**SEARCH_HIT, "sitelinks": 100}
    two_candidates = {"search": [low_sitelinks, high_sitelinks]}
    # Batch filter says both are food — but sitelinks order means Q192628 is returned
    filter_both = {
        "results": {
            "bindings": [
                {"entity": {"value": "http://www.wikidata.org/entity/Q192628"}},
                {"entity": {"value": "http://www.wikidata.org/entity/Q999"}},
            ]
        }
    }
    s = _session(
        _mock_response(two_candidates),
        _mock_response(filter_both),
        _mock_response(PROPS_RESPONSE),
    )
    entity = link_ingredient("chicken thigh", s)
    assert entity is not None
    assert entity.qid == "Q192628"


def test_retries_on_read_timeout_then_succeeds():
    s = MagicMock(spec=requests.Session)
    s.get.side_effect = [requests.exceptions.ReadTimeout(), _mock_response(SEARCH_RESPONSE)]
    with patch("backend.entity_linker.time.sleep"):
        result = search_candidates("chicken thigh", s)
    assert s.get.call_count == 2
    assert len(result) == 2


def test_raises_after_max_read_timeout_retries():
    s = MagicMock(spec=requests.Session)
    s.get.side_effect = requests.exceptions.ReadTimeout()
    with patch("backend.entity_linker.time.sleep"):
        with pytest.raises(requests.exceptions.ReadTimeout):
            search_candidates("chicken thigh", s)
