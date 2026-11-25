# Methods

## Parsing strategy

Extraction is deterministic and tries, in order:

1. explicit labeled fields on source pages,
2. structured URLs / ids,
3. regular expressions for dates / currencies / identifiers,
4. curated alias dictionaries,
5. manual review queue.

## Match methodology

A tranche enters the public watchlist only when all of the following are true:

1. its risk window is active or plausibly active,
2. the event peril matches the tranche peril taxonomy,
3. the event geography overlaps the tranche coverage geography at the coarse text level,
4. the source evidence for the tranche is not too weak.

Matches that rely on `other_property_cat` or incomplete region evidence stay in the review-candidate set, shown separately from the public watchlist.

Every match carries classification metadata:
- `match_scope`: `public` or `candidate`
- `public_blockers`: tranche-side evidence blockers that disqualify a row from public display
- `candidate_reason_codes`: the broad-peril / weak-region / missing-evidence reasons that explain why the row is still review-only
- `confidence_band`: coarse `high` / `medium` / `low` display guidance for the watchlist surface

## Field attribution

Provenance is recorded per field rather than as one tranche-level confidence score:
- sponsor source and source URL
- sponsor attribution state (`bsx_declared`, `sec_exact_spv`, `sec_ranked_spv`, `alias_family`, `manual_override`, `missing`)
- BMA linkage method and top candidate metadata when an issuer/entity link is ambiguous
- SEC SPV linkage method and top candidate metadata when an issuer/SPV link is ambiguous
- peril source type / URL / note
- region source type / URL / note
- maturity source type / URL / note

## Linkage policy

Linkage is deterministic and tries, in order:

1. exact BSX-declared sponsor,
2. exact SEC SPV linkage,
3. clearly dominant ranked BMA / SEC candidates,
4. curated family aliases,
5. tranche-specific manual override,
6. review queue when no auto-accept path is defensible.
