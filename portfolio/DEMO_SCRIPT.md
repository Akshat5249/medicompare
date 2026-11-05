# Demo script

Setup: `make up`, then open http://localhost:3000. Say early that brands and shop prices are fictional demo data.

## 60-second pitch
The same medicine can cost very different amounts by brand in India, but a wrong "cheaper equivalent" could hurt someone. MediCompare is a neutral price information tool built around that risk. It reads a prescription, but a person must confirm every medicine before the server will show a single price. It only compares products proven identical on ingredient, salt, strength, form, route and release type, and every price shows its type, source and date. Real government ceiling prices are loaded, and retail brand data is the main gap. It is a working, tested prototype with 96 safety tests, not yet a live service.

## 3-minute walkthrough
| Time | Do | Say |
|---|---|---|
| 0:00 | Home page | "Information only, and it sells nothing. Note the notice on every page" |
| 0:20 | Search `metformn` | "Typo tolerated, but these are only possible matches, and it says why" |
| 0:40 | Open `Metformin 500mg Tablet` | "Real NPPA data. It's labelled as a legal maximum, not a shop price, and flagged as possibly out of date, because it is" |
| 1:00 | Scroll to "Not directly comparable" | "Salt form isn't stated by the source, so we refuse to compare. That honesty costs us features" |
| 1:15 | Search `DemoAtorvAlpha` | "Demo data, labelled. Here's a real comparison: it states exactly what's compared" |
| 1:35 | Add prescription, type `DemoMetacin`, `500 mg` | "Typing is equal to uploading. This name looks like another medicine, so confirm stays locked until you check" |
| 2:00 | Open the item's prices URL before confirming | "Even a direct request gets refused by the server" |
| 2:15 | Confirm, then show the summary | "Confirmed items only, addressed to your doctor or pharmacist. The link expires" |
| 2:35 | Type `I took too many tablets` in search | "Emergency language interrupts everything with 112, in three languages" |
| 2:50 | Switch to Tamil | "Full interface in Hindi and Tamil, pending native-speaker review" |

Videos are in `portfolio/demo/videos/`.
