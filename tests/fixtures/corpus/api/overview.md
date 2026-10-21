# API Overview

The Larch REST API lives at `https://api.larch.example/v1`. All responses are JSON.

## Rate limits

Clients may send 600 requests per minute per token. Exceeding the limit returns `429` with a `Retry-After` header.

## Errors

Errors use a JSON body with `code` and `message` fields.
