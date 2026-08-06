from unittest.mock import MagicMock, patch

import dashboard.llm_client as llm_client_module
from dashboard.llm_client import generate_reply


def test_generate_reply_calls_bedrock_converse_with_system_and_user_message(monkeypatch):
    monkeypatch.setattr(llm_client_module, "_client", None)
    fake_response = {
        "output": {"message": {"content": [{"text": "안녕하세요, 좋은 하루 보내세요!"}]}}
    }
    mock_client = MagicMock()
    mock_client.converse.return_value = fake_response

    with patch("dashboard.llm_client.boto3.client", return_value=mock_client) as mock_boto3_client:
        reply = generate_reply("당신은 친절한 재활 코치입니다.", "오늘 스쿼트 몇 개 해야 하나요?")

    assert reply == "안녕하세요, 좋은 하루 보내세요!"
    mock_boto3_client.assert_called_once_with("bedrock-runtime", region_name="us-east-1")
    call_kwargs = mock_client.converse.call_args.kwargs
    assert call_kwargs["modelId"] == "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    assert call_kwargs["system"] == [{"text": "당신은 친절한 재활 코치입니다."}]
    assert call_kwargs["messages"] == [
        {"role": "user", "content": [{"text": "오늘 스쿼트 몇 개 해야 하나요?"}]},
    ]


def test_generate_reply_reuses_client_across_calls(monkeypatch):
    monkeypatch.setattr(llm_client_module, "_client", None)
    fake_response = {"output": {"message": {"content": [{"text": "응답"}]}}}
    mock_client = MagicMock()
    mock_client.converse.return_value = fake_response

    with patch("dashboard.llm_client.boto3.client", return_value=mock_client) as mock_boto3_client:
        generate_reply("system", "message one")
        generate_reply("system", "message two")

    mock_boto3_client.assert_called_once()
    assert mock_client.converse.call_count == 2
