import json
from unittest.mock import MagicMock

import pytest

from backend.normaliser import normalise_ingredient


def _mock_client(response_text: str) -> MagicMock:
    client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = response_text
    client.chat.completions.create.return_value = mock_resp
    return client


def _json_resp(*items) -> str:
    """Build a JSON response string from (name, quantity_g) tuples."""
    return json.dumps([{"name": n, "quantity_g": q} for n, q in items])


def test_normalise_strips_quantity_and_unit():
    client = _mock_client(_json_resp(("chicken thigh", 400.0)))
    assert normalise_ingredient("400g Chicken thighs", client) == "chicken thigh"


def test_normalise_plain_name():
    client = _mock_client(_json_resp(("tahini", None)))
    assert normalise_ingredient("Tahini", client) == "tahini"


def test_normalise_strips_leading_trailing_whitespace():
    client = _mock_client(_json_resp(("butternut squash", 700.0)))
    result = normalise_ingredient("1 Butternut squash", client)
    assert result == "butternut squash"


def test_normalise_sends_raw_string_to_api():
    client = _mock_client(_json_resp(("chicken thigh", 400.0)))
    normalise_ingredient("400g Chicken thighs", client)
    call_kwargs = client.chat.completions.create.call_args.kwargs
    messages = call_kwargs["messages"]
    user_msg = next(m for m in messages if m["role"] == "user")
    assert "400g Chicken thighs" in user_msg["content"]


def test_normalise_includes_system_prompt():
    client = _mock_client(_json_resp(("chicken thigh", 400.0)))
    normalise_ingredient("400g Chicken thighs", client)
    call_kwargs = client.chat.completions.create.call_args.kwargs
    messages = call_kwargs["messages"]
    system_msg = next(m for m in messages if m["role"] == "system")
    assert len(system_msg["content"]) > 0


# --- normalise_all ---

from backend.normaliser import normalise_all


def test_normalise_all_returns_dicts():
    client = _mock_client(_json_resp(("chicken thigh", 400.0)))
    result = normalise_all(["400g Chicken thighs"], client)
    assert isinstance(result[0], dict)
    assert "name" in result[0]
    assert "quantity_g" in result[0]


def test_normalise_all_maps_list():
    client = _mock_client(_json_resp(
        ("chicken thigh", 400.0),
        ("butternut squash", 700.0),
        ("tahini", None),
    ))
    result = normalise_all(["400g Chicken thighs", "1 Butternut squash", "Tahini"], client)
    assert result == [
        {"name": "chicken thigh", "quantity_g": 400.0},
        {"name": "butternut squash", "quantity_g": 700.0},
        {"name": "tahini", "quantity_g": None},
    ]


def test_normalise_all_quantity_g_in_grams():
    # 2 tbsp → 30g
    client = _mock_client(_json_resp(("olive oil", 30.0)))
    result = normalise_all(["2 tbsp olive oil"], client)
    assert result[0]["quantity_g"] == pytest.approx(30.0)


def test_normalise_all_returns_null_quantity_for_to_taste():
    client = _mock_client(_json_resp(("salt", None)))
    result = normalise_all(["salt to taste"], client)
    assert result[0]["quantity_g"] is None


def test_normalise_all_single_api_call():
    client = _mock_client(_json_resp(("chicken thigh", 400.0), ("butternut squash", 700.0)))
    normalise_all(["400g Chicken thighs", "1 Butternut squash"], client)
    client.chat.completions.create.assert_called_once()


def test_normalise_all_sends_all_ingredients_in_one_message():
    client = _mock_client(_json_resp(("chicken thigh", 400.0), ("butternut squash", 700.0)))
    normalise_all(["400g Chicken thighs", "1 Butternut squash"], client)
    call_kwargs = client.chat.completions.create.call_args.kwargs
    user_msg = next(m for m in call_kwargs["messages"] if m["role"] == "user")
    assert "400g Chicken thighs" in user_msg["content"]
    assert "1 Butternut squash" in user_msg["content"]


def test_normalise_all_empty_list():
    client = MagicMock()
    result = normalise_all([], client)
    assert result == []
    client.chat.completions.create.assert_not_called()


def test_normalise_all_preserves_order():
    client = _mock_client(_json_resp(("egg", None), ("olive oil", 30.0)))
    result = normalise_all(["2 Eggs", "2 tbsp olive oil"], client)
    assert result[0]["name"] == "egg"
    assert result[1]["name"] == "olive oil"


def test_normalise_all_strips_whitespace_from_name():
    client = _mock_client(_json_resp(("  butternut squash  ", 700.0)))
    result = normalise_all(["1 Butternut squash"], client)
    assert result[0]["name"] == "butternut squash"


# --- make_client ---

import openai

from backend.normaliser import make_client


def test_make_client_returns_openai_client(monkeypatch):
    monkeypatch.setenv("CAMPUSAI_API_KEY", "test-key")
    monkeypatch.setenv("CAMPUSAI_BASE_URL", "https://example.com/v1")
    client = make_client()
    assert isinstance(client, openai.OpenAI)


def test_make_client_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("CAMPUSAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="CAMPUSAI_API_KEY"):
        make_client()
