from moss_slack_discord.adapters import extract_discord_question, extract_slack_question


def test_extracts_slack_question_from_app_mention() -> None:
    assert (
        extract_slack_question("<@U123> What is our refund policy?")
        == "What is our refund policy?"
    )


def test_extracts_discord_question_from_prefix() -> None:
    assert (
        extract_discord_question("!ask Where is the onboarding guide?", 42, "!ask")
        == "Where is the onboarding guide?"
    )


def test_extracts_discord_question_from_mention() -> None:
    assert (
        extract_discord_question("<@!42> How do I request access?", 42, "!ask")
        == "How do I request access?"
    )


def test_ignores_unrelated_discord_message() -> None:
    assert extract_discord_question("hello everyone", 42, "!ask") is None
