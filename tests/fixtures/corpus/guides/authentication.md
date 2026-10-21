# Authentication

Every API request must be authenticated. Larch supports API tokens and OAuth.

## Tokens

API tokens are long-lived secrets created in the dashboard. Send them in the `Authorization: Bearer` header.
Tokens expire after 90 days unless you rotate them.

### Rotating tokens

Create a new token, deploy it, then revoke the old one. Both tokens work during the overlap.

## OAuth

Use OAuth when acting on behalf of another user. Larch implements the authorization code flow with PKCE.

## Scopes

Each token or OAuth grant carries scopes such as `notes:read` and `notes:write`.

## Troubleshooting

A `401` means the token is missing or expired. A `403` means the token lacks the required scope.
