# Security & Authentication Architecture

## Authentication State Machine

The library models login only. It has no token refresh: when a session is no longer valid, the caller calls `async_login()` again.

```mermaid
stateDiagram-v2
    [*] --> Unauthenticated
    Unauthenticated --> LoggingIn: async_login()
    LoggingIn --> TFA_Required: MfaChallenge raised
    LoggingIn --> Authenticated: saved tfa_token accepted
    LoggingIn --> Unauthenticated: InvalidAuth, CannotConnect or ApiException
    TFA_Required --> LoggingIn: code accepted, async_login() retried
    TFA_Required --> Unauthenticated: code rejected (InvalidAuth)
```

## Auth Flow Sequence (Security-Focused)

```mermaid
sequenceDiagram
    participant Caller as Caller (CLI or Home Assistant)
    participant Client as client.DominionSC
    participant Auth as auth.LoginFlow
    participant Transport as transport.py
    participant Portal as Dominion portal
    participant Bidgely as Bidgely API

    Caller->>Client: async_login()
    Client->>Auth: LoginFlow.execute(session, username, password, login_data)
    Auth->>Transport: GET login page, POST Authenticate
    Transport->>Portal: username and password over HTTPS
    Portal-->>Auth: status twoFA
    alt saved tfa_token is accepted
        Auth->>Transport: GET Verify2FAToken
        Transport->>Portal: saved tfa_token
    else token missing or rejected
        Auth-->>Caller: raise MfaChallenge (carries TFA handler)
        Caller->>Portal: handler: SendPINCode, then VerifyPIN with the code
        Portal-->>Caller: new tfa_token (caller must store it securely)
        Caller->>Client: async_login() again with login_data
    end
    Auth->>Transport: home page, account listing, InitAccount, GetBidgelySDKInit
    Auth->>Transport: POST wc-session (encrypted token)
    Transport->>Bidgely: encrypted token
    Bidgely-->>Auth: bearer access token
    Note over Client,Bidgely: Session cookies live in the caller's aiohttp cookie jar. The bearer token and user id stay in memory on DominionSC.
```

## Security Boundaries & Sensitive Assets

- **Credentials:** the username and password are supplied by the caller (constructor arguments; for the CLI, `--username`/`--password` or interactive prompts, with the password read through `getpass`). `DominionSC` keeps them on the instance for its lifetime and sends them only to the portal's `Authenticate` endpoint. The library does not read credentials from the environment or from files. A `--password` given on the command line is visible in shell history and process listings; omit it to be prompted instead.
- **TFA code:** entered by the user and sent once to `VerifyPIN`; not stored.
- **TFA token (`tfa_token`):** a long-lived value that lets later logins skip interactive TFA. The library returns it to the caller and never persists it. The CLI writes it as plain JSON to `--login_data_file` without changing file permissions; Home Assistant stores it in the config entry. Treat it like a password.
- **Bidgely bearer token and user id:** held in memory on the `DominionSC` instance (`access_token`, `user_id`); never persisted by the library.
- **Session cookies:** managed by the caller's `aiohttp.ClientSession`, which must be created with `create_cookie_jar()` (`helpers.py`, re-exported from the package root) so cookie values are not percent-encoded.
- **Transport:** the default Dominion and Bidgely endpoints in `config.py` are HTTPS.
- **Data at rest:** CSV output contains usage data and the service type; the library does no encryption (consumer responsibility).
- **Exceptions:** the library does not put the password in exception messages, but `InvalidAuth`, `ApiException`, and `CannotConnect` can embed raw API response bodies (`response_text`), which may include a service address or account number. Redact them before logging or sharing.

## Component Security Map

```mermaid
flowchart LR
    subgraph TrustBoundary["Trust Boundary: Library Process"]
        AuthMod["auth.py"]
        ClientMod["client.py"]
        TransportMod["transport.py"]
    end
    subgraph SensitiveAssets["Sensitive Assets"]
        Creds["Username and password (in memory)"]
        TFA_Code["TFA code (used once)"]
        TFA_Token["tfa_token (persisted by the caller)"]
        Bearer["Bidgely bearer token (in memory)"]
        Session["Cookie jar / session cookies (caller's session)"]
    end
    subgraph External["External / Untrusted"]
        UserInput["Caller input: constructor args, CLI args or prompts"]
        DominionAPI["Dominion portal API"]
        BidgelyAPI["Bidgely API"]
    end

    UserInput --> AuthMod
    AuthMod --> Creds
    AuthMod --> TFA_Code
    AuthMod --> TFA_Token
    AuthMod --> Bearer
    AuthMod --> TransportMod
    TransportMod --> Session
    TransportMod --> DominionAPI
    TransportMod --> BidgelyAPI
    ClientMod --> Bearer
    ClientMod --> Session
    ClientMod --> TransportMod
    ClientMod --> BidgelyAPI
```
