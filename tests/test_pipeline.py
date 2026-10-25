import contextlib
import io
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
from groq import BadRequestError
import pipeline


class ResearchPipelineTests(unittest.TestCase):
    def test_existing_four_stage_workflow_and_optional_progress(self) -> None:
        search_agent = SimpleNamespace(
            invoke=lambda _input: {"messages": [SimpleNamespace(content="Search findings")]}
        )
        reader_agent = SimpleNamespace(
            invoke=lambda _input: {"messages": [SimpleNamespace(content="Detailed reading")]}
        )
        writer = SimpleNamespace(invoke=lambda _input: "Research report")
        critic = SimpleNamespace(invoke=lambda _input: "Critical review")
        progress = []

        with (
            patch.object(pipeline, "build_web_search_agent", return_value=search_agent),
            patch.object(pipeline, "build_web_reader_agent", return_value=reader_agent),
            patch.object(pipeline, "writer_chain", writer),
            patch.object(pipeline, "critic_chain", critic),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            result = pipeline.run_research_pipeline(
                "Test topic",
                progress_callback=lambda stage, value: progress.append((stage, value)),
            )

        self.assertEqual(
            result,
            {
                "search_results": "Search findings",
                "scraped_content": "Detailed reading",
                "report": "Research report",
                "feedback": "Critical review",
            },
        )
        self.assertEqual(
            progress,
            [
                ("search", 5),
                ("reading", 30),
                ("writing", 55),
                ("reviewing", 80),
                ("completed", 100),
            ],
        )

    def test_critic_retries_once_with_shorter_inputs_after_413(self) -> None:
        class RequestTooLargeError(Exception):
            status_code = 413

        search_agent = SimpleNamespace(
            invoke=Mock(return_value={
                "messages": [SimpleNamespace(content="search evidence " * 1000)]
            })
        )
        reader_agent = SimpleNamespace(
            invoke=Mock(return_value={
                "messages": [SimpleNamespace(content="reading evidence " * 1000)]
            })
        )
        writer = SimpleNamespace(invoke=Mock(return_value="report " * 2000))
        critic = SimpleNamespace(invoke=Mock(side_effect=[
            RequestTooLargeError("request exceeds token limit"),
            "Critical review",
        ]))

        with (
            patch.object(pipeline, "build_web_search_agent", return_value=search_agent),
            patch.object(pipeline, "build_web_reader_agent", return_value=reader_agent),
            patch.object(pipeline, "writer_chain", writer),
            patch.object(pipeline, "critic_chain", critic),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            result = pipeline.run_research_pipeline("Test topic")

        first_input, retry_input = [call.args[0] for call in critic.invoke.call_args_list]
        self.assertEqual(len(critic.invoke.call_args_list), 2)
        self.assertEqual(len(first_input["report"]), 14000)
        self.assertLess(len(retry_input["report"]), len(first_input["report"]))
        self.assertIn("middle omitted", retry_input["report"])
        self.assertLess(len(retry_input["research"]), len(first_input["research"]))
        self.assertEqual(result["feedback"], "Critical review")
        search_agent.invoke.assert_called_once()
        reader_agent.invoke.assert_called_once()
        writer.invoke.assert_called_once()

    def test_non_413_critic_errors_are_not_retried(self) -> None:
        search_agent = SimpleNamespace(
            invoke=lambda _input: {"messages": [SimpleNamespace(content="Search findings")]}
        )
        reader_agent = SimpleNamespace(
            invoke=lambda _input: {"messages": [SimpleNamespace(content="Detailed reading")]}
        )
        writer = SimpleNamespace(invoke=lambda _input: "Research report")
        critic = SimpleNamespace(invoke=Mock(side_effect=RuntimeError("provider unavailable")))

        with (
            patch.object(pipeline, "build_web_search_agent", return_value=search_agent),
            patch.object(pipeline, "build_web_reader_agent", return_value=reader_agent),
            patch.object(pipeline, "writer_chain", writer),
            patch.object(pipeline, "critic_chain", critic),
            contextlib.redirect_stdout(io.StringIO()),
            self.assertRaisesRegex(RuntimeError, "provider unavailable"),
        ):
            pipeline.run_research_pipeline("Test topic")

        critic.invoke.assert_called_once()

    def test_malformed_search_tool_call_falls_back_to_direct_tavily(self) -> None:
        search_error = BadRequestError(
            "Failed to parse tool call arguments as JSON",
            response=httpx.Response(
                400,
                request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
            ),
            body={
                "error": {
                    "code": "tool_use_failed",
                    "message": "Failed to parse tool call arguments as JSON",
                }
            },
        )
        search_agent = SimpleNamespace(invoke=Mock(side_effect=search_error))
        reader_agent = SimpleNamespace(
            invoke=Mock(return_value={
                "messages": [SimpleNamespace(content="Read evidence")]
            })
        )
        writer = SimpleNamespace(invoke=Mock(return_value="Research report"))
        critic = SimpleNamespace(invoke=Mock(return_value="Critical review"))
        direct_search_tool = SimpleNamespace(
            invoke=Mock(
                return_value=(
                    "Title: Reliable source\nURL: https://example.org\n"
                    "Snippet: Evidence."
                )
            )
        )

        with (
            patch.object(pipeline, "build_web_search_agent", return_value=search_agent),
            patch.object(pipeline, "build_web_reader_agent", return_value=reader_agent),
            patch.object(pipeline, "writer_chain", writer),
            patch.object(pipeline, "critic_chain", critic),
            patch.object(pipeline, "web_search", direct_search_tool),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            result = pipeline.run_research_pipeline("topic to search")

        search_agent.invoke.assert_called_once()
        direct_search_tool.invoke.assert_called_once_with({"query": "topic to search"})
        self.assertEqual(
            result["search_results"],
            "Title: Reliable source\nURL: https://example.org\nSnippet: Evidence.",
        )
        reader_input = reader_agent.invoke.call_args.args[0]["messages"][0][1]
        self.assertIn("https://example.org", reader_input)
        writer.invoke.assert_called_once()
        critic.invoke.assert_called_once()

    def test_other_groq_bad_requests_are_not_hidden_by_search_fallback(self) -> None:
        search_error = BadRequestError(
            "Invalid API request",
            response=httpx.Response(
                400,
                request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
            ),
            body={"error": {"code": "invalid_request_error"}},
        )
        search_agent = SimpleNamespace(invoke=Mock(side_effect=search_error))

        with (
            patch.object(pipeline, "build_web_search_agent", return_value=search_agent),
            patch.object(pipeline, "web_search") as direct_search_tool,
            contextlib.redirect_stdout(io.StringIO()),
            self.assertRaises(BadRequestError),
        ):
            pipeline.run_research_pipeline("topic to search")

        direct_search_tool.invoke.assert_not_called()


if __name__ == "__main__":
    unittest.main()
