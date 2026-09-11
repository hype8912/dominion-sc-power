# Security & Authentication Architecture

## Authentication State Machine

```mermaid
stateDiagram-v2
    [*] --> Unauthenticated
    Unauthenticated --> LoggingIn: LoginFlow.execute()
    LoggingIn --> TFA_Required: MfaChallenge
    LoggingIn --> Authenticated: direct OK
    TFA_Required --> LoggingIn: submit TFA
    TFA_Required --> Authenticated: TFA OK
    Authenticated --> Unauthenticated: session expiry / error
    Authenticated --> Authenticated: refresh / continue
```

## Auth Flow Sequence (Security-Focused)

```mermaid
sequenceDiagram
    participant Client as client.DominionSC
    participant Auth as auth.py
    participant Transport as transport.py
    participant Cookies as cookie jar (aiohttp)
    participant API as Dominion API

    Client->>Auth: LoginFlow.execute(username, password)
    Auth->>Transport: POST /login
    Transport->>API: credentials
    API-->>Transport: session + MfaChallenge (if TFA enabled)
    alt Direct Auth
        Transport-->>Auth: session cookie
        Auth->>Cookies: store cookies
        Auth-->>Client: ready
    else TFA Required
        Transport-->>Auth: MfaChallenge exception
        Auth->>Client: raise MfaChallenge
        Client->>Auth: submit code
        Auth->>Transport: POST /tfa
        Transport->>API: TFA code
        API-->>Transport: validated session
        Auth->>Cookies: persist session
        Auth-->>Client: ready
    end
    Note over Client,Cookies: Cookie jar reused for all subsequent requests via transport session
```

## Security Boundaries & Sensitive Assets

- **Secrets:** Password / TFA code passed through `auth.py`; never stored in source or config files (only env/args at runtime).
- **Session:** `create_cookie_jar()` in `__init__.py`; session cookies handled by `aiohttp.ClientSession` via `transport.py`.
- **Transport:** HTTPS only to Dominion endpoints; `urls.py` defines secure endpoints.
- **Data at rest:** CSV output may contain usage data; no encryption enforced by library (consumer responsibility).
- **Exceptions:** `exceptions.py` defines `InvalidAuth`, `MfaChallenge` to prevent credential leakage in error messages.

## Component Security Map

```mermaid
flowchart LR
    subgraph TrustBoundary["Trust Boundary: Library Process"]
        AuthMod["auth.py"]
        ClientMod["client.py"]
        TransportMod["transport.py"]
    end
    subgraph SensitiveAssets["Sensitive Assets"]
        Creds["User credentials (runtime only)"]
        TFA_Code["2FA code (runtime only)"]
        Session["Cookie jar / session tokens"]
    end
    subgraph External["External / Untrusted"]
        UserInput["CLI args / env vars"]
        DominionAPI["Dominion ESPI API"]
    end

    UserInput --> AuthMod
    AuthMod --> Creds
    AuthMod --> TFA_Code
    AuthMod --> Session
    AuthMod --> TransportMod
    TransportMod --> DominionAPI
    ClientMod --> Session
    ClientMod --> TransportMod
```
