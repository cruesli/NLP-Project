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
