from unittest.mock import MagicMock

import pytest

from backend.normaliser import normalise_ingredient


def _mock_client(response_text: str) -> MagicMock:
    client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = response_text
    client.chat.completions.create.return_value = mock_resp
    return client


def test_normalise_strips_quantity_and_unit():
    client = _mock_client("chicken thigh")
    assert normalise_ingredient("400g Chicken thighs", client) == "chicken thigh"


def test_normalise_plain_name():
    client = _mock_client("tahini")
    assert normalise_ingredient("Tahini", client) == "tahini"


def test_normalise_strips_leading_trailing_whitespace():
    client = _mock_client("  butternut squash  ")
    result = normalise_ingredient("1 Butternut squash", client)
    assert result == "butternut squash"


def test_normalise_sends_raw_string_to_api():
    client = _mock_client("chicken thigh")
    normalise_ingredient("400g Chicken thighs", client)
    call_kwargs = client.chat.completions.create.call_args.kwargs
    messages = call_kwargs["messages"]
    user_msg = next(m for m in messages if m["role"] == "user")
    assert "400g Chicken thighs" in user_msg["content"]


def test_normalise_includes_system_prompt():
    client = _mock_client("chicken thigh")
    normalise_ingredient("400g Chicken thighs", client)
    call_kwargs = client.chat.completions.create.call_args.kwargs
    messages = call_kwargs["messages"]
    system_msg = next(m for m in messages if m["role"] == "system")
    assert len(system_msg["content"]) > 0


# --- normalise_all ---

from backend.normaliser import normalise_all


def test_normalise_all_maps_list():
    client = MagicMock()
    responses = ["chicken thigh", "butternut squash", "tahini"]
    mock_resps = []
    for text in responses:
        m = MagicMock()
        m.choices[0].message.content = text
        mock_resps.append(m)
    client.chat.completions.create.side_effect = mock_resps

    result = normalise_all(["400g Chicken thighs", "1 Butternut squash", "Tahini"], client)
    assert result == ["chicken thigh", "butternut squash", "tahini"]


def test_normalise_all_empty_list():
    client = MagicMock()
    result = normalise_all([], client)
    assert result == []
    client.chat.completions.create.assert_not_called()


def test_normalise_all_preserves_order():
    client = MagicMock()
    responses = ["egg", "olive oil"]
    mock_resps = []
    for text in responses:
        m = MagicMock()
        m.choices[0].message.content = text
        mock_resps.append(m)
    client.chat.completions.create.side_effect = mock_resps

    result = normalise_all(["2 Eggs", "2 tbsp olive oil"], client)
    assert result[0] == "egg"
    assert result[1] == "olive oil"


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
