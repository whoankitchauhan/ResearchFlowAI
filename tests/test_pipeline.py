import contextlib
import io
import unittest
from types import SimpleNamespace
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
