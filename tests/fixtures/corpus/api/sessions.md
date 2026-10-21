# Sessions

A session represents an authenticated device.

## Create a session

`POST /v1/sessions` exchanges an API token for a short-lived session token that expires after one hour.

## List sessions

`GET /v1/sessions` returns the active sessions for the current account.

## Revoke a session

`DELETE /v1/sessions/{id}` signs the device out immediately.
