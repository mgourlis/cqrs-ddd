# CQRS-DDD Identity

Authentication — "Who are you?"

Resolves bearer tokens to an immutable `Principal` value object via `IIdentityProvider`. Supports OAuth 2.0 / OIDC flows and optional two-factor authentication (2FA).

## Installation

```bash
pip install cqrs-ddd-identity
```

### Extras

```bash
# Keycloak OIDC support
pip install cqrs-ddd-identity[keycloak]

# Generic OAuth2 providers
pip install cqrs-ddd-identity[oauth2]

# Database authentication
pip install cqrs-ddd-identity[db]

# MFA/2FA support
pip install cqrs-ddd-identity[mfa]

# LDAP authentication
pip install cqrs-ddd-identity[ldap]

# FastAPI integration
pip install cqrs-ddd-identity[fastapi]

# All features
pip install cqrs-ddd-identity[all]
```

## Quick Start

### Basic Usage

```python
from cqrs_ddd_identity import (
    Principal,
    get_current_principal,
    IIdentityProvider,
)

# In your request handler or domain service
principal = get_current_principal()
print(f"Current user: {principal.username}")

# Check permissions
if principal.has_permission("write:orders"):
    # Allow order modification
    pass

# Check roles
if principal.has_role("admin"):
    # Admin-only logic
    pass
```

### FastAPI Integration

```python
from fastapi import FastAPI, Depends
from cqrs_ddd_identity import get_current_principal, Principal

app = FastAPI()

@app.get("/me")
def get_me(principal: Principal = Depends(get_current_principal)):
    return {"user_id": principal.user_id, "username": principal.username}
```

### Context Management

```python
from cqrs_ddd_identity import (
    set_principal,
    clear_principal,
    get_user_id,
    require_role,
)

# Set principal in middleware
token = set_principal(principal)
try:
    # Get user ID anywhere in request
    user_id = get_user_id()

    # Require role for sensitive operations
    require_role("admin")
finally:
    clear_principal()
```

## Features

- **Principal Value Object**: Immutable identity representation
- **Context Management**: Async-safe principal storage via `ContextVar`
- **OAuth 2.0 / OIDC**: Authorization code flow with PKCE
- **Keycloak Support**: OIDC discovery, group-to-role mapping
- **Database Auth**: Username/password with bcrypt/argon2id
- **MFA/2FA**: TOTP, backup codes, email/SMS OTP
- **API Key Auth**: Service-to-service authentication
- **FastAPI Integration**: Middleware and dependencies

## License

MIT
