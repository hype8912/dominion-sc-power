# Data Flow & Sequence Architecture

## Request Sequence (CLI -> API -> Parser -> CSV)

```mermaid
sequenceDiagram
    actor User
    participant CLI as cli.py
    participant Client as client.DominionSC
    participant Auth as auth.py
    participant Transport as transport.py
    participant URLs as urls.py
    participant API as Dominion ESPI API
    participant Parser as parsers/greenbutton.py
    participant Models as models/

    User->>CLI: python -m dominionsc --username ...
    CLI->>Client: DominionSC(session)
    Client->>Auth: LoginFlow.execute(username, password)
    Auth->>Transport: GET /access/#login
    Transport->>URLs: login_page_url()
    URLs-->>Transport: URL
    Transport->>API: login request
    API-->>Transport: session cookie + possible TFA
    alt TFA Required
        Transport-->>Auth: MfaChallenge
        Auth->>Client: prompt / input
        Client->>Auth: submit TFA code
        Auth->>Transport: POST /tfa
        Transport->>API: TFA verification
    end
    API-->>Transport: authenticated session
    Auth-->>Client: cookie jar ready

    Client->>Transport: GET usage / forecast
    Transport->>URLs: gb_download_url(user_id, ...)
    Transport->>API: request with cookies
    API-->>Transport: XML / JSON response
    Transport-->>Client: raw response
    Client->>Parser: parse_usage(raw)
    Parser->>Parser: parse ESPI UsagePoint XML
    Parser-->>Models: register_reads (per UsagePoint id)
    Models-->>Client: structured result
    Client-->>CLI: list[register_reads]
    CLI->>CLI: write CSV (service/register/reading/date/usage)
```

## Data Flow Diagram (Flowchart)

```mermaid
flowchart TD
    A["User / CLI args"] --> B["cli.run()"]
    B --> C["DominionSC.init(session, cookie_jar)"]
    C --> D["auth.LoginFlow.execute()"]
    D --> E["transport GET login page"]
    E --> F{"TFA?"}
    F -- Yes --> G["MfaChallenge -> submit TFA"]
    G --> H["transport POST TFA"]
    F -- No --> H
    H --> I["Cookie jar session"]
    I --> J["client.async_get_usage_reads()"]
    J --> K["transport GET usage endpoint"]
    K --> L["Dominion API (ESPI)"]
    L --> M["Raw XML / JSON"]
    M --> N["parsers.greenbutton.parse()"]
    N --> O["models.register_reads"]
    O --> P["cli CSV writer"]
    P --> Q["Output file (service, register, reading, date, usage)"]
```

## Response Parsing Flow (Grounded)

- **Historical:** `parsers/greenbutton.py` parses ESPI XML. Registers separated by `UsagePoint` id (see `register_reads.py`). Negative values preserved for solar export.
- **Forecast:** `parsers/forecast.py` parses forecast endpoint into cost projections (`models/forecast.py`).
