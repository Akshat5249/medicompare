# UX

## Information architecture
- **Search:** results, medicine detail (composition, prices, options).
- **Jan Aushadhi:** Kendra directory, catalogue listings.
- **Prescriptions:** list, add (type or upload), check, prices for one medicine, summary.
- **Account:** saved lists, export, delete. Sign in, register, pharmacist registration.
- **Pharmacist:** queue, review. **Admin:** freshness, imports, review queue, approvals, audit.
- **About, Privacy, offline page.**

## Principles
1. **Safety copy comes first.** Disclaimers and differences appear before prices.
2. **Neutral options.** No green, no "recommended", no rank badges.
3. **State the uncertainty.** "Not found" and "Unclear" are visible states, not blanks.
4. **Friction where it protects.** Look-alike names need a checkbox, and identity is confirmed one medicine at a time.
5. **Typing is equal to uploading,** and is the default tab.

## Design system
- **Colour:** indigo 800 and 900 for actions, amber for warnings, red for regulatory notices and emergencies, purple for the demo badge, slate for text. No green. Colour is never the only signal, since every state has text.
- **Type:** the system font stack, so Hindi and Tamil use device fonts with no font download.
- **Targets:** interactive controls are at least 44 px tall.
- **Components:** `frontend/src/components/ui.tsx`.

## States on every screen
| State | Implementation |
|---|---|
| Loading | `Loading`, with `role="status"` |
| Empty | `Empty`, with a specific message |
| Error | `ErrorState`, with `role="alert"` and retry |
| Signed out | A prompt to sign in |
| Low confidence | Label per item, highlighted span on the image |
| No data | "We have no sourced price" (never a blank or zero) |
| Stale | "May be out of date" |
| Demo | "Demo data" badge |
| Emergency | Modal `alertdialog` with a Call 112 link |

## Accessibility
Skip link, landmarks, one `h1` per page, labelled controls, a focus-visible outline, `lang` set per locale, dialog focus handling. Automated checks: axe on each page, on desktop and mobile. **Not done:** testing with screen-reader users, or on a real low-end Android device.

## Screens
Screenshots are captured by Playwright into `portfolio/demo/screenshots/`.

| Screen | Desktop | Mobile |
|---|---|---|
| Home | [view](../portfolio/demo/screenshots/desktop-home.png) | [view](../portfolio/demo/screenshots/mobile-home.png) |
| Hindi home | [view](../portfolio/demo/screenshots/desktop-home-hi.png) | [view](../portfolio/demo/screenshots/mobile-home-hi.png) |
| Tamil home | [view](../portfolio/demo/screenshots/desktop-home-ta.png) | [view](../portfolio/demo/screenshots/mobile-home-ta.png) |
| Search with a typo | [view](../portfolio/demo/screenshots/desktop-search-typo.png) | [view](../portfolio/demo/screenshots/mobile-search-typo.png) |
| Real record with stale label | [view](../portfolio/demo/screenshots/desktop-medicine-real.png) | [view](../portfolio/demo/screenshots/mobile-medicine-real.png) |
| Demo record with options | [view](../portfolio/demo/screenshots/desktop-medicine-demo.png) | [view](../portfolio/demo/screenshots/mobile-medicine-demo.png) |
| Emergency | [view](../portfolio/demo/screenshots/desktop-emergency.png) | [view](../portfolio/demo/screenshots/mobile-emergency.png) |
| Jan Aushadhi | [view](../portfolio/demo/screenshots/desktop-jan-aushadhi.png) | [view](../portfolio/demo/screenshots/mobile-jan-aushadhi.png) |
| Consent and upload | [view](../portfolio/demo/screenshots/desktop-upload-consent.png) | [view](../portfolio/demo/screenshots/mobile-upload-consent.png) |
| Checking, typed | [view](../portfolio/demo/screenshots/desktop-verify-manual.png) | [view](../portfolio/demo/screenshots/mobile-verify-manual.png) |
| Checking, with image | [view](../portfolio/demo/screenshots/desktop-verify-upload.png) | [view](../portfolio/demo/screenshots/mobile-verify-upload.png) |
| Gate blocked | [view](../portfolio/demo/screenshots/desktop-gate-blocked.png) | [view](../portfolio/demo/screenshots/mobile-gate-blocked.png) |
| Look-alike warning | [view](../portfolio/demo/screenshots/desktop-lasa-warning.png) | [view](../portfolio/demo/screenshots/mobile-lasa-warning.png) |
| No match | [view](../portfolio/demo/screenshots/desktop-no-match.png) | [view](../portfolio/demo/screenshots/mobile-no-match.png) |
| Comparison | [view](../portfolio/demo/screenshots/desktop-comparison.png) | [view](../portfolio/demo/screenshots/mobile-comparison.png) |
| Summary | [view](../portfolio/demo/screenshots/desktop-summary.png) | [view](../portfolio/demo/screenshots/mobile-summary.png) |
| Pharmacist queue | [view](../portfolio/demo/screenshots/desktop-pharmacist-queue.png) | [view](../portfolio/demo/screenshots/mobile-pharmacist-queue.png) |
| Pharmacist review | [view](../portfolio/demo/screenshots/desktop-pharmacist-review.png) | [view](../portfolio/demo/screenshots/mobile-pharmacist-review.png) |
| Admin | [view](../portfolio/demo/screenshots/desktop-admin.png) | [view](../portfolio/demo/screenshots/mobile-admin.png) |
| Account | [view](../portfolio/demo/screenshots/desktop-account.png) | [view](../portfolio/demo/screenshots/mobile-account.png) |

Loading and error states are covered by unit tests rather than screenshots, since they are brief or need a forced failure.

## Pharmacist test script (not yet run)
1. Sign in, and find a prescription shared with you.
2. Compare the image with the extracted fields. Is anything misleading?
3. Correct one misread strength. Is the effect clear?
4. Confirm one medicine and mark another unresolved.
5. Is "Registration self-declared" acceptable wording? Would you want anything else recorded?
6. Would you be comfortable discussing this summary with a patient?
