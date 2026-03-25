# Methods

## Parsing strategy

Prefer deterministic extraction in this order:

1. explicit labeled fields on source pages,
2. structured URLs / ids,
3. regular expressions for dates / currencies / identifiers,
4. curated alias dictionaries,
5. manual review queue.

Avoid unbounded ML extraction in the first release.

## Match methodology

A tranche enters the watchlist only when all of the following are true:

1. its risk window is active or plausibly active,
2. the event peril matches the tranche peril taxonomy,
3. the event geography overlaps the tranche coverage geography at the coarse text level,
4. the source evidence for the tranche is not too weak.

## Confidence scoring

Suggested factors:
- +0.35 peril specificity
- +0.35 active-date overlap
- +0.20 coarse region overlap
- +0.10 sponsor evidence support

Clamp scores to [0, 1].

## Claim language

Safe language:
- possible overlap
- relevant event
- active risk-window overlap
- public sponsor evidence suggests exposure to this peril/region

Unsafe language without stronger evidence:
- triggered
- principal loss certain
- payout amount
- marked down by X bps
