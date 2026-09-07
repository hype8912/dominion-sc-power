"""Constants."""

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"

# NOTE: Bidgely's platform is multi-tenant and requests must include a Pilot ID
# identifying which utility program's data pipeline to use. This value was
# previously hardcoded as "10106" in two places in dominionsc.py, which routed
# requests into the wrong pilot and returned incorrect (smoothed/estimated,
# hourly-quantized) usage data instead of the real 15-minute meter reads.
# Confirmed correct value ("10078") via browser DevTools on a real gb-download
# request from account.dominionenergysc.com.
# CAVEAT: this is almost certainly account/utility-specific in Bidgely's
# multi-tenant setup and may not be correct for every Dominion Energy SC
# customer -- ideally this would be discovered dynamically per-account rather
# than hardcoded at all.
BIDGELY_PILOT_ID = "10078"
