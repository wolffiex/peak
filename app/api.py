from anthropic import AsyncAnthropic, APIError, RateLimitError
import asyncio
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

# Semaphore to limit concurrent API calls
anthropic_semaphore = asyncio.Semaphore(3)
# Create async client instead of synchronous one
client = AsyncAnthropic()


@retry(
    retry=retry_if_exception_type((RateLimitError, APIError)),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    reraise=True,
)
async def call_anthropic_api(
    model, messages, system=None, max_tokens=1024, temperature=0.0
):
    """
    Centralized function for non-streaming Anthropic API calls with concurrency control.
    Includes retry logic for handling rate limits and API errors.

    Args:
        model: The Claude model to use
        messages: The conversation messages
        system: Optional system prompt
        max_tokens: Maximum tokens to generate
        temperature: Sampling temperature

    Returns:
        The API response
    """

    # Use semaphore to control concurrency
    async with anthropic_semaphore:
        # Create the API parameters
        params = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }

        # Add system prompt if provided
        if system:
            params["system"] = system

        # Use await with the async client
        response = await client.messages.create(**params)
        return response


@retry(
    retry=retry_if_exception_type((RateLimitError, APIError)),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    reraise=True,
)
async def stream_anthropic_api(
    model, messages, system=None, max_tokens=1024, temperature=0.0
):
    """
    Streaming version of Anthropic API calls with concurrency control.
    Includes retry logic for handling rate limits and API errors.

    Args:
        model: The Claude model to use
        messages: The conversation messages
        system: Optional system prompt
        max_tokens: Maximum tokens to generate
        temperature: Sampling temperature

    Yields:
        Content chunks from the streaming response
    """

    # Use semaphore to control concurrency
    async with anthropic_semaphore:
        # Create the API parameters
        params = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }

        # Add system prompt if provided
        if system:
            params["system"] = system

        # Return the stream directly for the caller to iterate over
        async with client.messages.stream(**params) as stream:
            async for chunk in stream:
                if chunk.type == "content_block_delta":
                    yield chunk.delta.text
