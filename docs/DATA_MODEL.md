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
- attribution_status
- sponsor_attribution_state
- sponsor_source_url
- sponsor_source_note
- bma_match_method
- bma_candidate_count
- bma_top_candidate_name
- bma_top_candidate_score
- sec_match_method
- sec_candidate_count
- sec_top_candidate_name
- sec_top_candidate_score
- peril_source_type
- peril_source_url
- peril_source_note
- region_source_type
- region_source_url
- region_source_note
- maturity_source_type
- maturity_source_url
- maturity_source_note
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
- source_record_id
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
- match_scope
- public_blockers
- candidate_reason_codes
- confidence_band
- tranche_issue_flags
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
