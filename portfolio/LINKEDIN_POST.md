# LinkedIn post

The same medicine can cost very different amounts depending on the brand in India. But a wrong "cheaper equivalent" could really hurt someone.

So I built a prototype, MediCompare, around one rule: software proposes, a person decides.

- It reads a prescription, but the server shows no prices until a person confirms each medicine
- It compares only products proven identical on ingredient, salt, strength, form, route and release type
- Every price shows its type, source and date
- English, Hindi and Tamil

What I measured: 99 safety tests, 295 backend tests at 98.3% coverage, and an OCR evaluation on 600 synthetic prescriptions, where about one in five unfiltered top matches was wrong. That result is why a person has to confirm.

What it isn't yet: it isn't live, it has no users, and it has no real shop prices. Real data is NPPA's legal price limits, not shop prices. Synthetic handwriting is easier than the real thing.

Built with substantial help from Claude Code. Feedback from pharmacists and doctors is very welcome.
