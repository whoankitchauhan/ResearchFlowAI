import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import app


class ResearchApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app.app)

    def test_health_and_frontend_are_served(self) -> None:
        health = self.client.get("/api/health")
        page = self.client.get("/")
        asset = self.client.get("/assets/app.js")

        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json(), {"status": "ok"})
        self.assertIn("ResearchFlowAI", page.text)
        self.assertEqual(asset.status_code, 200)
        self.assertIn("startJob", asset.text)

    def test_topic_validation_rejects_blank_and_oversized_values(self) -> None:
        self.assertEqual(
            self.client.post("/api/jobs", json={"topic": "  "}).status_code,
            422,
        )
        self.assertEqual(
            self.client.post("/api/jobs", json={"topic": "x" * 501}).status_code,
            422,
        )

    def test_job_runs_pipeline_and_returns_all_research_stages(self) -> None:
        def fake_pipeline(topic: str, progress_callback=None) -> dict[str, str]:
            self.assertEqual(topic, "Grid resilience")
            progress_callback("search", 5)
            progress_callback("completed", 100)
            return {
                "search_results": "Search results",
                "scraped_content": "Read content",
                "report": "Final report",
                "feedback": "Critical review",
            }

        with patch("app.run_research_pipeline", side_effect=fake_pipeline):
            created = self.client.post(
                "/api/jobs",
                json={"topic": "  Grid resilience  "},
            )
            self.assertEqual(created.status_code, 202)
            job_id = created.json()["id"]

            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                response = self.client.get(f"/api/jobs/{job_id}")
                if response.json()["status"] == "completed":
                    break
                time.sleep(0.02)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["topic"], "Grid resilience")
        self.assertEqual(response.json()["status"], "completed")
        self.assertEqual(response.json()["progress"], 100)
        self.assertEqual(response.json()["result"]["report"], "Final report")
        self.assertIsNone(response.json()["error"])

    def test_failed_job_does_not_expose_exception_details(self) -> None:
        with self.assertLogs("app", level="ERROR") as captured:
            with patch("app.run_research_pipeline", side_effect=RuntimeError("private detail")):
                created = self.client.post("/api/jobs", json={"topic": "Research topic"})
                job_id = created.json()["id"]

                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    response = self.client.get(f"/api/jobs/{job_id}")
                    if response.json()["status"] == "failed":
                        break
                    time.sleep(0.02)

        self.assertEqual(response.json()["status"], "failed")
        self.assertNotIn("private detail", response.json()["error"])
        self.assertIn("private detail", captured.output[0])

    def test_unknown_job_returns_not_found(self) -> None:
        response = self.client.get("/api/jobs/00000000-0000-0000-0000-000000000000")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
