import os
import sys

# Define base paths relative to this file
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ADK_PROJECT_DIR = os.path.dirname(CURRENT_DIR)
BUCKET_DATA_DIR = os.path.dirname(ADK_PROJECT_DIR)

# Add paths to sys.path if not already present to allow absolute imports
if ADK_PROJECT_DIR not in sys.path:
    sys.path.append(ADK_PROJECT_DIR)
if BUCKET_DATA_DIR not in sys.path:
    sys.path.append(BUCKET_DATA_DIR)

import asyncio
from dotenv import load_dotenv
from google.adk import Agent
from google.adk.runners import InMemoryRunner
from google.adk.sessions import Session
from google.genai import types
from google.adk.models import Gemini, LlmResponse
from google.adk.apps.app import App

from adk_utils.plugins import Graceful429Plugin

import logging
import google.cloud.logging

# 1. Load environment variables from the agent directory's .env file
load_dotenv()
model_name = os.getenv("MODEL")

# Retry options help avoid the occasional error from popular models
# receiving too many requests at once.
RETRY_OPTIONS = types.HttpRetryOptions(initial_delay=1, max_delay=3, attempts=30)

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)

cloud_logging_client = google.cloud.logging.Client()
cloud_logging_client.setup_logging()

# Create an async main function
async def main():

    # 2. Set or load other variables
    app_name = 'app_agent'
    user_id_1 = 'user1'

    # 3. Define Your Agent
    root_agent = Agent(
        model=Gemini(model=model_name, retry_options=RETRY_OPTIONS),
        name="trivia_agent",
            instruction="Answer questions.",
    )

    graceful_plugin = Graceful429Plugin(
        name="graceful_429_plugin",
        fallback_text='{"capital": "Paris (Mocked due to Quota)"}'
    )

    # UNCOMMENT THE LINE BELOW TO TEST FAILOVER:
    # graceful_plugin.apply_test_failover(root_agent)

    graceful_plugin.apply_429_interceptor(root_agent)

    app = App(
        name=app_name,
        root_agent=root_agent,
        plugins=[graceful_plugin]
    )

    # 3. Create a Runner
    runner = InMemoryRunner(app=app)

    # 4. Create a session
    my_session = await runner.session_service.create_session(
        app_name=app_name, user_id=user_id_1
    )

    # 5. Prepare a function to package a user's message as
    # genai.types.Content, run it asynchronously, and iterate
    # through the response 
    async def run_prompt(session: Session, new_message: str):
        content = types.Content(
                role='user', parts=[types.Part.from_text(text=new_message)]
            )
        logging.info(f'** User says: {new_message}')
        async for event in runner.run_async(
            user_id=user_id_1,
            session_id=session.id,
            new_message=content,
        ):
            if event.content.parts and event.content.parts[0].text:
                logging.info(f'** {event.author}: {event.content.parts[0].text}')


    # 6. Use this function on a new query
    query = "What is the capital of France?"
    await run_prompt(my_session, query)

    cloud_logging_client.close()


if __name__ == "__main__":
    asyncio.run(main())