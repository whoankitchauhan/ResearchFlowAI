import contextlib
import io
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

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


if __name__ == "__main__":
    unittest.main()
