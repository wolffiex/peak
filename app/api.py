from anthropic import AsyncAnthropic
import asyncio

# Semaphore to limit concurrent API calls
anthropic_semaphore = asyncio.Semaphore(3)
# Create async client instead of synchronous one
client = AsyncAnthropic()


async def call_anthropic_api(
    model, messages, system=None, max_tokens=1024, temperature=0
):
    """
    Centralized function for non-streaming Anthropic API calls with concurrency control.

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


async def stream_anthropic_api(
    model, messages, system=None, max_tokens=1024, temperature=0
):
    """
    Streaming version of Anthropic API calls with concurrency control.

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
