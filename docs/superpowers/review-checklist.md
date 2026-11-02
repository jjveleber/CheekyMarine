# Review checklist

## Writing

- US English in user-visible strings, comments and docs. Word list (US from UK): favorite (favourite), color (colour), center (centre), meter (metre), gray (grey), license (licence, the noun), behavior (behaviour), neighbor (neighbour), canceled (cancelled), modeled (modelled), labeled (labelled), signaled (signalled), minimize and the -ize family (minimise, initialise, organise, recognise, normalise, serialise, visualise, customise, optimise), analyze (analyse), catalog (catalogue).
- Exceptions: code identifiers (`favouriteCapacity`, `setFavourite`, `FavouriteRole`), stored keys (the JSON key `"favourite"` until a schema migration, issue #32), third-party text, and words quoted from the owner.
- No em-dash character anywhere (prose, code, labels, commit messages). Use a colon, comma, parentheses, or a period.

## Reviewing

- The reviewer posts their own PR review (COMMENT, inline threads); the controller adjudicates.
- Threads are resolved one by one after a verified fix, never in bulk.
- No merge with open threads or red CI.
- One independent adversarial review of the branch before merge.
