

--- SOURCE: https://raw.githubusercontent.com/openai/openai-python/main/README.md ---

# OpenAI Python API library

<!-- prettier-ignore -->
[![PyPI version](https://img.shields.io/pypi/v/openai.svg?label=pypi%20(stable))](https://pypi.org/project/openai/)

The OpenAI Python library provides convenient access to the OpenAI REST API from any Python 3.9+
application. The library includes type definitions for all request params and response fields,
and offers both synchronous and asynchronous clients powered by [httpx](https://github.com/encode/httpx).

It is generated from our [OpenAPI specification](https://github.com/openai/openai-openapi) with [Stainless](https://stainlessapi.com/).

## Documentation

The REST API documentation can be found on [platform.openai.com](https://platform.openai.com/docs/api-reference). The full API of this library can be found in [api.md](api.md).

## Installation

```sh
# install from PyPI
pip install openai
```

## Usage

The full API of this library can be found in [api.md](api.md).

The primary API for interacting with OpenAI models is the [Responses API](https://platform.openai.com/docs/api-reference/responses). You can generate text from the model with the code below.

```python
import os
from openai import OpenAI

client = OpenAI(
    # This is the default and can be omitted
    api_key=os.environ.get("OPENAI_API_KEY"),
)

response = client.responses.create(
    model="gpt-5.2",
    instructions="You are a coding assistant that talks like a pirate.",
    input="How do I check if a Python object is an instance of a class?",
)

print(response.output_text)
```

The previous standard (supported indefinitely) for generating text is the [Chat Completions API](https://platform.openai.com/docs/api-reference/chat). You can use that API to generate text from the model with the code below.

```python
from openai import OpenAI

client = OpenAI()

completion = client.chat.completions.create(
    model="gpt-5.2",
    messages=[
        {"role": "developer", "content": "Talk like a pirate."},
        {
            "role": "user",
            "content": "How do I check if a Python object is an instance of a class?",
        },
    ],
)

print(completion.choices[0].message.content)
```

While you can provide an `api_key` keyword argument,
we recommend using [python-dotenv](https://pypi.org/project/python-dotenv/)
to add `OPENAI_API_KEY="My API Key"` to your `.env` file
so that your API key is not stored in source control.
[Get an API key here](https://platform.openai.com/settings/organization/api-keys).

### Vision

With an image URL:

```python
prompt = "What is in this image?"
img_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d5/2023_06_08_Raccoon1.jpg/1599px-2023_06_08_Raccoon1.jpg"

response = client.responses.create(
    model="gpt-5.2",
    input=[
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": prompt},
                {"type": "input_image", "image_url": f"{img_url}"},
            ],
        }
    ],
)
```

With the image as a base64 encoded string:

```python
import base64
from openai import OpenAI

client = OpenAI()

prompt = "What is in this image?"
with open("path/to/image.png", "rb") as image_file:
    b64_image = base64.b64encode(image_file.read()).decode("utf-8")

response = client.responses.create(
    model="gpt-5.2",
    input=[
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": prompt},
                {"type": "input_image", "image_url": f"data:image/png;base64,{b64_image}"},
            ],
        }
    ],
)
```

## Async usage

Simply import `AsyncOpenAI` instead of `OpenAI` and use `await` with each API call:

```python
import os
import asyncio
from openai import AsyncOpenAI

client = AsyncOpenAI(
    # This is the default and can be omitted
    api_key=os.environ.get("OPENAI_API_KEY"),
)


async def main() -> None:
    response = await client.responses.create(
        model="gpt-5.2", input="Explain disestablishmentarianism to a smart five year old."
    )
    print(response.output_text)


asyncio.run(main())
```

Functionality between the synchronous and asynchronous clients is otherwise identical.

### With aiohttp

By default, the async client uses `httpx` for HTTP requests. However, for improved concurrency performance you may also use `aiohttp` as the HTTP backend.

You can enable this by installing `aiohttp`:

```sh
# install from PyPI
pip install openai[aiohttp]
```

Then you can enable it by instantiating the client with `http_client=DefaultAioHttpClient()`:

```python
import os
import asyncio
from openai import DefaultAioHttpClient
from openai import AsyncOpenAI


async def main() -> None:
    async with AsyncOpenAI(
        api_key=os.environ.get("OPENAI_API_KEY"),  # This is the default and can be omitted
        http_client=DefaultAioHttpClient(),
    ) as client:
        chat_completion = await client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": "Say this is a test",
                }
            ],
            model="gpt-5.2",
        )


asyncio.run(main())
```

## Streaming responses

We provide support for streaming responses using Server Side Events (SSE).

```python
from openai import OpenAI

client = OpenAI()

stream = client.responses.create(
    model="gpt-5.2",
    input="Write a one-sentence bedtime story about a unicorn.",
    stream=True,
)

for event in stream:
    print(event)
```

The async client uses the exact same interface.

```python
import asyncio
from openai import AsyncOpenAI

client = AsyncOpenAI()


async def main():
    stream = await client.responses.create(
        model="gpt-5.2",
        input="Write a one-sentence bedtime story about a unicorn.",
        stream=True,
    )

    async for event in stream:
        print(event)


asyncio.run(main())
```

## Realtime API

The Realtime API enables you to build low-latency, multi-modal conversational experiences. It currently supports text and audio as both input and output, as well as [function calling](https://platform.openai.com/docs/guides/function-calling) through a WebSocket connection.

Under the hood the SDK uses the [`websockets`](https://websockets.readthedocs.io/en/stable/) library to manage connections.

The Realtime API works through a combination of client-sent events and server-sent events. Clients can send events to do things like update session configuration or send text and audio inputs. Server events confirm when audio responses have completed, or when a text response from the model has been received. A full event reference can be found [here](https://platform.openai.com/docs/api-reference/realtime-client-events) and a guide can be found [here](https://platform.openai.com/docs/guides/realtime).

Basic text based example:

```py
import asyncio
from openai import AsyncOpenAI

async def main():
    client = AsyncOpenAI()

    async with client.realtime.connect(model="gpt-realtime") as connection:
        await connection.session.update(
            session={"type": "realtime", "output_modalities": ["text"]}
        )

        await connection.conversation.item.create(
            item={
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Say hello!"}],
            }
        )
        await connection.response.create()

        async for event in connection:
            if event.type == "response.output_text.delta":
                print(event.delta, flush=True, end="")

            elif event.type == "response.output_text.done":
                print()

            elif event.type == "response.done":
                break

asyncio.run(main())
```

However the real magic of the Realtime API is handling audio inputs / outputs, see this example [TUI script](https://github.com/openai/openai-python/blob/main/examples/realtime/push_to_talk_app.py) for a fully fledged example.

### Realtime error handling

Whenever an error occurs, the Realtime API will send an [`error` event](https://platform.openai.com/docs/guides/realtime-model-capabilities#error-handling) and the connection will stay open and remain usable. This means you need to handle it yourself, as _no errors are raised directly_ by the SDK when an `error` event comes in.

```py
client = AsyncOpenAI()

async with client.realtime.connect(model="gpt-realtime") as connection:
    ...
    async for event in connection:
        if event.type == 'error':
            print(event.error.type)
            print(event.error.code)
            print(event.error.event_id)
            print(event.error.message)
```

## Using types

Nested request parameters are [TypedDicts](https://docs.python.org/3/library/typing.html#typing.TypedDict). Responses are [Pydantic models](https://docs.pydantic.dev) which also provide helper methods for things like:

- Serializing back into JSON, `model.to_json()`
- Converting to a dictionary, `model.to_dict()`

Typed requests and responses provide autocomplete and documentation within your editor. If you would like to see type errors in VS Code to help catch bugs earlier, set `python.analysis.typeCheckingMode` to `basic`.

## Pagination

List methods in the OpenAI API are paginated.

This library provides auto-paginating iterators with each list response, so you do not have to request successive pages manually:

```python
from openai import OpenAI

client = OpenAI()

all_jobs = []
# Automatically fetches more pages as needed.
for job in client.fine_tuning.jobs.list(
    limit=20,
):
    # Do something with job here
    all_jobs.append(job)
print(all_jobs)
```

Or, asynchronously:

```python
import asyncio
from openai import AsyncOpenAI

client = AsyncOpenAI()


async def main() -> None:
    all_jobs = []
    # Iterate through items across all pages, issuing requests as needed.
    async for job in client.fine_tuning.jobs.list(
        limit=20,
    ):
        all_jobs.append(job)
    print(all_jobs)


asyncio.run(main())
```

Alternatively, you can use the `.has_next_page()`, `.next_page_info()`, or `.get_next_page()` methods for more granular control working with pages:

```python
first_page = await client.fine_tuning.jobs.list(
    limit=20,
)
if first_page.has_next_page():
    print(f"will fetch next page using these details: {first_page.next_page_info()}")
    next_page = await first_page.get_next_page()
    print(f"number of items we just fetched: {len(next_page.data)}")

# Remove `await` for non-async usage.
```

Or just work directly with the returned data:

```python
first_page = await client.fine_tuning.jobs.list(
    limit=20,
)

print(f"next page cursor: {first_page.after}")  # => "next page cursor: ..."
for job in first_page.data:
    print(job.id)

# Remove `await` for non-async usage.
```

## Nested params

Nested parameters are dictionaries, typed using `TypedDict`, for example:

```python
from openai import OpenAI

client = OpenAI()

response = client.chat.responses.create(
    input=[
        {
            "role": "user",
            "content": "How much ?",
        }
    ],
    model="gpt-5.2",
    response_format={"type": "json_object"},
)
```

## File uploads

Request parameters that correspond to file uploads can be passed as `bytes`, or a [`PathLike`](https://docs.python.org/3/library/os.html#os.PathLike) instance or a tuple of `(filename, contents, media type)`.

```python
from pathlib import Path
from openai import OpenAI

client = OpenAI()

client.files.create(
    file=Path("input.jsonl"),
    purpose="fine-tune",
)
```

The async client uses the exact same interface. If you pass a [`PathLike`](https://docs.python.org/3/library/os.html#os.PathLike) instance, the file contents will be read asynchronously automatically.

## Webhook Verification

Verifying webhook signatures is _optional but encouraged_.

For more information about webhooks, see [the API docs](https://platform.openai.com/docs/guides/webhooks).

### Parsing webhook payloads

For most use cases, you will likely want to verify the webhook and parse the payload at the same time. To achieve this, we provide the method `client.webhooks.unwrap()`, which parses a webhook request and verifies that it was sent by OpenAI. This method will raise an error if the signature is invalid.

Note that the `body` parameter must be the raw JSON string sent from the server (do not parse it first). The `.unwrap()` method will parse this JSON for you into an event object after verifying the webhook was sent from OpenAI.

```python
from openai import OpenAI
from flask import Flask, request

app = Flask(__name__)
client = OpenAI()  # OPENAI_WEBHOOK_SECRET environment variable is used by default


@app.route("/webhook", methods=["POST"])
def webhook():
    request_body = request.get_data(as_text=True)

    try:
        event = client.webhooks.unwrap(request_body, request.headers)

        if event.type == "response.completed":
            print("Response completed:", event.data)
        elif event.type == "response.failed":
            print("Response failed:", event.data)
        else:
            print("Unhandled event type:", event.type)

        return "ok"
    except Exception as e:
        print("Invalid signature:", e)
        return "Invalid signature", 400


if __name__ == "__main__":
    app.run(port=8000)
```

### Verifying webhook payloads directly

In some cases, you may want to verify the webhook separately from parsing the payload. If you prefer to handle these steps separately, we provide the method `client.webhooks.verify_signature()` to _only verify_ the signature of a webhook request. Like `.unwrap()`, this method will raise an error if the signature is invalid.

Note that the `body` parameter must be the raw JSON string sent from the server (do not parse it first). You will then need to parse the body after verifying the signature.

```python
import json
from openai import OpenAI
from flask import Flask, request

app = Flask(__name__)
client = OpenAI()  # OPENAI_WEBHOOK_SECRET environment variable is used by default


@app.route("/webhook", methods=["POST"])
def webhook():
    request_body = request.get_data(as_text=True)

    try:
        client.webhooks.verify_signature(request_body, request.headers)

        # Parse the body after verification
        event = json.loads(request_body)
        print("Verified event:", event)

        return "ok"
    except Exception as e:
        print("Invalid signature:", e)
        return "Invalid signature", 400


if __name__ == "__main__":
    app.run(port=8000)
```

## Handling errors

When the library is unable to connect to the API (for example, due to network connection problems or a timeout), a subclass of `openai.APIConnectionError` is raised.

When the API returns a non-success status code (that is, 4xx or 5xx
response), a subclass of `openai.APIStatusError` is raised, containing `status_code` and `response` properties.

All errors inherit from `openai.APIError`.

```python
import openai
from openai import OpenAI

client = OpenAI()

try:
    client.fine_tuning.jobs.create(
        model="gpt-4o",
        training_file="file-abc123",
    )
except openai.APIConnectionError as e:
    print("The server could not be reached")
    print(e.__cause__)  # an underlying Exception, likely raised within httpx.
except openai.RateLimitError as e:
    print("A 429 status code was received; we should back off a bit.")
except openai.APIStatusError as e:
    print("Another non-200-range status code was received")
    print(e.status_code)
    print(e.response)
```

Error codes are as follows:

| Status Code | Error Type                 |
| ----------- | -------------------------- |
| 400         | `BadRequestError`          |
| 401         | `AuthenticationError`      |
| 403         | `PermissionDeniedError`    |
| 404         | `NotFoundError`            |
| 422         | `UnprocessableEntityError` |
| 429         | `RateLimitError`           |
| >=500       | `InternalServerError`      |
| N/A         | `APIConnectionError`       |

## Request IDs

> For more information on debugging requests, see [these docs](https://platform.openai.com/docs/api-reference/debugging-requests)

All object responses in the SDK provide a `_request_id` property which is added from the `x-request-id` response header so that you can quickly log failing requests and report them back to OpenAI.

```python
response = await client.responses.create(
    model="gpt-5.2",
    input="Say 'this is a test'.",
)
print(response._request_id)  # req_123
```

Note that unlike other properties that use an `_` prefix, the `_request_id` property
_is_ public. Unless documented otherwise, _all_ other `_` prefix properties,
methods and modules are _private_.

> [!IMPORTANT]  
> If you need to access request IDs for failed requests you must catch the `APIStatusError` exception

```python
import openai

try:
    completion = await client.chat.completions.create(
        messages=[{"role": "user", "content": "Say this is a test"}], model="gpt-5.2"
    )
except openai.APIStatusError as exc:
    print(exc.request_id)  # req_123
    raise exc
```

## Retries

Certain errors are automatically retried 2 times by default, with a short exponential backoff.
Connection errors (for example, due to a network connectivity problem), 408 Request Timeout, 409 Conflict,
429 Rate Limit, and >=500 Internal errors are all retried by default.

You can use the `max_retries` option to configure or disable retry settings:

```python
from openai import OpenAI

# Configure the default for all requests:
client = OpenAI(
    # default is 2
    max_retries=0,
)

# Or, configure per-request:
client.with_options(max_retries=5).chat.completions.create(
    messages=[
        {
            "role": "user",
            "content": "How can I get the name of the current day in JavaScript?",
        }
    ],
    model="gpt-5.2",
)
```

## Timeouts

By default requests time out after 10 minutes. You can configure this with a `timeout` option,
which accepts a float or an [`httpx.Timeout`](https://www.python-httpx.org/advanced/timeouts/#fine-tuning-the-configuration) object:

```python
from openai import OpenAI

# Configure the default for all requests:
client = OpenAI(
    # 20 seconds (default is 10 minutes)
    timeout=20.0,
)

# More granular control:
client = OpenAI(
    timeout=httpx.Timeout(60.0, read=5.0, write=10.0, connect=2.0),
)

# Override per-request:
client.with_options(timeout=5.0).chat.completions.create(
    messages=[
        {
            "role": "user",
            "content": "How can I list all files in a directory using Python?",
        }
    ],
    model="gpt-5.2",
)
```

On timeout, an `APITimeoutError` is thrown.

Note that requests that time out are [retried twice by default](#retries).

## Advanced

### Logging

We use the standard library [`logging`](https://docs.python.org/3/library/logging.html) module.

You can enable logging by setting the environment variable `OPENAI_LOG` to `info`.

```shell
$ export OPENAI_LOG=info
```

Or to `debug` for more verbose logging.

### How to tell whether `None` means `null` or missing

In an API response, a field may be explicitly `null`, or missing entirely; in either case, its value is `None` in this library. You can differentiate the two cases with `.model_fields_set`:

```py
if response.my_field is None:
  if 'my_field' not in response.model_fields_set:
    print('Got json like {}, without a "my_field" key present at all.')
  else:
    print('Got json like {"my_field": null}.')
```

### Accessing raw response data (e.g. headers)

The "raw" Response object can be accessed by prefixing `.with_raw_response.` to any HTTP method call, e.g.,

```py
from openai import OpenAI

client = OpenAI()
response = client.chat.completions.with_raw_response.create(
    messages=[{
        "role": "user",
        "content": "Say this is a test",
    }],
    model="gpt-5.2",
)
print(response.headers.get('X-My-Header'))

completion = response.parse()  # get the object that `chat.completions.create()` would have returned
print(completion)
```

These methods return a [`LegacyAPIResponse`](https://github.com/openai/openai-python/tree/main/src/openai/_legacy_response.py) object. This is a legacy class as we're changing it slightly in the next major version.

For the sync client this will mostly be the same with the exception
of `content` & `text` will be methods instead of properties. In the
async client, all methods will be async.

A migration script will be provided & the migration in general should
be smooth.

#### `.with_streaming_response`

The above interface eagerly reads the full response body when you make the request, which may not always be what you want.

To stream the response body, use `.with_streaming_response` instead, which requires a context manager and only reads the response body once you call `.read()`, `.text()`, `.json()`, `.iter_bytes()`, `.iter_text()`, `.iter_lines()` or `.parse()`. In the async client, these are async methods.

As such, `.with_streaming_response` methods return a different [`APIResponse`](https://github.com/openai/openai-python/tree/main/src/openai/_response.py) object, and the async client returns an [`AsyncAPIResponse`](https://github.com/openai/openai-python/tree/main/src/openai/_response.py) object.

```python
with client.chat.completions.with_streaming_response.create(
    messages=[
        {
            "role": "user",
            "content": "Say this is a test",
        }
    ],
    model="gpt-5.2",
) as response:
    print(response.headers.get("X-My-Header"))

    for line in response.iter_lines():
        print(line)
```

The context manager is required so that the response will reliably be closed.

### Making custom/undocumented requests

This library is typed for convenient access to the documented API.

If you need to access undocumented endpoints, params, or response properties, the library can still be used.

#### Undocumented endpoints

To make requests to undocumented endpoints, you can make requests using `client.get`, `client.post`, and other
http verbs. Options on the client will be respected (such as retries) when making this request.

```py
import httpx

response = client.post(
    "/foo",
    cast_to=httpx.Response,
    body={"my_param": True},
)

print(response.headers.get("x-foo"))
```

#### Undocumented request params

If you want to explicitly send an extra param, you can do so with the `extra_query`, `extra_body`, and `extra_headers` request
options.

#### Undocumented response properties

To access undocumented response properties, you can access the extra fields like `response.unknown_prop`. You
can also get all the extra fields on the Pydantic model as a dict with
[`response.model_extra`](https://docs.pydantic.dev/latest/api/base_model/#pydantic.BaseModel.model_extra).

### Configuring the HTTP client

You can directly override the [httpx client](https://www.python-httpx.org/api/#client) to customize it for your use case, including:

- Support for [proxies](https://www.python-httpx.org/advanced/proxies/)
- Custom [transports](https://www.python-httpx.org/advanced/transports/)
- Additional [advanced](https://www.python-httpx.org/advanced/clients/) functionality

```python
import httpx
from openai import OpenAI, DefaultHttpxClient

client = OpenAI(
    # Or use the `OPENAI_BASE_URL` env var
    base_url="http://my.test.server.example.com:8083/v1",
    http_client=DefaultHttpxClient(
        proxy="http://my.test.proxy.example.com",
        transport=httpx.HTTPTransport(local_address="0.0.0.0"),
    ),
)
```

You can also customize the client on a per-request basis by using `with_options()`:

```python
client.with_options(http_client=DefaultHttpxClient(...))
```

### Managing HTTP resources

By default the library closes underlying HTTP connections whenever the client is [garbage collected](https://docs.python.org/3/reference/datamodel.html#object.__del__). You can manually close the client using the `.close()` method if desired, or with a context manager that closes when exiting.

```py
from openai import OpenAI

with OpenAI() as client:
  # make requests here
  ...

# HTTP client is now closed
```

## Microsoft Azure OpenAI

To use this library with [Azure OpenAI](https://learn.microsoft.com/azure/ai-services/openai/overview), use the `AzureOpenAI`
class instead of the `OpenAI` class.

> [!IMPORTANT]
> The Azure API shape differs from the core API shape which means that the static types for responses / params
> won't always be correct.

```py
from openai import AzureOpenAI

# gets the API Key from environment variable AZURE_OPENAI_API_KEY
client = AzureOpenAI(
    # https://learn.microsoft.com/azure/ai-services/openai/reference#rest-api-versioning
    api_version="2023-07-01-preview",
    # https://learn.microsoft.com/azure/cognitive-services/openai/how-to/create-resource?pivots=web-portal#create-a-resource
    azure_endpoint="https://example-endpoint.openai.azure.com",
)

completion = client.chat.completions.create(
    model="deployment-name",  # e.g. gpt-35-instant
    messages=[
        {
            "role": "user",
            "content": "How do I output all files in a directory using Python?",
        },
    ],
)
print(completion.to_json())
```

In addition to the options provided in the base `OpenAI` client, the following options are provided:

- `azure_endpoint` (or the `AZURE_OPENAI_ENDPOINT` environment variable)
- `azure_deployment`
- `api_version` (or the `OPENAI_API_VERSION` environment variable)
- `azure_ad_token` (or the `AZURE_OPENAI_AD_TOKEN` environment variable)
- `azure_ad_token_provider`

An example of using the client with Microsoft Entra ID (formerly known as Azure Active Directory) can be found [here](https://github.com/openai/openai-python/blob/main/examples/azure_ad.py).

## Versioning

This package generally follows [SemVer](https://semver.org/spec/v2.0.0.html) conventions, though certain backwards-incompatible changes may be released as minor versions:

1. Changes that only affect static types, without breaking runtime behavior.
2. Changes to library internals which are technically public but not intended or documented for external use. _(Please open a GitHub issue to let us know if you are relying on such internals.)_
3. Changes that we do not expect to impact the vast majority of users in practice.

We take backwards-compatibility seriously and work hard to ensure you can rely on a smooth upgrade experience.

We are keen for your feedback; please open an [issue](https://www.github.com/openai/openai-python/issues) with questions, bugs, or suggestions.

### Determining the installed version

If you've upgraded to the latest version but aren't seeing any new features you were expecting then your python environment is likely still using an older version.

You can determine the version that is being used at runtime with:

```py
import openai
print(openai.__version__)
```

## Requirements

Python 3.9 or higher.

## Contributing

See [the contributing documentation](./CONTRIBUTING.md).


--- SOURCE: https://raw.githubusercontent.com/openai/openai-python/main/api.md ---

# Shared Types

```python
from openai.types import (
    AllModels,
    ChatModel,
    ComparisonFilter,
    CompoundFilter,
    CustomToolInputFormat,
    ErrorObject,
    FunctionDefinition,
    FunctionParameters,
    Metadata,
    Reasoning,
    ReasoningEffort,
    ResponseFormatJSONObject,
    ResponseFormatJSONSchema,
    ResponseFormatText,
    ResponseFormatTextGrammar,
    ResponseFormatTextPython,
    ResponsesModel,
)
```

# Completions

Types:

```python
from openai.types import Completion, CompletionChoice, CompletionUsage
```

Methods:

- <code title="post /completions">client.completions.<a href="./src/openai/resources/completions.py">create</a>(\*\*<a href="src/openai/types/completion_create_params.py">params</a>) -> <a href="./src/openai/types/completion.py">Completion</a></code>

# Chat

Types:

```python
from openai.types import ChatModel
```

## Completions

Types:

```python
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionAllowedToolChoice,
    ChatCompletionAssistantMessageParam,
    ChatCompletionAudio,
    ChatCompletionAudioParam,
    ChatCompletionChunk,
    ChatCompletionContentPart,
    ChatCompletionContentPartImage,
    ChatCompletionContentPartInputAudio,
    ChatCompletionContentPartRefusal,
    ChatCompletionContentPartText,
    ChatCompletionCustomTool,
    ChatCompletionDeleted,
    ChatCompletionDeveloperMessageParam,
    ChatCompletionFunctionCallOption,
    ChatCompletionFunctionMessageParam,
    ChatCompletionFunctionTool,
    ChatCompletionMessage,
    ChatCompletionMessageCustomToolCall,
    ChatCompletionMessageFunctionToolCall,
    ChatCompletionMessageParam,
    ChatCompletionMessageToolCallUnion,
    ChatCompletionModality,
    ChatCompletionNamedToolChoice,
    ChatCompletionNamedToolChoiceCustom,
    ChatCompletionPredictionContent,
    ChatCompletionRole,
    ChatCompletionStoreMessage,
    ChatCompletionStreamOptions,
    ChatCompletionSystemMessageParam,
    ChatCompletionTokenLogprob,
    ChatCompletionToolUnion,
    ChatCompletionToolChoiceOption,
    ChatCompletionToolMessageParam,
    ChatCompletionUserMessageParam,
    ChatCompletionAllowedTools,
    ChatCompletionReasoningEffort,
)
```

Methods:

- <code title="post /chat/completions">client.chat.completions.<a href="./src/openai/resources/chat/completions/completions.py">create</a>(\*\*<a href="src/openai/types/chat/completion_create_params.py">params</a>) -> <a href="./src/openai/types/chat/chat_completion.py">ChatCompletion</a></code>
- <code title="get /chat/completions/{completion_id}">client.chat.completions.<a href="./src/openai/resources/chat/completions/completions.py">retrieve</a>(completion_id) -> <a href="./src/openai/types/chat/chat_completion.py">ChatCompletion</a></code>
- <code title="post /chat/completions/{completion_id}">client.chat.completions.<a href="./src/openai/resources/chat/completions/completions.py">update</a>(completion_id, \*\*<a href="src/openai/types/chat/completion_update_params.py">params</a>) -> <a href="./src/openai/types/chat/chat_completion.py">ChatCompletion</a></code>
- <code title="get /chat/completions">client.chat.completions.<a href="./src/openai/resources/chat/completions/completions.py">list</a>(\*\*<a href="src/openai/types/chat/completion_list_params.py">params</a>) -> <a href="./src/openai/types/chat/chat_completion.py">SyncCursorPage[ChatCompletion]</a></code>
- <code title="delete /chat/completions/{completion_id}">client.chat.completions.<a href="./src/openai/resources/chat/completions/completions.py">delete</a>(completion_id) -> <a href="./src/openai/types/chat/chat_completion_deleted.py">ChatCompletionDeleted</a></code>

### Messages

Methods:

- <code title="get /chat/completions/{completion_id}/messages">client.chat.completions.messages.<a href="./src/openai/resources/chat/completions/messages.py">list</a>(completion_id, \*\*<a href="src/openai/types/chat/completions/message_list_params.py">params</a>) -> <a href="./src/openai/types/chat/chat_completion_store_message.py">SyncCursorPage[ChatCompletionStoreMessage]</a></code>

# Embeddings

Types:

```python
from openai.types import CreateEmbeddingResponse, Embedding, EmbeddingModel
```

Methods:

- <code title="post /embeddings">client.embeddings.<a href="./src/openai/resources/embeddings.py">create</a>(\*\*<a href="src/openai/types/embedding_create_params.py">params</a>) -> <a href="./src/openai/types/create_embedding_response.py">CreateEmbeddingResponse</a></code>

# Files

Types:

```python
from openai.types import FileContent, FileDeleted, FileObject, FilePurpose
```

Methods:

- <code title="post /files">client.files.<a href="./src/openai/resources/files.py">create</a>(\*\*<a href="src/openai/types/file_create_params.py">params</a>) -> <a href="./src/openai/types/file_object.py">FileObject</a></code>
- <code title="get /files/{file_id}">client.files.<a href="./src/openai/resources/files.py">retrieve</a>(file_id) -> <a href="./src/openai/types/file_object.py">FileObject</a></code>
- <code title="get /files">client.files.<a href="./src/openai/resources/files.py">list</a>(\*\*<a href="src/openai/types/file_list_params.py">params</a>) -> <a href="./src/openai/types/file_object.py">SyncCursorPage[FileObject]</a></code>
- <code title="delete /files/{file_id}">client.files.<a href="./src/openai/resources/files.py">delete</a>(file_id) -> <a href="./src/openai/types/file_deleted.py">FileDeleted</a></code>
- <code title="get /files/{file_id}/content">client.files.<a href="./src/openai/resources/files.py">content</a>(file_id) -> HttpxBinaryResponseContent</code>
- <code title="get /files/{file_id}/content">client.files.<a href="./src/openai/resources/files.py">retrieve_content</a>(file_id) -> <a href="./src/openai/types/file_content.py">str</a></code>
- <code>client.files.<a href="./src/openai/resources/files.py">wait_for_processing</a>(\*args) -> FileObject</code>

# Images

Types:

```python
from openai.types import (
    Image,
    ImageEditCompletedEvent,
    ImageEditPartialImageEvent,
    ImageEditStreamEvent,
    ImageGenCompletedEvent,
    ImageGenPartialImageEvent,
    ImageGenStreamEvent,
    ImageModel,
    ImagesResponse,
)
```

Methods:

- <code title="post /images/variations">client.images.<a href="./src/openai/resources/images.py">create_variation</a>(\*\*<a href="src/openai/types/image_create_variation_params.py">params</a>) -> <a href="./src/openai/types/images_response.py">ImagesResponse</a></code>
- <code title="post /images/edits">client.images.<a href="./src/openai/resources/images.py">edit</a>(\*\*<a href="src/openai/types/image_edit_params.py">params</a>) -> <a href="./src/openai/types/images_response.py">ImagesResponse</a></code>
- <code title="post /images/generations">client.images.<a href="./src/openai/resources/images.py">generate</a>(\*\*<a href="src/openai/types/image_generate_params.py">params</a>) -> <a href="./src/openai/types/images_response.py">ImagesResponse</a></code>

# Audio

Types:

```python
from openai.types import AudioModel, AudioResponseFormat
```

## Transcriptions

Types:

```python
from openai.types.audio import (
    Transcription,
    TranscriptionDiarized,
    TranscriptionDiarizedSegment,
    TranscriptionInclude,
    TranscriptionSegment,
    TranscriptionStreamEvent,
    TranscriptionTextDeltaEvent,
    TranscriptionTextDoneEvent,
    TranscriptionTextSegmentEvent,
    TranscriptionVerbose,
    TranscriptionWord,
    TranscriptionCreateResponse,
)
```

Methods:

- <code title="post /audio/transcriptions">client.audio.transcriptions.<a href="./src/openai/resources/audio/transcriptions.py">create</a>(\*\*<a href="src/openai/types/audio/transcription_create_params.py">params</a>) -> <a href="./src/openai/types/audio/transcription_create_response.py">TranscriptionCreateResponse</a></code>

## Translations

Types:

```python
from openai.types.audio import Translation, TranslationVerbose, TranslationCreateResponse
```

Methods:

- <code title="post /audio/translations">client.audio.translations.<a href="./src/openai/resources/audio/translations.py">create</a>(\*\*<a href="src/openai/types/audio/translation_create_params.py">params</a>) -> <a href="./src/openai/types/audio/translation_create_response.py">TranslationCreateResponse</a></code>

## Speech

Types:

```python
from openai.types.audio import SpeechModel
```

Methods:

- <code title="post /audio/speech">client.audio.speech.<a href="./src/openai/resources/audio/speech.py">create</a>(\*\*<a href="src/openai/types/audio/speech_create_params.py">params</a>) -> HttpxBinaryResponseContent</code>

# Moderations

Types:

```python
from openai.types import (
    Moderation,
    ModerationImageURLInput,
    ModerationModel,
    ModerationMultiModalInput,
    ModerationTextInput,
    ModerationCreateResponse,
)
```

Methods:

- <code title="post /moderations">client.moderations.<a href="./src/openai/resources/moderations.py">create</a>(\*\*<a href="src/openai/types/moderation_create_params.py">params</a>) -> <a href="./src/openai/types/moderation_create_response.py">ModerationCreateResponse</a></code>

# Models

Types:

```python
from openai.types import Model, ModelDeleted
```

Methods:

- <code title="get /models/{model}">client.models.<a href="./src/openai/resources/models.py">retrieve</a>(model) -> <a href="./src/openai/types/model.py">Model</a></code>
- <code title="get /models">client.models.<a href="./src/openai/resources/models.py">list</a>() -> <a href="./src/openai/types/model.py">SyncPage[Model]</a></code>
- <code title="delete /models/{model}">client.models.<a href="./src/openai/resources/models.py">delete</a>(model) -> <a href="./src/openai/types/model_deleted.py">ModelDeleted</a></code>

# FineTuning

## Methods

Types:

```python
from openai.types.fine_tuning import (
    DpoHyperparameters,
    DpoMethod,
    ReinforcementHyperparameters,
    ReinforcementMethod,
    SupervisedHyperparameters,
    SupervisedMethod,
)
```

## Jobs

Types:

```python
from openai.types.fine_tuning import (
    FineTuningJob,
    FineTuningJobEvent,
    FineTuningJobWandbIntegration,
    FineTuningJobWandbIntegrationObject,
    FineTuningJobIntegration,
)
```

Methods:

- <code title="post /fine_tuning/jobs">client.fine_tuning.jobs.<a href="./src/openai/resources/fine_tuning/jobs/jobs.py">create</a>(\*\*<a href="src/openai/types/fine_tuning/job_create_params.py">params</a>) -> <a href="./src/openai/types/fine_tuning/fine_tuning_job.py">FineTuningJob</a></code>
- <code title="get /fine_tuning/jobs/{fine_tuning_job_id}">client.fine_tuning.jobs.<a href="./src/openai/resources/fine_tuning/jobs/jobs.py">retrieve</a>(fine_tuning_job_id) -> <a href="./src/openai/types/fine_tuning/fine_tuning_job.py">FineTuningJob</a></code>
- <code title="get /fine_tuning/jobs">client.fine_tuning.jobs.<a href="./src/openai/resources/fine_tuning/jobs/jobs.py">list</a>(\*\*<a href="src/openai/types/fine_tuning/job_list_params.py">params</a>) -> <a href="./src/openai/types/fine_tuning/fine_tuning_job.py">SyncCursorPage[FineTuningJob]</a></code>
- <code title="post /fine_tuning/jobs/{fine_tuning_job_id}/cancel">client.fine_tuning.jobs.<a href="./src/openai/resources/fine_tuning/jobs/jobs.py">cancel</a>(fine_tuning_job_id) -> <a href="./src/openai/types/fine_tuning/fine_tuning_job.py">FineTuningJob</a></code>
- <code title="get /fine_tuning/jobs/{fine_tuning_job_id}/events">client.fine_tuning.jobs.<a href="./src/openai/resources/fine_tuning/jobs/jobs.py">list_events</a>(fine_tuning_job_id, \*\*<a href="src/openai/types/fine_tuning/job_list_events_params.py">params</a>) -> <a href="./src/openai/types/fine_tuning/fine_tuning_job_event.py">SyncCursorPage[FineTuningJobEvent]</a></code>
- <code title="post /fine_tuning/jobs/{fine_tuning_job_id}/pause">client.fine_tuning.jobs.<a href="./src/openai/resources/fine_tuning/jobs/jobs.py">pause</a>(fine_tuning_job_id) -> <a href="./src/openai/types/fine_tuning/fine_tuning_job.py">FineTuningJob</a></code>
- <code title="post /fine_tuning/jobs/{fine_tuning_job_id}/resume">client.fine_tuning.jobs.<a href="./src/openai/resources/fine_tuning/jobs/jobs.py">resume</a>(fine_tuning_job_id) -> <a href="./src/openai/types/fine_tuning/fine_tuning_job.py">FineTuningJob</a></code>

### Checkpoints

Types:

```python
from openai.types.fine_tuning.jobs import FineTuningJobCheckpoint
```

Methods:

- <code title="get /fine_tuning/jobs/{fine_tuning_job_id}/checkpoints">client.fine_tuning.jobs.checkpoints.<a href="./src/openai/resources/fine_tuning/jobs/checkpoints.py">list</a>(fine_tuning_job_id, \*\*<a href="src/openai/types/fine_tuning/jobs/checkpoint_list_params.py">params</a>) -> <a href="./src/openai/types/fine_tuning/jobs/fine_tuning_job_checkpoint.py">SyncCursorPage[FineTuningJobCheckpoint]</a></code>

## Checkpoints

### Permissions

Types:

```python
from openai.types.fine_tuning.checkpoints import (
    PermissionCreateResponse,
    PermissionRetrieveResponse,
    PermissionDeleteResponse,
)
```

Methods:

- <code title="post /fine_tuning/checkpoints/{fine_tuned_model_checkpoint}/permissions">client.fine_tuning.checkpoints.permissions.<a href="./src/openai/resources/fine_tuning/checkpoints/permissions.py">create</a>(fine_tuned_model_checkpoint, \*\*<a href="src/openai/types/fine_tuning/checkpoints/permission_create_params.py">params</a>) -> <a href="./src/openai/types/fine_tuning/checkpoints/permission_create_response.py">SyncPage[PermissionCreateResponse]</a></code>
- <code title="get /fine_tuning/checkpoints/{fine_tuned_model_checkpoint}/permissions">client.fine_tuning.checkpoints.permissions.<a href="./src/openai/resources/fine_tuning/checkpoints/permissions.py">retrieve</a>(fine_tuned_model_checkpoint, \*\*<a href="src/openai/types/fine_tuning/checkpoints/permission_retrieve_params.py">params</a>) -> <a href="./src/openai/types/fine_tuning/checkpoints/permission_retrieve_response.py">PermissionRetrieveResponse</a></code>
- <code title="delete /fine_tuning/checkpoints/{fine_tuned_model_checkpoint}/permissions/{permission_id}">client.fine_tuning.checkpoints.permissions.<a href="./src/openai/resources/fine_tuning/checkpoints/permissions.py">delete</a>(permission_id, \*, fine_tuned_model_checkpoint) -> <a href="./src/openai/types/fine_tuning/checkpoints/permission_delete_response.py">PermissionDeleteResponse</a></code>

## Alpha

### Graders

Types:

```python
from openai.types.fine_tuning.alpha import GraderRunResponse, GraderValidateResponse
```

Methods:

- <code title="post /fine_tuning/alpha/graders/run">client.fine_tuning.alpha.graders.<a href="./src/openai/resources/fine_tuning/alpha/graders.py">run</a>(\*\*<a href="src/openai/types/fine_tuning/alpha/grader_run_params.py">params</a>) -> <a href="./src/openai/types/fine_tuning/alpha/grader_run_response.py">GraderRunResponse</a></code>
- <code title="post /fine_tuning/alpha/graders/validate">client.fine_tuning.alpha.graders.<a href="./src/openai/resources/fine_tuning/alpha/graders.py">validate</a>(\*\*<a href="src/openai/types/fine_tuning/alpha/grader_validate_params.py">params</a>) -> <a href="./src/openai/types/fine_tuning/alpha/grader_validate_response.py">GraderValidateResponse</a></code>

# Graders

## GraderModels

Types:

```python
from openai.types.graders import (
    GraderInputs,
    LabelModelGrader,
    MultiGrader,
    PythonGrader,
    ScoreModelGrader,
    StringCheckGrader,
    TextSimilarityGrader,
)
```

# VectorStores

Types:

```python
from openai.types import (
    AutoFileChunkingStrategyParam,
    FileChunkingStrategy,
    FileChunkingStrategyParam,
    OtherFileChunkingStrategyObject,
    StaticFileChunkingStrategy,
    StaticFileChunkingStrategyObject,
    StaticFileChunkingStrategyObjectParam,
    VectorStore,
    VectorStoreDeleted,
    VectorStoreSearchResponse,
)
```

Methods:

- <code title="post /vector_stores">client.vector_stores.<a href="./src/openai/resources/vector_stores/vector_stores.py">create</a>(\*\*<a href="src/openai/types/vector_store_create_params.py">params</a>) -> <a href="./src/openai/types/vector_store.py">VectorStore</a></code>
- <code title="get /vector_stores/{vector_store_id}">client.vector_stores.<a href="./src/openai/resources/vector_stores/vector_stores.py">retrieve</a>(vector_store_id) -> <a href="./src/openai/types/vector_store.py">VectorStore</a></code>
- <code title="post /vector_stores/{vector_store_id}">client.vector_stores.<a href="./src/openai/resources/vector_stores/vector_stores.py">update</a>(vector_store_id, \*\*<a href="src/openai/types/vector_store_update_params.py">params</a>) -> <a href="./src/openai/types/vector_store.py">VectorStore</a></code>
- <code title="get /vector_stores">client.vector_stores.<a href="./src/openai/resources/vector_stores/vector_stores.py">list</a>(\*\*<a href="src/openai/types/vector_store_list_params.py">params</a>) -> <a href="./src/openai/types/vector_store.py">SyncCursorPage[VectorStore]</a></code>
- <code title="delete /vector_stores/{vector_store_id}">client.vector_stores.<a href="./src/openai/resources/vector_stores/vector_stores.py">delete</a>(vector_store_id) -> <a href="./src/openai/types/vector_store_deleted.py">VectorStoreDeleted</a></code>
- <code title="post /vector_stores/{vector_store_id}/search">client.vector_stores.<a href="./src/openai/resources/vector_stores/vector_stores.py">search</a>(vector_store_id, \*\*<a href="src/openai/types/vector_store_search_params.py">params</a>) -> <a href="./src/openai/types/vector_store_search_response.py">SyncPage[VectorStoreSearchResponse]</a></code>

## Files

Types:

```python
from openai.types.vector_stores import VectorStoreFile, VectorStoreFileDeleted, FileContentResponse
```

Methods:

- <code title="post /vector_stores/{vector_store_id}/files">client.vector_stores.files.<a href="./src/openai/resources/vector_stores/files.py">create</a>(vector_store_id, \*\*<a href="src/openai/types/vector_stores/file_create_params.py">params</a>) -> <a href="./src/openai/types/vector_stores/vector_store_file.py">VectorStoreFile</a></code>
- <code title="get /vector_stores/{vector_store_id}/files/{file_id}">client.vector_stores.files.<a href="./src/openai/resources/vector_stores/files.py">retrieve</a>(file_id, \*, vector_store_id) -> <a href="./src/openai/types/vector_stores/vector_store_file.py">VectorStoreFile</a></code>
- <code title="post /vector_stores/{vector_store_id}/files/{file_id}">client.vector_stores.files.<a href="./src/openai/resources/vector_stores/files.py">update</a>(file_id, \*, vector_store_id, \*\*<a href="src/openai/types/vector_stores/file_update_params.py">params</a>) -> <a href="./src/openai/types/vector_stores/vector_store_file.py">VectorStoreFile</a></code>
- <code title="get /vector_stores/{vector_store_id}/files">client.vector_stores.files.<a href="./src/openai/resources/vector_stores/files.py">list</a>(vector_store_id, \*\*<a href="src/openai/types/vector_stores/file_list_params.py">params</a>) -> <a href="./src/openai/types/vector_stores/vector_store_file.py">SyncCursorPage[VectorStoreFile]</a></code>
- <code title="delete /vector_stores/{vector_store_id}/files/{file_id}">client.vector_stores.files.<a href="./src/openai/resources/vector_stores/files.py">delete</a>(file_id, \*, vector_store_id) -> <a href="./src/openai/types/vector_stores/vector_store_file_deleted.py">VectorStoreFileDeleted</a></code>
- <code title="get /vector_stores/{vector_store_id}/files/{file_id}/content">client.vector_stores.files.<a href="./src/openai/resources/vector_stores/files.py">content</a>(file_id, \*, vector_store_id) -> <a href="./src/openai/types/vector_stores/file_content_response.py">SyncPage[FileContentResponse]</a></code>
- <code>client.vector_stores.files.<a href="./src/openai/resources/vector_stores/files.py">create_and_poll</a>(\*args) -> VectorStoreFile</code>
- <code>client.vector_stores.files.<a href="./src/openai/resources/vector_stores/files.py">poll</a>(\*args) -> VectorStoreFile</code>
- <code>client.vector_stores.files.<a href="./src/openai/resources/vector_stores/files.py">upload</a>(\*args) -> VectorStoreFile</code>
- <code>client.vector_stores.files.<a href="./src/openai/resources/vector_stores/files.py">upload_and_poll</a>(\*args) -> VectorStoreFile</code>

## FileBatches

Types:

```python
from openai.types.vector_stores import VectorStoreFileBatch
```

Methods:

- <code title="post /vector_stores/{vector_store_id}/file_batches">client.vector_stores.file_batches.<a href="./src/openai/resources/vector_stores/file_batches.py">create</a>(vector_store_id, \*\*<a href="src/openai/types/vector_stores/file_batch_create_params.py">params</a>) -> <a href="./src/openai/types/vector_stores/vector_store_file_batch.py">VectorStoreFileBatch</a></code>
- <code title="get /vector_stores/{vector_store_id}/file_batches/{batch_id}">client.vector_stores.file_batches.<a href="./src/openai/resources/vector_stores/file_batches.py">retrieve</a>(batch_id, \*, vector_store_id) -> <a href="./src/openai/types/vector_stores/vector_store_file_batch.py">VectorStoreFileBatch</a></code>
- <code title="post /vector_stores/{vector_store_id}/file_batches/{batch_id}/cancel">client.vector_stores.file_batches.<a href="./src/openai/resources/vector_stores/file_batches.py">cancel</a>(batch_id, \*, vector_store_id) -> <a href="./src/openai/types/vector_stores/vector_store_file_batch.py">VectorStoreFileBatch</a></code>
- <code title="get /vector_stores/{vector_store_id}/file_batches/{batch_id}/files">client.vector_stores.file_batches.<a href="./src/openai/resources/vector_stores/file_batches.py">list_files</a>(batch_id, \*, vector_store_id, \*\*<a href="src/openai/types/vector_stores/file_batch_list_files_params.py">params</a>) -> <a href="./src/openai/types/vector_stores/vector_store_file.py">SyncCursorPage[VectorStoreFile]</a></code>
- <code>client.vector_stores.file_batches.<a href="./src/openai/resources/vector_stores/file_batches.py">create_and_poll</a>(\*args) -> VectorStoreFileBatch</code>
- <code>client.vector_stores.file_batches.<a href="./src/openai/resources/vector_stores/file_batches.py">poll</a>(\*args) -> VectorStoreFileBatch</code>
- <code>client.vector_stores.file_batches.<a href="./src/openai/resources/vector_stores/file_batches.py">upload_and_poll</a>(\*args) -> VectorStoreFileBatch</code>

# Webhooks

Types:

```python
from openai.types.webhooks import (
    BatchCancelledWebhookEvent,
    BatchCompletedWebhookEvent,
    BatchExpiredWebhookEvent,
    BatchFailedWebhookEvent,
    EvalRunCanceledWebhookEvent,
    EvalRunFailedWebhookEvent,
    EvalRunSucceededWebhookEvent,
    FineTuningJobCancelledWebhookEvent,
    FineTuningJobFailedWebhookEvent,
    FineTuningJobSucceededWebhookEvent,
    RealtimeCallIncomingWebhookEvent,
    ResponseCancelledWebhookEvent,
    ResponseCompletedWebhookEvent,
    ResponseFailedWebhookEvent,
    ResponseIncompleteWebhookEvent,
    UnwrapWebhookEvent,
)
```

Methods:

- <code>client.webhooks.<a href="./src/openai/resources/webhooks.py">unwrap</a>(payload, headers, \*, secret) -> UnwrapWebhookEvent</code>
- <code>client.webhooks.<a href="./src/openai/resources/webhooks.py">verify_signature</a>(payload, headers, \*, secret, tolerance) -> None</code>

# Beta

## Realtime

Types:

```python
from openai.types.beta.realtime import (
    ConversationCreatedEvent,
    ConversationItem,
    ConversationItemContent,
    ConversationItemCreateEvent,
    ConversationItemCreatedEvent,
    ConversationItemDeleteEvent,
    ConversationItemDeletedEvent,
    ConversationItemInputAudioTranscriptionCompletedEvent,
    ConversationItemInputAudioTranscriptionDeltaEvent,
    ConversationItemInputAudioTranscriptionFailedEvent,
    ConversationItemRetrieveEvent,
    ConversationItemTruncateEvent,
    ConversationItemTruncatedEvent,
    ConversationItemWithReference,
    ErrorEvent,
    InputAudioBufferAppendEvent,
    InputAudioBufferClearEvent,
    InputAudioBufferClearedEvent,
    InputAudioBufferCommitEvent,
    InputAudioBufferCommittedEvent,
    InputAudioBufferSpeechStartedEvent,
    InputAudioBufferSpeechStoppedEvent,
    RateLimitsUpdatedEvent,
    RealtimeClientEvent,
    RealtimeResponse,
    RealtimeResponseStatus,
    RealtimeResponseUsage,
    RealtimeServerEvent,
    ResponseAudioDeltaEvent,
    ResponseAudioDoneEvent,
    ResponseAudioTranscriptDeltaEvent,
    ResponseAudioTranscriptDoneEvent,
    ResponseCancelEvent,
    ResponseContentPartAddedEvent,
    ResponseContentPartDoneEvent,
    ResponseCreateEvent,
    ResponseCreatedEvent,
    ResponseDoneEvent,
    ResponseFunctionCallArgumentsDeltaEvent,
    ResponseFunctionCallArgumentsDoneEvent,
    ResponseOutputItemAddedEvent,
    ResponseOutputItemDoneEvent,
    ResponseTextDeltaEvent,
    ResponseTextDoneEvent,
    SessionCreatedEvent,
    SessionUpdateEvent,
    SessionUpdatedEvent,
    TranscriptionSessionUpdate,
    TranscriptionSessionUpdatedEvent,
)
```

### Sessions

Types:

```python
from openai.types.beta.realtime import Session, SessionCreateResponse
```

Methods:

- <code title="post /realtime/sessions">client.beta.realtime.sessions.<a href="./src/openai/resources/beta/realtime/sessions.py">create</a>(\*\*<a href="src/openai/types/beta/realtime/session_create_params.py">params</a>) -> <a href="./src/openai/types/beta/realtime/session_create_response.py">SessionCreateResponse</a></code>

### TranscriptionSessions

Types:

```python
from openai.types.beta.realtime import TranscriptionSession
```

Methods:

- <code title="post /realtime/transcription_sessions">client.beta.realtime.transcription_sessions.<a href="./src/openai/resources/beta/realtime/transcription_sessions.py">create</a>(\*\*<a href="src/openai/types/beta/realtime/transcription_session_create_params.py">params</a>) -> <a href="./src/openai/types/beta/realtime/transcription_session.py">TranscriptionSession</a></code>

## Assistants

Types:

```python
from openai.types.beta import (
    Assistant,
    AssistantDeleted,
    AssistantStreamEvent,
    AssistantTool,
    CodeInterpreterTool,
    FileSearchTool,
    FunctionTool,
    MessageStreamEvent,
    RunStepStreamEvent,
    RunStreamEvent,
    ThreadStreamEvent,
)
```

Methods:

- <code title="post /assistants">client.beta.assistants.<a href="./src/openai/resources/beta/assistants.py">create</a>(\*\*<a href="src/openai/types/beta/assistant_create_params.py">params</a>) -> <a href="./src/openai/types/beta/assistant.py">Assistant</a></code>
- <code title="get /assistants/{assistant_id}">client.beta.assistants.<a href="./src/openai/resources/beta/assistants.py">retrieve</a>(assistant_id) -> <a href="./src/openai/types/beta/assistant.py">Assistant</a></code>
- <code title="post /assistants/{assistant_id}">client.beta.assistants.<a href="./src/openai/resources/beta/assistants.py">update</a>(assistant_id, \*\*<a href="src/openai/types/beta/assistant_update_params.py">params</a>) -> <a href="./src/openai/types/beta/assistant.py">Assistant</a></code>
- <code title="get /assistants">client.beta.assistants.<a href="./src/openai/resources/beta/assistants.py">list</a>(\*\*<a href="src/openai/types/beta/assistant_list_params.py">params</a>) -> <a href="./src/openai/types/beta/assistant.py">SyncCursorPage[Assistant]</a></code>
- <code title="delete /assistants/{assistant_id}">client.beta.assistants.<a href="./src/openai/resources/beta/assistants.py">delete</a>(assistant_id) -> <a href="./src/openai/types/beta/assistant_deleted.py">AssistantDeleted</a></code>

## Threads

Types:

```python
from openai.types.beta import (
    AssistantResponseFormatOption,
    AssistantToolChoice,
    AssistantToolChoiceFunction,
    AssistantToolChoiceOption,
    Thread,
    ThreadDeleted,
)
```

Methods:

- <code title="post /threads">client.beta.threads.<a href="./src/openai/resources/beta/threads/threads.py">create</a>(\*\*<a href="src/openai/types/beta/thread_create_params.py">params</a>) -> <a href="./src/openai/types/beta/thread.py">Thread</a></code>
- <code title="get /threads/{thread_id}">client.beta.threads.<a href="./src/openai/resources/beta/threads/threads.py">retrieve</a>(thread_id) -> <a href="./src/openai/types/beta/thread.py">Thread</a></code>
- <code title="post /threads/{thread_id}">client.beta.threads.<a href="./src/openai/resources/beta/threads/threads.py">update</a>(thread_id, \*\*<a href="src/openai/types/beta/thread_update_params.py">params</a>) -> <a href="./src/openai/types/beta/thread.py">Thread</a></code>
- <code title="delete /threads/{thread_id}">client.beta.threads.<a href="./src/openai/resources/beta/threads/threads.py">delete</a>(thread_id) -> <a href="./src/openai/types/beta/thread_deleted.py">ThreadDeleted</a></code>
- <code title="post /threads/runs">client.beta.threads.<a href="./src/openai/resources/beta/threads/threads.py">create_and_run</a>(\*\*<a href="src/openai/types/beta/thread_create_and_run_params.py">params</a>) -> <a href="./src/openai/types/beta/threads/run.py">Run</a></code>
- <code>client.beta.threads.<a href="./src/openai/resources/beta/threads/threads.py">create_and_run_poll</a>(\*args) -> Run</code>
- <code>client.beta.threads.<a href="./src/openai/resources/beta/threads/threads.py">create_and_run_stream</a>(\*args) -> AssistantStreamManager[AssistantEventHandler] | AssistantStreamManager[AssistantEventHandlerT]</code>

### Runs

Types:

```python
from openai.types.beta.threads import RequiredActionFunctionToolCall, Run, RunStatus
```

Methods:

- <code title="post /threads/{thread_id}/runs">client.beta.threads.runs.<a href="./src/openai/resources/beta/threads/runs/runs.py">create</a>(thread_id, \*\*<a href="src/openai/types/beta/threads/run_create_params.py">params</a>) -> <a href="./src/openai/types/beta/threads/run.py">Run</a></code>
- <code title="get /threads/{thread_id}/runs/{run_id}">client.beta.threads.runs.<a href="./src/openai/resources/beta/threads/runs/runs.py">retrieve</a>(run_id, \*, thread_id) -> <a href="./src/openai/types/beta/threads/run.py">Run</a></code>
- <code title="post /threads/{thread_id}/runs/{run_id}">client.beta.threads.runs.<a href="./src/openai/resources/beta/threads/runs/runs.py">update</a>(run_id, \*, thread_id, \*\*<a href="src/openai/types/beta/threads/run_update_params.py">params</a>) -> <a href="./src/openai/types/beta/threads/run.py">Run</a></code>
- <code title="get /threads/{thread_id}/runs">client.beta.threads.runs.<a href="./src/openai/resources/beta/threads/runs/runs.py">list</a>(thread_id, \*\*<a href="src/openai/types/beta/threads/run_list_params.py">params</a>) -> <a href="./src/openai/types/beta/threads/run.py">SyncCursorPage[Run]</a></code>
- <code title="post /threads/{thread_id}/runs/{run_id}/cancel">client.beta.threads.runs.<a href="./src/openai/resources/beta/threads/runs/runs.py">cancel</a>(run_id, \*, thread_id) -> <a href="./src/openai/types/beta/threads/run.py">Run</a></code>
- <code title="post /threads/{thread_id}/runs/{run_id}/submit_tool_outputs">client.beta.threads.runs.<a href="./src/openai/resources/beta/threads/runs/runs.py">submit_tool_outputs</a>(run_id, \*, thread_id, \*\*<a href="src/openai/types/beta/threads/run_submit_tool_outputs_params.py">params</a>) -> <a href="./src/openai/types/beta/threads/run.py">Run</a></code>
- <code>client.beta.threads.runs.<a href="./src/openai/resources/beta/threads/runs/runs.py">create_and_poll</a>(\*args) -> Run</code>
- <code>client.beta.threads.runs.<a href="./src/openai/resources/beta/threads/runs/runs.py">create_and_stream</a>(\*args) -> AssistantStreamManager[AssistantEventHandler] | AssistantStreamManager[AssistantEventHandlerT]</code>
- <code>client.beta.threads.runs.<a href="./src/openai/resources/beta/threads/runs/runs.py">poll</a>(\*args) -> Run</code>
- <code>client.beta.threads.runs.<a href="./src/openai/resources/beta/threads/runs/runs.py">stream</a>(\*args) -> AssistantStreamManager[AssistantEventHandler] | AssistantStreamManager[AssistantEventHandlerT]</code>
- <code>client.beta.threads.runs.<a href="./src/openai/resources/beta/threads/runs/runs.py">submit_tool_outputs_and_poll</a>(\*args) -> Run</code>
- <code>client.beta.threads.runs.<a href="./src/openai/resources/beta/threads/runs/runs.py">submit_tool_outputs_stream</a>(\*args) -> AssistantStreamManager[AssistantEventHandler] | AssistantStreamManager[AssistantEventHandlerT]</code>

#### Steps

Types:

```python
from openai.types.beta.threads.runs import (
    CodeInterpreterLogs,
    CodeInterpreterOutputImage,
    CodeInterpreterToolCall,
    CodeInterpreterToolCallDelta,
    FileSearchToolCall,
    FileSearchToolCallDelta,
    FunctionToolCall,
    FunctionToolCallDelta,
    MessageCreationStepDetails,
    RunStep,
    RunStepDelta,
    RunStepDeltaEvent,
    RunStepDeltaMessageDelta,
    RunStepInclude,
    ToolCall,
    ToolCallDelta,
    ToolCallDeltaObject,
    ToolCallsStepDetails,
)
```

Methods:

- <code title="get /threads/{thread_id}/runs/{run_id}/steps/{step_id}">client.beta.threads.runs.steps.<a href="./src/openai/resources/beta/threads/runs/steps.py">retrieve</a>(step_id, \*, thread_id, run_id, \*\*<a href="src/openai/types/beta/threads/runs/step_retrieve_params.py">params</a>) -> <a href="./src/openai/types/beta/threads/runs/run_step.py">RunStep</a></code>
- <code title="get /threads/{thread_id}/runs/{run_id}/steps">client.beta.threads.runs.steps.<a href="./src/openai/resources/beta/threads/runs/steps.py">list</a>(run_id, \*, thread_id, \*\*<a href="src/openai/types/beta/threads/runs/step_list_params.py">params</a>) -> <a href="./src/openai/types/beta/threads/runs/run_step.py">SyncCursorPage[RunStep]</a></code>

### Messages

Types:

```python
from openai.types.beta.threads import (
    Annotation,
    AnnotationDelta,
    FileCitationAnnotation,
    FileCitationDeltaAnnotation,
    FilePathAnnotation,
    FilePathDeltaAnnotation,
    ImageFile,
    ImageFileContentBlock,
    ImageFileDelta,
    ImageFileDeltaBlock,
    ImageURL,
    ImageURLContentBlock,
    ImageURLDelta,
    ImageURLDeltaBlock,
    Message,
    MessageContent,
    MessageContentDelta,
    MessageContentPartParam,
    MessageDeleted,
    MessageDelta,
    MessageDeltaEvent,
    RefusalContentBlock,
    RefusalDeltaBlock,
    Text,
    TextContentBlock,
    TextContentBlockParam,
    TextDelta,
    TextDeltaBlock,
)
```

Methods:

- <code title="post /threads/{thread_id}/messages">client.beta.threads.messages.<a href="./src/openai/resources/beta/threads/messages.py">create</a>(thread_id, \*\*<a href="src/openai/types/beta/threads/message_create_params.py">params</a>) -> <a href="./src/openai/types/beta/threads/message.py">Message</a></code>
- <code title="get /threads/{thread_id}/messages/{message_id}">client.beta.threads.messages.<a href="./src/openai/resources/beta/threads/messages.py">retrieve</a>(message_id, \*, thread_id) -> <a href="./src/openai/types/beta/threads/message.py">Message</a></code>
- <code title="post /threads/{thread_id}/messages/{message_id}">client.beta.threads.messages.<a href="./src/openai/resources/beta/threads/messages.py">update</a>(message_id, \*, thread_id, \*\*<a href="src/openai/types/beta/threads/message_update_params.py">params</a>) -> <a href="./src/openai/types/beta/threads/message.py">Message</a></code>
- <code title="get /threads/{thread_id}/messages">client.beta.threads.messages.<a href="./src/openai/resources/beta/threads/messages.py">list</a>(thread_id, \*\*<a href="src/openai/types/beta/threads/message_list_params.py">params</a>) -> <a href="./src/openai/types/beta/threads/message.py">SyncCursorPage[Message]</a></code>
- <code title="delete /threads/{thread_id}/messages/{message_id}">client.beta.threads.messages.<a href="./src/openai/resources/beta/threads/messages.py">delete</a>(message_id, \*, thread_id) -> <a href="./src/openai/types/beta/threads/message_deleted.py">MessageDeleted</a></code>

# Batches

Types:

```python
from openai.types import Batch, BatchError, BatchRequestCounts, BatchUsage
```

Methods:

- <code title="post /batches">client.batches.<a href="./src/openai/resources/batches.py">create</a>(\*\*<a href="src/openai/types/batch_create_params.py">params</a>) -> <a href="./src/openai/types/batch.py">Batch</a></code>
- <code title="get /batches/{batch_id}">client.batches.<a href="./src/openai/resources/batches.py">retrieve</a>(batch_id) -> <a href="./src/openai/types/batch.py">Batch</a></code>
- <code title="get /batches">client.batches.<a href="./src/openai/resources/batches.py">list</a>(\*\*<a href="src/openai/types/batch_list_params.py">params</a>) -> <a href="./src/openai/types/batch.py">SyncCursorPage[Batch]</a></code>
- <code title="post /batches/{batch_id}/cancel">client.batches.<a href="./src/openai/resources/batches.py">cancel</a>(batch_id) -> <a href="./src/openai/types/batch.py">Batch</a></code>

# Uploads

Types:

```python
from openai.types import Upload
```

Methods:

- <code title="post /uploads">client.uploads.<a href="./src/openai/resources/uploads/uploads.py">create</a>(\*\*<a href="src/openai/types/upload_create_params.py">params</a>) -> <a href="./src/openai/types/upload.py">Upload</a></code>
- <code title="post /uploads/{upload_id}/cancel">client.uploads.<a href="./src/openai/resources/uploads/uploads.py">cancel</a>(upload_id) -> <a href="./src/openai/types/upload.py">Upload</a></code>
- <code title="post /uploads/{upload_id}/complete">client.uploads.<a href="./src/openai/resources/uploads/uploads.py">complete</a>(upload_id, \*\*<a href="src/openai/types/upload_complete_params.py">params</a>) -> <a href="./src/openai/types/upload.py">Upload</a></code>

## Parts

Types:

```python
from openai.types.uploads import UploadPart
```

Methods:

- <code title="post /uploads/{upload_id}/parts">client.uploads.parts.<a href="./src/openai/resources/uploads/parts.py">create</a>(upload_id, \*\*<a href="src/openai/types/uploads/part_create_params.py">params</a>) -> <a href="./src/openai/types/uploads/upload_part.py">UploadPart</a></code>

# Responses

Types:

```python
from openai.types.responses import (
    ApplyPatchTool,
    CompactedResponse,
    ComputerTool,
    CustomTool,
    EasyInputMessage,
    FileSearchTool,
    FunctionShellTool,
    FunctionTool,
    Response,
    ResponseApplyPatchToolCall,
    ResponseApplyPatchToolCallOutput,
    ResponseAudioDeltaEvent,
    ResponseAudioDoneEvent,
    ResponseAudioTranscriptDeltaEvent,
    ResponseAudioTranscriptDoneEvent,
    ResponseCodeInterpreterCallCodeDeltaEvent,
    ResponseCodeInterpreterCallCodeDoneEvent,
    ResponseCodeInterpreterCallCompletedEvent,
    ResponseCodeInterpreterCallInProgressEvent,
    ResponseCodeInterpreterCallInterpretingEvent,
    ResponseCodeInterpreterToolCall,
    ResponseCompactionItem,
    ResponseCompactionItemParam,
    ResponseCompletedEvent,
    ResponseComputerToolCall,
    ResponseComputerToolCallOutputItem,
    ResponseComputerToolCallOutputScreenshot,
    ResponseContent,
    ResponseContentPartAddedEvent,
    ResponseContentPartDoneEvent,
    ResponseConversationParam,
    ResponseCreatedEvent,
    ResponseCustomToolCall,
    ResponseCustomToolCallInputDeltaEvent,
    ResponseCustomToolCallInputDoneEvent,
    ResponseCustomToolCallOutput,
    ResponseError,
    ResponseErrorEvent,
    ResponseFailedEvent,
    ResponseFileSearchCallCompletedEvent,
    ResponseFileSearchCallInProgressEvent,
    ResponseFileSearchCallSearchingEvent,
    ResponseFileSearchToolCall,
    ResponseFormatTextConfig,
    ResponseFormatTextJSONSchemaConfig,
    ResponseFunctionCallArgumentsDeltaEvent,
    ResponseFunctionCallArgumentsDoneEvent,
    ResponseFunctionCallOutputItem,
    ResponseFunctionCallOutputItemList,
    ResponseFunctionShellCallOutputContent,
    ResponseFunctionShellToolCall,
    ResponseFunctionShellToolCallOutput,
    ResponseFunctionToolCall,
    ResponseFunctionToolCallItem,
    ResponseFunctionToolCallOutputItem,
    ResponseFunctionWebSearch,
    ResponseImageGenCallCompletedEvent,
    ResponseImageGenCallGeneratingEvent,
    ResponseImageGenCallInProgressEvent,
    ResponseImageGenCallPartialImageEvent,
    ResponseInProgressEvent,
    ResponseIncludable,
    ResponseIncompleteEvent,
    ResponseInput,
    ResponseInputAudio,
    ResponseInputContent,
    ResponseInputFile,
    ResponseInputFileContent,
    ResponseInputImage,
    ResponseInputImageContent,
    ResponseInputItem,
    ResponseInputMessageContentList,
    ResponseInputMessageItem,
    ResponseInputText,
    ResponseInputTextContent,
    ResponseItem,
    ResponseMcpCallArgumentsDeltaEvent,
    ResponseMcpCallArgumentsDoneEvent,
    ResponseMcpCallCompletedEvent,
    ResponseMcpCallFailedEvent,
    ResponseMcpCallInProgressEvent,
    ResponseMcpListToolsCompletedEvent,
    ResponseMcpListToolsFailedEvent,
    ResponseMcpListToolsInProgressEvent,
    ResponseOutputAudio,
    ResponseOutputItem,
    ResponseOutputItemAddedEvent,
    ResponseOutputItemDoneEvent,
    ResponseOutputMessage,
    ResponseOutputRefusal,
    ResponseOutputText,
    ResponseOutputTextAnnotationAddedEvent,
    ResponsePrompt,
    ResponseQueuedEvent,
    ResponseReasoningItem,
    ResponseReasoningSummaryPartAddedEvent,
    ResponseReasoningSummaryPartDoneEvent,
    ResponseReasoningSummaryTextDeltaEvent,
    ResponseReasoningSummaryTextDoneEvent,
    ResponseReasoningTextDeltaEvent,
    ResponseReasoningTextDoneEvent,
    ResponseRefusalDeltaEvent,
    ResponseRefusalDoneEvent,
    ResponseStatus,
    ResponseStreamEvent,
    ResponseTextConfig,
    ResponseTextDeltaEvent,
    ResponseTextDoneEvent,
    ResponseUsage,
    ResponseWebSearchCallCompletedEvent,
    ResponseWebSearchCallInProgressEvent,
    ResponseWebSearchCallSearchingEvent,
    Tool,
    ToolChoiceAllowed,
    ToolChoiceApplyPatch,
    ToolChoiceCustom,
    ToolChoiceFunction,
    ToolChoiceMcp,
    ToolChoiceOptions,
    ToolChoiceShell,
    ToolChoiceTypes,
    WebSearchPreviewTool,
    WebSearchTool,
)
```

Methods:

- <code title="post /responses">client.responses.<a href="./src/openai/resources/responses/responses.py">create</a>(\*\*<a href="src/openai/types/responses/response_create_params.py">params</a>) -> <a href="./src/openai/types/responses/response.py">Response</a></code>
- <code title="get /responses/{response_id}">client.responses.<a href="./src/openai/resources/responses/responses.py">retrieve</a>(response_id, \*\*<a href="src/openai/types/responses/response_retrieve_params.py">params</a>) -> <a href="./src/openai/types/responses/response.py">Response</a></code>
- <code title="delete /responses/{response_id}">client.responses.<a href="./src/openai/resources/responses/responses.py">delete</a>(response_id) -> None</code>
- <code title="post /responses/{response_id}/cancel">client.responses.<a href="./src/openai/resources/responses/responses.py">cancel</a>(response_id) -> <a href="./src/openai/types/responses/response.py">Response</a></code>
- <code title="post /responses/compact">client.responses.<a href="./src/openai/resources/responses/responses.py">compact</a>(\*\*<a href="src/openai/types/responses/response_compact_params.py">params</a>) -> <a href="./src/openai/types/responses/compacted_response.py">CompactedResponse</a></code>

## InputItems

Types:

```python
from openai.types.responses import ResponseItemList
```

Methods:

- <code title="get /responses/{response_id}/input_items">client.responses.input_items.<a href="./src/openai/resources/responses/input_items.py">list</a>(response_id, \*\*<a href="src/openai/types/responses/input_item_list_params.py">params</a>) -> <a href="./src/openai/types/responses/response_item.py">SyncCursorPage[ResponseItem]</a></code>

## InputTokens

Types:

```python
from openai.types.responses import InputTokenCountResponse
```

Methods:

- <code title="post /responses/input_tokens">client.responses.input_tokens.<a href="./src/openai/resources/responses/input_tokens.py">count</a>(\*\*<a href="src/openai/types/responses/input_token_count_params.py">params</a>) -> <a href="./src/openai/types/responses/input_token_count_response.py">InputTokenCountResponse</a></code>

# Realtime

Types:

```python
from openai.types.realtime import (
    AudioTranscription,
    ConversationCreatedEvent,
    ConversationItem,
    ConversationItemAdded,
    ConversationItemCreateEvent,
    ConversationItemCreatedEvent,
    ConversationItemDeleteEvent,
    ConversationItemDeletedEvent,
    ConversationItemDone,
    ConversationItemInputAudioTranscriptionCompletedEvent,
    ConversationItemInputAudioTranscriptionDeltaEvent,
    ConversationItemInputAudioTranscriptionFailedEvent,
    ConversationItemInputAudioTranscriptionSegment,
    ConversationItemRetrieveEvent,
    ConversationItemTruncateEvent,
    ConversationItemTruncatedEvent,
    ConversationItemWithReference,
    InputAudioBufferAppendEvent,
    InputAudioBufferClearEvent,
    InputAudioBufferClearedEvent,
    InputAudioBufferCommitEvent,
    InputAudioBufferCommittedEvent,
    InputAudioBufferDtmfEventReceivedEvent,
    InputAudioBufferSpeechStartedEvent,
    InputAudioBufferSpeechStoppedEvent,
    InputAudioBufferTimeoutTriggered,
    LogProbProperties,
    McpListToolsCompleted,
    McpListToolsFailed,
    McpListToolsInProgress,
    NoiseReductionType,
    OutputAudioBufferClearEvent,
    RateLimitsUpdatedEvent,
    RealtimeAudioConfig,
    RealtimeAudioConfigInput,
    RealtimeAudioConfigOutput,
    RealtimeAudioFormats,
    RealtimeAudioInputTurnDetection,
    RealtimeClientEvent,
    RealtimeConversationItemAssistantMessage,
    RealtimeConversationItemFunctionCall,
    RealtimeConversationItemFunctionCallOutput,
    RealtimeConversationItemSystemMessage,
    RealtimeConversationItemUserMessage,
    RealtimeError,
    RealtimeErrorEvent,
    RealtimeFunctionTool,
    RealtimeMcpApprovalRequest,
    RealtimeMcpApprovalResponse,
    RealtimeMcpListTools,
    RealtimeMcpProtocolError,
    RealtimeMcpToolCall,
    RealtimeMcpToolExecutionError,
    RealtimeMcphttpError,
    RealtimeResponse,
    RealtimeResponseCreateAudioOutput,
    RealtimeResponseCreateMcpTool,
    RealtimeResponseCreateParams,
    RealtimeResponseStatus,
    RealtimeResponseUsage,
    RealtimeResponseUsageInputTokenDetails,
    RealtimeResponseUsageOutputTokenDetails,
    RealtimeServerEvent,
    RealtimeSession,
    RealtimeSessionCreateRequest,
    RealtimeToolChoiceConfig,
    RealtimeToolsConfig,
    RealtimeToolsConfigUnion,
    RealtimeTracingConfig,
    RealtimeTranscriptionSessionAudio,
    RealtimeTranscriptionSessionAudioInput,
    RealtimeTranscriptionSessionAudioInputTurnDetection,
    RealtimeTranscriptionSessionCreateRequest,
    RealtimeTruncation,
    RealtimeTruncationRetentionRatio,
    ResponseAudioDeltaEvent,
    ResponseAudioDoneEvent,
    ResponseAudioTranscriptDeltaEvent,
    ResponseAudioTranscriptDoneEvent,
    ResponseCancelEvent,
    ResponseContentPartAddedEvent,
    ResponseContentPartDoneEvent,
    ResponseCreateEvent,
    ResponseCreatedEvent,
    ResponseDoneEvent,
    ResponseFunctionCallArgumentsDeltaEvent,
    ResponseFunctionCallArgumentsDoneEvent,
    ResponseMcpCallArgumentsDelta,
    ResponseMcpCallArgumentsDone,
    ResponseMcpCallCompleted,
    ResponseMcpCallFailed,
    ResponseMcpCallInProgress,
    ResponseOutputItemAddedEvent,
    ResponseOutputItemDoneEvent,
    ResponseTextDeltaEvent,
    ResponseTextDoneEvent,
    SessionCreatedEvent,
    SessionUpdateEvent,
    SessionUpdatedEvent,
    TranscriptionSessionUpdate,
    TranscriptionSessionUpdatedEvent,
)
```

## ClientSecrets

Types:

```python
from openai.types.realtime import (
    RealtimeSessionClientSecret,
    RealtimeSessionCreateResponse,
    RealtimeTranscriptionSessionCreateResponse,
    RealtimeTranscriptionSessionTurnDetection,
    ClientSecretCreateResponse,
)
```

Methods:

- <code title="post /realtime/client_secrets">client.realtime.client_secrets.<a href="./src/openai/resources/realtime/client_secrets.py">create</a>(\*\*<a href="src/openai/types/realtime/client_secret_create_params.py">params</a>) -> <a href="./src/openai/types/realtime/client_secret_create_response.py">ClientSecretCreateResponse</a></code>

## Calls

Methods:

- <code title="post /realtime/calls">client.realtime.calls.<a href="./src/openai/resources/realtime/calls.py">create</a>(\*\*<a href="src/openai/types/realtime/call_create_params.py">params</a>) -> HttpxBinaryResponseContent</code>
- <code title="post /realtime/calls/{call_id}/accept">client.realtime.calls.<a href="./src/openai/resources/realtime/calls.py">accept</a>(call_id, \*\*<a href="src/openai/types/realtime/call_accept_params.py">params</a>) -> None</code>
- <code title="post /realtime/calls/{call_id}/hangup">client.realtime.calls.<a href="./src/openai/resources/realtime/calls.py">hangup</a>(call_id) -> None</code>
- <code title="post /realtime/calls/{call_id}/refer">client.realtime.calls.<a href="./src/openai/resources/realtime/calls.py">refer</a>(call_id, \*\*<a href="src/openai/types/realtime/call_refer_params.py">params</a>) -> None</code>
- <code title="post /realtime/calls/{call_id}/reject">client.realtime.calls.<a href="./src/openai/resources/realtime/calls.py">reject</a>(call_id, \*\*<a href="src/openai/types/realtime/call_reject_params.py">params</a>) -> None</code>

# Conversations

Types:

```python
from openai.types.conversations import (
    ComputerScreenshotContent,
    Conversation,
    ConversationDeleted,
    ConversationDeletedResource,
    Message,
    SummaryTextContent,
    TextContent,
    InputTextContent,
    OutputTextContent,
    RefusalContent,
    InputImageContent,
    InputFileContent,
)
```

Methods:

- <code title="post /conversations">client.conversations.<a href="./src/openai/resources/conversations/conversations.py">create</a>(\*\*<a href="src/openai/types/conversations/conversation_create_params.py">params</a>) -> <a href="./src/openai/types/conversations/conversation.py">Conversation</a></code>
- <code title="get /conversations/{conversation_id}">client.conversations.<a href="./src/openai/resources/conversations/conversations.py">retrieve</a>(conversation_id) -> <a href="./src/openai/types/conversations/conversation.py">Conversation</a></code>
- <code title="post /conversations/{conversation_id}">client.conversations.<a href="./src/openai/resources/conversations/conversations.py">update</a>(conversation_id, \*\*<a href="src/openai/types/conversations/conversation_update_params.py">params</a>) -> <a href="./src/openai/types/conversations/conversation.py">Conversation</a></code>
- <code title="delete /conversations/{conversation_id}">client.conversations.<a href="./src/openai/resources/conversations/conversations.py">delete</a>(conversation_id) -> <a href="./src/openai/types/conversations/conversation_deleted_resource.py">ConversationDeletedResource</a></code>

## Items

Types:

```python
from openai.types.conversations import ConversationItem, ConversationItemList
```

Methods:

- <code title="post /conversations/{conversation_id}/items">client.conversations.items.<a href="./src/openai/resources/conversations/items.py">create</a>(conversation_id, \*\*<a href="src/openai/types/conversations/item_create_params.py">params</a>) -> <a href="./src/openai/types/conversations/conversation_item_list.py">ConversationItemList</a></code>
- <code title="get /conversations/{conversation_id}/items/{item_id}">client.conversations.items.<a href="./src/openai/resources/conversations/items.py">retrieve</a>(item_id, \*, conversation_id, \*\*<a href="src/openai/types/conversations/item_retrieve_params.py">params</a>) -> <a href="./src/openai/types/conversations/conversation_item.py">ConversationItem</a></code>
- <code title="get /conversations/{conversation_id}/items">client.conversations.items.<a href="./src/openai/resources/conversations/items.py">list</a>(conversation_id, \*\*<a href="src/openai/types/conversations/item_list_params.py">params</a>) -> <a href="./src/openai/types/conversations/conversation_item.py">SyncConversationCursorPage[ConversationItem]</a></code>
- <code title="delete /conversations/{conversation_id}/items/{item_id}">client.conversations.items.<a href="./src/openai/resources/conversations/items.py">delete</a>(item_id, \*, conversation_id) -> <a href="./src/openai/types/conversations/conversation.py">Conversation</a></code>

# Evals

Types:

```python
from openai.types import (
    EvalCustomDataSourceConfig,
    EvalStoredCompletionsDataSourceConfig,
    EvalCreateResponse,
    EvalRetrieveResponse,
    EvalUpdateResponse,
    EvalListResponse,
    EvalDeleteResponse,
)
```

Methods:

- <code title="post /evals">client.evals.<a href="./src/openai/resources/evals/evals.py">create</a>(\*\*<a href="src/openai/types/eval_create_params.py">params</a>) -> <a href="./src/openai/types/eval_create_response.py">EvalCreateResponse</a></code>
- <code title="get /evals/{eval_id}">client.evals.<a href="./src/openai/resources/evals/evals.py">retrieve</a>(eval_id) -> <a href="./src/openai/types/eval_retrieve_response.py">EvalRetrieveResponse</a></code>
- <code title="post /evals/{eval_id}">client.evals.<a href="./src/openai/resources/evals/evals.py">update</a>(eval_id, \*\*<a href="src/openai/types/eval_update_params.py">params</a>) -> <a href="./src/openai/types/eval_update_response.py">EvalUpdateResponse</a></code>
- <code title="get /evals">client.evals.<a href="./src/openai/resources/evals/evals.py">list</a>(\*\*<a href="src/openai/types/eval_list_params.py">params</a>) -> <a href="./src/openai/types/eval_list_response.py">SyncCursorPage[EvalListResponse]</a></code>
- <code title="delete /evals/{eval_id}">client.evals.<a href="./src/openai/resources/evals/evals.py">delete</a>(eval_id) -> <a href="./src/openai/types/eval_delete_response.py">EvalDeleteResponse</a></code>

## Runs

Types:

```python
from openai.types.evals import (
    CreateEvalCompletionsRunDataSource,
    CreateEvalJSONLRunDataSource,
    EvalAPIError,
    RunCreateResponse,
    RunRetrieveResponse,
    RunListResponse,
    RunDeleteResponse,
    RunCancelResponse,
)
```

Methods:

- <code title="post /evals/{eval_id}/runs">client.evals.runs.<a href="./src/openai/resources/evals/runs/runs.py">create</a>(eval_id, \*\*<a href="src/openai/types/evals/run_create_params.py">params</a>) -> <a href="./src/openai/types/evals/run_create_response.py">RunCreateResponse</a></code>
- <code title="get /evals/{eval_id}/runs/{run_id}">client.evals.runs.<a href="./src/openai/resources/evals/runs/runs.py">retrieve</a>(run_id, \*, eval_id) -> <a href="./src/openai/types/evals/run_retrieve_response.py">RunRetrieveResponse</a></code>
- <code title="get /evals/{eval_id}/runs">client.evals.runs.<a href="./src/openai/resources/evals/runs/runs.py">list</a>(eval_id, \*\*<a href="src/openai/types/evals/run_list_params.py">params</a>) -> <a href="./src/openai/types/evals/run_list_response.py">SyncCursorPage[RunListResponse]</a></code>
- <code title="delete /evals/{eval_id}/runs/{run_id}">client.evals.runs.<a href="./src/openai/resources/evals/runs/runs.py">delete</a>(run_id, \*, eval_id) -> <a href="./src/openai/types/evals/run_delete_response.py">RunDeleteResponse</a></code>
- <code title="post /evals/{eval_id}/runs/{run_id}">client.evals.runs.<a href="./src/openai/resources/evals/runs/runs.py">cancel</a>(run_id, \*, eval_id) -> <a href="./src/openai/types/evals/run_cancel_response.py">RunCancelResponse</a></code>

### OutputItems

Types:

```python
from openai.types.evals.runs import OutputItemRetrieveResponse, OutputItemListResponse
```

Methods:

- <code title="get /evals/{eval_id}/runs/{run_id}/output_items/{output_item_id}">client.evals.runs.output_items.<a href="./src/openai/resources/evals/runs/output_items.py">retrieve</a>(output_item_id, \*, eval_id, run_id) -> <a href="./src/openai/types/evals/runs/output_item_retrieve_response.py">OutputItemRetrieveResponse</a></code>
- <code title="get /evals/{eval_id}/runs/{run_id}/output_items">client.evals.runs.output_items.<a href="./src/openai/resources/evals/runs/output_items.py">list</a>(run_id, \*, eval_id, \*\*<a href="src/openai/types/evals/runs/output_item_list_params.py">params</a>) -> <a href="./src/openai/types/evals/runs/output_item_list_response.py">SyncCursorPage[OutputItemListResponse]</a></code>

# Containers

Types:

```python
from openai.types import ContainerCreateResponse, ContainerRetrieveResponse, ContainerListResponse
```

Methods:

- <code title="post /containers">client.containers.<a href="./src/openai/resources/containers/containers.py">create</a>(\*\*<a href="src/openai/types/container_create_params.py">params</a>) -> <a href="./src/openai/types/container_create_response.py">ContainerCreateResponse</a></code>
- <code title="get /containers/{container_id}">client.containers.<a href="./src/openai/resources/containers/containers.py">retrieve</a>(container_id) -> <a href="./src/openai/types/container_retrieve_response.py">ContainerRetrieveResponse</a></code>
- <code title="get /containers">client.containers.<a href="./src/openai/resources/containers/containers.py">list</a>(\*\*<a href="src/openai/types/container_list_params.py">params</a>) -> <a href="./src/openai/types/container_list_response.py">SyncCursorPage[ContainerListResponse]</a></code>
- <code title="delete /containers/{container_id}">client.containers.<a href="./src/openai/resources/containers/containers.py">delete</a>(container_id) -> None</code>

## Files

Types:

```python
from openai.types.containers import FileCreateResponse, FileRetrieveResponse, FileListResponse
```

Methods:

- <code title="post /containers/{container_id}/files">client.containers.files.<a href="./src/openai/resources/containers/files/files.py">create</a>(container_id, \*\*<a href="src/openai/types/containers/file_create_params.py">params</a>) -> <a href="./src/openai/types/containers/file_create_response.py">FileCreateResponse</a></code>
- <code title="get /containers/{container_id}/files/{file_id}">client.containers.files.<a href="./src/openai/resources/containers/files/files.py">retrieve</a>(file_id, \*, container_id) -> <a href="./src/openai/types/containers/file_retrieve_response.py">FileRetrieveResponse</a></code>
- <code title="get /containers/{container_id}/files">client.containers.files.<a href="./src/openai/resources/containers/files/files.py">list</a>(container_id, \*\*<a href="src/openai/types/containers/file_list_params.py">params</a>) -> <a href="./src/openai/types/containers/file_list_response.py">SyncCursorPage[FileListResponse]</a></code>
- <code title="delete /containers/{container_id}/files/{file_id}">client.containers.files.<a href="./src/openai/resources/containers/files/files.py">delete</a>(file_id, \*, container_id) -> None</code>

### Content

Methods:

- <code title="get /containers/{container_id}/files/{file_id}/content">client.containers.files.content.<a href="./src/openai/resources/containers/files/content.py">retrieve</a>(file_id, \*, container_id) -> HttpxBinaryResponseContent</code>

# Videos

Types:

```python
from openai.types import (
    Video,
    VideoCreateError,
    VideoModel,
    VideoSeconds,
    VideoSize,
    VideoDeleteResponse,
)
```

Methods:

- <code title="post /videos">client.videos.<a href="./src/openai/resources/videos.py">create</a>(\*\*<a href="src/openai/types/video_create_params.py">params</a>) -> <a href="./src/openai/types/video.py">Video</a></code>
- <code title="get /videos/{video_id}">client.videos.<a href="./src/openai/resources/videos.py">retrieve</a>(video_id) -> <a href="./src/openai/types/video.py">Video</a></code>
- <code title="get /videos">client.videos.<a href="./src/openai/resources/videos.py">list</a>(\*\*<a href="src/openai/types/video_list_params.py">params</a>) -> <a href="./src/openai/types/video.py">SyncConversationCursorPage[Video]</a></code>
- <code title="delete /videos/{video_id}">client.videos.<a href="./src/openai/resources/videos.py">delete</a>(video_id) -> <a href="./src/openai/types/video_delete_response.py">VideoDeleteResponse</a></code>
- <code title="get /videos/{video_id}/content">client.videos.<a href="./src/openai/resources/videos.py">download_content</a>(video_id, \*\*<a href="src/openai/types/video_download_content_params.py">params</a>) -> HttpxBinaryResponseContent</code>
- <code title="post /videos/{video_id}/remix">client.videos.<a href="./src/openai/resources/videos.py">remix</a>(video_id, \*\*<a href="src/openai/types/video_remix_params.py">params</a>) -> <a href="./src/openai/types/video.py">Video</a></code>
- <code>client.videos.<a href="./src/openai/resources/videos.py">create_and_poll</a>(\*args) -> Video</code>



--- SOURCE: https://raw.githubusercontent.com/openai/openai-python/main/CONTRIBUTING.md ---

## Setting up the environment

### With Rye

We use [Rye](https://rye.astral.sh/) to manage dependencies because it will automatically provision a Python environment with the expected Python version. To set it up, run:

```sh
$ ./scripts/bootstrap
```

Or [install Rye manually](https://rye.astral.sh/guide/installation/) and run:

```sh
$ rye sync --all-features
```

You can then run scripts using `rye run python script.py` or by activating the virtual environment:

```sh
# Activate the virtual environment - https://docs.python.org/3/library/venv.html#how-venvs-work
$ source .venv/bin/activate

# now you can omit the `rye run` prefix
$ python script.py
```

### Without Rye

Alternatively if you don't want to install `Rye`, you can stick with the standard `pip` setup by ensuring you have the Python version specified in `.python-version`, create a virtual environment however you desire and then install dependencies using this command:

```sh
$ pip install -r requirements-dev.lock
```

## Modifying/Adding code

Most of the SDK is generated code. Modifications to code will be persisted between generations, but may
result in merge conflicts between manual patches and changes from the generator. The generator will never
modify the contents of the `src/openai/lib/` and `examples/` directories.

## Adding and running examples

All files in the `examples/` directory are not modified by the generator and can be freely edited or added to.

```py
# add an example to examples/<your-example>.py

#!/usr/bin/env -S rye run python
…
```

```sh
$ chmod +x examples/<your-example>.py
# run the example against your api
$ ./examples/<your-example>.py
```

## Using the repository from source

If you’d like to use the repository from source, you can either install from git or link to a cloned repository:

To install via git:

```sh
$ pip install git+ssh://git@github.com/openai/openai-python.git
```

Alternatively, you can build from source and install the wheel file:

Building this package will create two files in the `dist/` directory, a `.tar.gz` containing the source files and a `.whl` that can be used to install the package efficiently.

To create a distributable version of the library, all you have to do is run this command:

```sh
$ rye build
# or
$ python -m build
```

Then to install:

```sh
$ pip install ./path-to-wheel-file.whl
```

## Running tests

Most tests require you to [set up a mock server](https://github.com/stoplightio/prism) against the OpenAPI spec to run the tests.

```sh
# you will need npm installed
$ npx prism mock path/to/your/openapi.yml
```

```sh
$ ./scripts/test
```

## Linting and formatting

This repository uses [ruff](https://github.com/astral-sh/ruff) and
[black](https://github.com/psf/black) to format the code in the repository.

To lint:

```sh
$ ./scripts/lint
```

To format and fix all ruff issues automatically:

```sh
$ ./scripts/format
```

## Publishing and releases

Changes made to this repository via the automated release PR pipeline should publish to PyPI automatically. If
the changes aren't made through the automated pipeline, you may want to make releases manually.

### Publish with a GitHub workflow

You can release to package managers by using [the `Publish PyPI` GitHub action](https://www.github.com/openai/openai-python/actions/workflows/publish-pypi.yml). This requires a setup organization or repository secret to be set up.

### Publish manually

If you need to manually release a package, you can run the `bin/publish-pypi` script with a `PYPI_TOKEN` set on
the environment.
