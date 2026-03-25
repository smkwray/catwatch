# Data model

## Core entities

### sponsors
Public risk transfer buyers or affiliated groups.

Proposed fields:
- sponsor_id
- sponsor_name
- canonical_name
- cik
- ticker
- domicile
- notes

### issuers_spv
SPIs / SPVs / issuers connected to programmes or tranches.

Proposed fields:
- issuer_id
- issuer_name
- canonical_name
- regulator_class
- registration_number
- jurisdiction
- notes

### programmes
Programme or series family.

Proposed fields:
- programme_id
- programme_name
- sponsor_id
- issuer_id
- first_seen_date
- last_seen_date
- status
- source_url

### tranches
Atomic tradable or listed tranche-like unit.

Proposed fields:
- tranche_id
- programme_id
- tranche_name
- sponsor_name
- issuer_name
- listing_venue
- listing_status
- listed_date
- maturity_date
- issue_amount
- currency
- isin
- cusip
- trigger_type
- peril_codes
- region_codes
- risk_start_date
- risk_end_date
- status
- confidence
- review_status
- source_url
- extraction_method
- retrieved_at

### hazard_events
Canonical event table shared across sources.

Proposed fields:
- event_id
- source_name
- source_event_id
- peril_code
- event_name
- start_time
- end_time
- region_codes
- latitude
- longitude
- geometry_json
- severity
- metadata_json
- source_url

### event_bond_matches
Rule-based possible overlaps.

Proposed fields:
- match_id
- event_id
- tranche_id
- match_status
- score
- reasons_json
- generated_at

## Taxonomies

### Perils
Use a concise normalized taxonomy first:
- us_wind
- ca_earthquake
- ca_wildfire
- flood
- severe_convective_storm
- europe_windstorm
- japan_typhoon
- earthquake
- tropical_cyclone
- mortality
- cyber
- other_property_cat

### Regions
Keep coarse codes initially:
- us
- florida
- southeast_us
- gulf_coast
- california
- japan
- europe
- caribbean
- global
