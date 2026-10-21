# Troubleshooting FAQ

## Sync is stuck

Check `larch status`. If the queue does not drain, run `larch sync --reset`.

## I get 429 errors

You hit the API rate limit. Wait for the `Retry-After` interval before retrying.
