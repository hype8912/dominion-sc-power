# Data Flow & Sequence Architecture

## Request Sequence (CLI -> APIs -> Parser -> CSV)

This is the flow for `python -m dominionsc --csv output.csv`. Without `--csv`, the CLI also fetches and prints the forecast and prints readings to the console instead of writing a file.

```mermaid
sequenceDiagram
    actor User
    participant CLI as cli.py
    participant Client as client.DominionSC
    participant Auth as auth.LoginFlow
    participant Portal as Dominion portal
    participant Bidgely as Bidgely API
    participant Parser as parsers/greenbutton.py

    User->>CLI: python -m dominionsc --username ... --csv out.csv
    CLI->>Client: DominionSC(session, username, password, login_data)
    CLI->>Client: async_login()
    Client->>Auth: LoginFlow.execute(session, username, password, login_data)
    Auth->>Portal: GET login page (verification token)
    Auth->>Portal: POST Authenticate (username, password)
    Portal-->>Auth: status twoFA
    alt no valid saved tfa_token
        Auth-->>CLI: raise MfaChallenge (carries TFA handler)
        CLI->>Portal: handler: InitAuthentication, SendPINCode, VerifyPIN
        Portal-->>CLI: new tfa_token (saved to --login_data_file if given)
        CLI->>Client: async_login() again
    else saved tfa_token is valid
        Auth->>Portal: GET Verify2FAToken
    end
    Auth->>Portal: GET home page, account listing, InitAccount, GetBidgelySDKInit
    Auth->>Bidgely: POST wc-session (encrypted token)
    Bidgely-->>Auth: bearer access token, user id, measurement types
    Auth-->>Client: access_token, user_id, accounts

    CLI->>Client: async_get_accounts()
    loop each measurement type (ELECTRIC, GAS)
        CLI->>Client: async_get_register_reads(type, start, end)
        Client->>Bidgely: GET gb-download (session.get, bearer token)
        Bidgely-->>Client: Green Button ESPI XML
        Client->>Parser: parse_registers(xml, timezone)
        Parser-->>Client: list of RegisterReads (one per UsagePoint)
        Client-->>CLI: list of RegisterReads
    end
    CLI->>CLI: write CSV rows (service, register, start_time, end_time, consumption)
```

All Dominion and Bidgely login and forecast calls go through `DominionSCURLHandler.call_api()` in `transport.py`. Usage reads (`gb-download`) call `session.get` directly, a known inconsistency documented in `transport.py` and the developer guide.

## Data Flow Diagram (Flowchart)

```mermaid
flowchart TD
    A["CLI args"] --> B["cli.run()"]
    B --> C["DominionSC(session, username, password, login_data)"]
    C --> D["async_login() -> LoginFlow.execute()"]
    D --> E{"valid saved tfa_token?"}
    E -- No --> F["MfaChallenge -> TFA handler -> new tfa_token"]
    F --> D
    E -- Yes --> G["Bidgely wc-session: access token + user id"]
    G --> H["async_get_register_reads(type, start, end)"]
    H --> I["GET Bidgely gb-download (Green Button XML)"]
    I --> J["parse_registers(): scale values, group by UsagePoint"]
    J --> K["list of RegisterReads"]
    K --> L["CLI CSV writer or console output"]
    L --> M["CSV columns: service, register, start_time, end_time, consumption"]
```

## Response Parsing Flow (Grounded)

- **Historical:** `parsers/greenbutton.py` parses ESPI XML. Registers are separated by `UsagePoint` id (see `register_reads.py`) and returned in first-seen order. Negative values are preserved (a solar-export register may report them). Raw values are multiplied by the feed's declared `powerOfTenMultiplier` (`10 ** multiplier`), which is what converts Dominion's gas readings to cubic feet; electric feeds declare none.
- **Forecast:** `DominionSC.async_get_forecast()` fetches the portal home page (for a fresh verification token), then the `GetAccountAMIUsageAlerts` endpoint; `parsers/forecast.py` turns the JSON into a `Forecast` (`models/forecast.py`).
