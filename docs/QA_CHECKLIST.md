# QA checklist

Use this before publishing snapshots or site updates.

## Registry QA
- [ ] titles are not blank
- [ ] source URLs resolve
- [ ] listed dates parse where visible
- [ ] status values are normalized
- [ ] issuer names are not polluted by HTML labels
- [ ] obvious duplicates are merged or flagged
- [ ] manual overrides are documented

## Event QA
- [ ] event ids are stable
- [ ] timestamps are UTC-normalized where possible
- [ ] peril mapping rules are documented
- [ ] source-specific caveats are preserved

## Watchlist QA
- [ ] matches include reasons
- [ ] score is bounded between 0 and 1
- [ ] language says possible overlap, not trigger
- [ ] region mismatches suppress false positives

## Site QA
- [ ] dashboard renders from static JSON only
- [ ] notes explain limitations
- [ ] demo fallback works
