"""New ADK agent for the OKF RFC leadership demo.

Live GCP: writes BQAA agent_events into a fresh dataset (okf_rfc_demo),
not adk_logs. Model: gemini-3.8-flash. Tools emit context_ref only.
"""
from __future__ import annotations

import asyncio
import os
import uuid

from google.adk.agents import Agent
from google.adk.models import Gemini
from google.adk.plugins.bigquery_agent_analytics_plugin import (
    BigQueryAgentAnalyticsPlugin,
)
from google.adk.plugins.bigquery_agent_analytics_plugin import BigQueryLoggerConfig
from google.adk.runners import InMemoryRunner
from google.genai import types

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "test-project-0728-467323")
DATASET = os.environ.get("OKF_DEMO_DATASET", "okf_rfc_demo")
TABLE = os.environ.get("OKF_DEMO_TABLE", "agent_events")
LOCATION = os.environ.get("OKF_DEMO_BQ_LOCATION", "US")
MODEL = os.environ.get("DEMO_MODEL_ID", "gemini-3.8-flash")
AGENT_LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")

# Pinned derived identities from rfc/demo/derived/identities.json
CONTEXT_REF = os.environ.get(
    "OKF_CONTEXT_REF",
    "okf:env-demo#"
    + "a25e1c0ccbcad270bf9e3b7a8f792167795381b6880bdc8a1ccde8df40ea52c5"[:12],
)
PUBLICATION_ID = (
    "sha256:a25e1c0ccbcad270bf9e3b7a8f792167795381b6880bdc8a1ccde8df40ea52c5"
)

os.environ["GOOGLE_CLOUD_PROJECT"] = PROJECT
os.environ["GOOGLE_CLOUD_LOCATION"] = AGENT_LOCATION
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"


def lookup_okf_context(context_ref: str) -> dict:
    """Retrieve sanctioned OKF context. Returns context_ref only (no paths, query, principal)."""
    # Never return concept_version_id, paths, principal, or query text.
    return {
        "ok": True,
        "context_ref": context_ref or CONTEXT_REF,
        "publication_id": PUBLICATION_ID,
        "note": "derived/demo bundle; not canonical authoring",
    }


root_agent = Agent(
    name="okf_rfc_consume_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    description="Leadership demo: consume derived OKF context for Germany active-customer revenue.",
    instruction=(
        "You are an ADK agent that answers questions using derived OKF context. "
        "Always call lookup_okf_context with the provided context_ref before answering. "
        "Never print SQL, principal, file paths, or concept_version_id. "
        "Cite only context_ref. Model is gemini-3.8-flash. "
        "If asked about Germany active-customer revenue, say the number is produced "
        "by the sanctioned computation bound in that context_ref, and that BQAA is observer-only."
    ),
    tools=[lookup_okf_context],
)

bq_plugin = BigQueryAgentAnalyticsPlugin(
    project_id=PROJECT,
    dataset_id=DATASET,
    table_id=TABLE,
    location=LOCATION,
    config=BigQueryLoggerConfig(
        enabled=True,
        max_content_length=64 * 1024,
        batch_size=1,
        shutdown_timeout=20.0,
    ),
)


async def main() -> None:
    runner = InMemoryRunner(
        agent=root_agent,
        app_name="okf_rfc_demo",
        plugins=[bq_plugin],
    )
    user_id = "leadership-demo"
    session = await runner.session_service.create_session(
        app_name=runner.app_name, user_id=user_id
    )
    session_id = session.id
    prompt = (
        "What was active-customer revenue in Germany last quarter, "
        f"and can I trust the number? Use context_ref={CONTEXT_REF}."
    )
    print("PROJECT", PROJECT)
    print("DATASET", f"{PROJECT}.{DATASET}.{TABLE}")
    print("MODEL", MODEL)
    print("SESSION", session_id)
    print("CONTEXT_REF", CONTEXT_REF)
    content = types.Content(role="user", parts=[types.Part(text=prompt)])
    async for event in runner.run_async(
        user_id=user_id, session_id=session_id, new_message=content
    ):
        if getattr(event, "content", None) and event.content.parts:
            for part in event.content.parts:
                if getattr(part, "text", None):
                    print("EVENT_TEXT", part.text[:500])
    print("DONE", session_id)
    closer = getattr(runner, "close", None)
    if closer:
        maybe = closer()
        if hasattr(maybe, "__await__"):
            await maybe


if __name__ == "__main__":
    asyncio.run(main())
