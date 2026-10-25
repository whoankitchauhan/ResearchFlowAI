import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage

from agents import CRITIC_MAX_TOKENS, WRITER_MAX_TOKENS, critic_chain, writer_chain


class AgentChainTests(unittest.TestCase):
    def test_writer_chain_creates_provider_only_when_invoked(self) -> None:
        with patch("agents._get_llm") as get_llm:
            get_llm.return_value.bind.return_value.invoke.return_value = AIMessage(
                content="Research report"
            )

            report = writer_chain.invoke(
                {"topic": "Test topic", "research": "Verified source material"}
            )

        self.assertEqual(report, "Research report")
        get_llm.assert_called_once_with()
        get_llm.return_value.bind.assert_called_once_with(
            max_tokens=WRITER_MAX_TOKENS
        )
        get_llm.return_value.bind.return_value.invoke.assert_called_once()

    def test_critic_chain_uses_a_small_output_budget(self) -> None:
        with patch("agents._get_llm") as get_llm:
            get_llm.return_value.bind.return_value.invoke.return_value = AIMessage(
                content="Concise critical review"
            )

            feedback = critic_chain.invoke(
                {"report": "Research report", "research": "Evidence excerpts"}
            )

        self.assertEqual(feedback, "Concise critical review")
        get_llm.return_value.bind.assert_called_once_with(
            max_tokens=CRITIC_MAX_TOKENS
        )
        get_llm.return_value.bind.return_value.invoke.assert_called_once()


if __name__ == "__main__":
    unittest.main()
