# Webhooks

Webhooks notify your server when notes change.

## Events

Larch sends `note.created`, `note.updated` and `note.deleted` events.

## Verifying signatures

Each delivery carries an `X-Larch-Signature` header: an HMAC-SHA256 of the body using your webhook secret.

## Retries

Failed deliveries are retried with exponential backoff for up to 24 hours.
