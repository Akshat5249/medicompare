// Builds portfolio/deck.pptx from verification/metrics.json, so numbers stay measured.
// Run: NODE_PATH=<dir with pptxgenjs> node scripts/build_deck.js [apply_theme.js path]
const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");

const ROOT = path.resolve(__dirname, "..");
const m = JSON.parse(fs.readFileSync(path.join(ROOT, "verification/metrics.json"), "utf8"));
const s = m.engines[m.selected_engine];
const o = m.engines[m.other_engine];
const shot = (name) => path.join(ROOT, "portfolio/demo/slides", `${name}.png`);
const INDIGO = "312E81";
const INK = "1E1B4B";
const MUTED = "57534E";
const TINT = "EEF0FB";
const AMBER = "B45309";
const AMBER_TINT = "FEF3C7";
const WHITE = "FFFFFF";
const THEME = {
  name: "MediCompare",
  colors: {
    dk1: INK, lt1: WHITE, dk2: INDIGO, lt2: TINT, accent1: INDIGO, accent2: AMBER, accent3: "EB6834",
    accent4: "2A78D6", accent5: "57534E", accent6: "7C3AED", hlink: INDIGO, folHlink: "57534E",
  },
};

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.title = "MediCompare";
pres.theme = { headFontFace: "Cambria", bodyFontFace: "Calibri" };
const C = pres.SchemeColor;

pres.defineSlideMaster({
  title: "CONTENT",
  background: { color: WHITE },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.4, w: 12.1, h: 1.0, fontSize: 32, bold: true, color: C.text2, margin: 0, valign: "top", align: "left" }, text: "" } },
    { text: { text: "MediCompare · Information only, not medical advice", options: { x: 0.6, y: 7.0, w: 9, h: 0.3, fontSize: 10, color: C.accent5, margin: 0 } } },
  ],
  slideNumber: { x: 12.2, y: 7.0, w: 0.6, h: 0.3, fontSize: 10, color: C.accent5, align: "right" },
});
pres.defineSlideMaster({
  title: "DARK",
  background: { color: INDIGO },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.8, y: 1.4, w: 11.7, h: 1.6, fontSize: 48, bold: true, color: C.background1, margin: 0, valign: "top", align: "left" }, text: "" } },
  ],
});

const text = (slide, value, options) => slide.addText(value, { isTextBox: true, margin: 0, color: C.text1, fontSize: 16, valign: "top", ...options });
const content = (title, notes) => {
  const slide = pres.addSlide({ masterName: "CONTENT" });
  slide.addText(title, { placeholder: "title" });
  if (notes) slide.addNotes(notes);
  return slide;
};
const card = (slide, x, y, w, h, heading, body, fill = TINT) => {
  slide.addShape(pres.ShapeType.roundRect, { x, y, w, h, fill: { color: fill }, line: { color: fill }, rectRadius: 0.08, objectName: `Card ${heading}` });
  text(slide, heading, { x: x + 0.22, y: y + 0.18, w: w - 0.44, h: 0.4, fontSize: 18, bold: true, color: C.text2 });
  text(slide, body, { x: x + 0.22, y: y + 0.62, w: w - 0.44, h: h - 0.75, fontSize: 18 });
};
const stat = (slide, x, y, w, big, label) => {
  text(slide, big, { x, y, w, h: 0.95, fontSize: 44, bold: true, color: C.text2, fontFace: "Cambria" });
  text(slide, label, { x, y: y + 0.98, w, h: 0.7, fontSize: 14, color: C.accent5 });
};
// Fits an image inside a box, keeping its proportions. Returns the size used.
const framed = (slide, name, x, y, maxW, maxH, alt) => {
  const { w: pw, h: ph } = JSON.parse(fs.readFileSync(path.join(ROOT, "portfolio/demo/slides/sizes.json")))[name];
  const scale = Math.min(maxW / pw, maxH / ph);
  const w = pw * scale;
  const h = ph * scale;
  slide.addImage({ path: shot(name), x, y, w, h, altText: alt, shadow: { type: "outer", color: "9A9A94", opacity: 0.35, blur: 6, offset: 2, angle: 90 } });
  return { w, h };
};

// 1
let slide = pres.addSlide({ masterName: "DARK" });
slide.addText("MediCompare", { placeholder: "title" });
text(slide, "Medicine prices you can trace to a source. Software proposes, a person decides.", { x: 0.8, y: 2.9, w: 10.5, h: 1.2, fontSize: 26, color: C.background1 });
text(slide, "Working, tested prototype. Not deployed. Real prices are NPPA legal maximums. Shop prices shown are fictional demo data.", { x: 0.8, y: 5.6, w: 10.5, h: 0.8, fontSize: 16, color: C.background2 });
slide.addNotes("Say at the start that this is a prototype, and that brand data is fictional.");

// 2
slide = content("Cheaper medicine is valuable. A wrong match is dangerous", "The risk is the design driver. No user research has been done: this comes from desk research.");
card(slide, 0.6, 1.7, 3.85, 3.2, "Prices vary", "The same molecule at the same strength can cost very different amounts by brand.");
card(slide, 4.74, 1.7, 3.85, 3.2, "Prescriptions are hard", "Handwriting, and brand versus generic names, make it hard to know what you were prescribed.");
card(slide, 8.88, 1.7, 3.85, 3.2, "Trust is hard", "Is that a shop price, a legal maximum or a catalogue listing? How old is it? Where did it come from?");
slide.addShape(pres.ShapeType.roundRect, { x: 0.6, y: 5.25, w: 12.13, h: 1.25, fill: { color: AMBER_TINT }, line: { color: AMBER_TINT }, rectRadius: 0.08, objectName: "Risk callout" });
text(slide, "Similar names are not the same medicine. An app that confidently suggests a wrong \"equivalent\" could harm someone.", { x: 0.85, y: 5.48, w: 11.6, h: 0.85, fontSize: 18, bold: true, valign: "middle", color: "78350F" });

// 3
slide = content("A neutral tool for a better conversation with your doctor", "It sells nothing, and ranking has no commercial input.");
text(slide, "What it does", { x: 0.6, y: 1.7, w: 7, h: 0.4, fontSize: 20, bold: true, color: C.text2 });
text(slide, [
  { text: "Search by brand, generic or ingredient, with typo tolerance", options: { bullet: true, breakLine: true } },
  { text: "Show prices with type, source and date", options: { bullet: true, breakLine: true } },
  { text: "List options with every difference flagged", options: { bullet: true, breakLine: true } },
  { text: "Find Jan Aushadhi listings and Kendras, with no stock claims", options: { bullet: true, breakLine: true } },
  { text: "Read prescriptions, with a person confirming each medicine", options: { bullet: true, breakLine: true } },
  { text: "Pharmacist review, a shareable summary, and three languages", options: { bullet: true } },
], { x: 0.6, y: 2.2, w: 7.1, h: 3.9, fontSize: 18, paraSpaceAfter: 10 });
card(slide, 8.2, 1.7, 4.53, 4.4, "What it is not", "A pharmacy, seller, prescriber, diagnostic tool, dosing advisor or emergency service. Payments and partnerships never influence results.");

// 4
slide = content("Search explains itself and labels every price", "Show that possible matches are separated, and that a ceiling price is labelled as a legal maximum.");
framed(slide, "search", 0.6, 1.6, 6.2, 3.8, "Search results for a misspelt medicine, showing possible matches with reasons");
text(slide, "A typo finds possible matches, each with its reason and a warning.", { x: 0.6, y: 5.5, w: 6.0, h: 0.9, fontSize: 18 });
framed(slide, "price", 7.1, 1.6, 5.63, 3.8, "Real NPPA ceiling price labelled as a legal maximum and possibly out of date");
text(slide, "A real NPPA ceiling price, labelled as a legal maximum and flagged as possibly out of date.", { x: 7.1, y: 5.5, w: 5.63, h: 0.9, fontSize: 18 });

// 5
slide = content("A person confirms every medicine before any price appears", "This is the core flow. The look-alike check locks confirmation until it is acknowledged.");
const verify = framed(slide, "verify", 0.6, 1.6, 7.6, 5.2, "Prescription beside extracted fields and candidate medicines, with a look-alike warning");
text(slide, [
  { text: "The image sits beside what was read", options: { bullet: true, breakLine: true } },
  { text: "Unreadable fields say \"Unclear\" or \"Not found\", and are never guessed", options: { bullet: true, breakLine: true } },
  { text: "Candidates explain themselves, and none is pre-selected", options: { bullet: true, breakLine: true } },
  { text: "Look-alike names lock confirmation until checked", options: { bullet: true, breakLine: true } },
  { text: "Personal details are left out of extracted text", options: { bullet: true } },
], { x: 0.6 + verify.w + 0.4, y: 1.7, w: 12.73 - (0.6 + verify.w + 0.4), h: 4.9, fontSize: 18, paraSpaceAfter: 12 });

// 6
slide = content("The server refuses, and emergencies interrupt", "The gate returns a 409 even for direct API calls. Emergency detection works in three languages but is pattern based.");
framed(slide, "gate", 0.6, 1.65, 5.85, 3.3, "Comparison page blocked until the medicine is confirmed");
text(slide, "Unconfirmed item: prices stay hidden, even by direct API call (HTTP 409).", { x: 0.6, y: 5.25, w: 5.85, h: 1.1, fontSize: 18 });
framed(slide, "emergency", 6.88, 1.65, 5.85, 3.3, "Emergency dialog showing a Call 112 button");
text(slide, "Emergency language in search, typing or OCR text shows 112, in English, Hindi and Tamil.", { x: 6.88, y: 5.25, w: 5.85, h: 1.1, fontSize: 18 });

// 7
slide = content("A modular monolith, with OCR isolated in a worker", "Safety, matching and pricing are pure, strictly typed modules.");
slide.addImage({ path: path.join(ROOT, "portfolio/demo/slides/container.png"), x: 0.6, y: 1.55, ...JSON.parse(fs.readFileSync(path.join(ROOT, "portfolio/demo/slides/sizes.json"))).containerFit, altText: "Container diagram of the system" });
card(slide, 8.3, 1.7, 4.43, 2.2, "Pure core", "Safety, matching and pricing depend on no web or database code.");
card(slide, 8.3, 4.15, 4.43, 2.4, "Provenance", `${m.catalogue_real} real NPPA rows with batch and row links. ${m.review_queue} sent to review, not guessed.`);

// 8
slide = content("Safety rules are enforced in code, and tested", `${m.safety_tests} tests in the safety suite.`);
const rows = [
  ["Rule", "How it is enforced"],
  ["Unverified items never reach comparison", "Server gate, database constraint, API bypass tests"],
  ["Similar names are not the same medicine", "Equivalence takes attributes, never names"],
  ["An unstated salt form proves nothing", "Refused, with the reason shown"],
  ["Nothing is guessed", "Fields are visible, unclear or unknown"],
  ["Text in files is data, not instructions", "No instruction channel exists in the pipeline"],
  ["A ceiling price is not a shop price", "Labelled, and no savings across price types"],
].map((row, index) => row.map((cell) => ({ text: cell, options: index === 0 ? { bold: true, color: WHITE, fill: { color: INDIGO } } : { color: INK, fill: { color: index % 2 ? WHITE : TINT } } })));
slide.addTable(rows, { x: 0.6, y: 1.6, w: 12.13, colW: [5.6, 6.53], fontSize: 16, rowH: 0.62, valign: "middle", border: { type: "none" }, margin: [0, 0.12, 0, 0.12], objectName: "Safety rules" });

// 9
slide = content("On synthetic data, about 1 in 5 raw top matches was wrong", "This is why a person must confirm. Synthetic handwriting is easier than the real thing, so these numbers do not show real-world accuracy.");
slide.addChart(pres.charts.BAR, [
  { name: m.selected_engine, labels: ["No thresholds", "Calibrated"], values: [s.unfiltered_fmr, s.fmr] },
  { name: m.other_engine, labels: ["No thresholds", "Calibrated"], values: [o.unfiltered_fmr, o.fmr] },
], {
  x: 0.6, y: 1.55, w: 6.9, h: 4.9, barDir: "col", barGrouping: "clustered", chartColors: ["2A78D6", "EB6834"], showTitle: true, title: "False-match rate, test split (%)",
  titleFontSize: 14, titleColor: INK, titleFontFace: "+mn-lt", showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 13, dataLabelColor: INK, dataLabelFontFace: "+mn-lt", dataLabelFormatCode: "0.0",
  showLegend: true, legendPos: "b", legendFontSize: 13, legendColor: MUTED, legendFontFace: "+mn-lt", catAxisLabelColor: MUTED, catAxisLabelFontSize: 13, catAxisLabelFontFace: "+mn-lt", valAxisHidden: true, valGridLine: { style: "none" }, catGridLine: { style: "none" }, valAxisMinVal: 0,
});
stat(slide, 8.0, 1.6, 2.2, `${s.false_matches}/${s.suggested}`, `false matches, ${m.selected_engine}, calibrated`);
stat(slide, 10.5, 1.6, 2.2, `${s.coverage}%`, "of readable lines get a suggestion");
slide.addShape(pres.ShapeType.roundRect, { x: 8.0, y: 3.75, w: 4.73, h: 2.7, fill: { color: AMBER_TINT }, line: { color: AMBER_TINT }, rectRadius: 0.08, objectName: "Limitation callout" });
text(slide, `Synthetic fonts are easier than real handwriting. This does not show real-world accuracy. The 95% upper bound is ${s.fmr_upper}%. The engines cannot be told apart at this sample size.`, { x: 8.22, y: 3.92, w: 4.3, h: 2.4, fontSize: 16, color: "78350F" });

// 10
slide = content(`${m.gates_passed} of ${m.gates_total} automated gates pass from one command`, "Numbers are from VERIFICATION_REPORT.md. The load test ran on one laptop and is not a production capacity figure.");
stat(slide, 0.6, 1.7, 2.8, String(m.backend_tests), `backend tests, ${m.backend_coverage}% coverage`);
stat(slide, 3.7, 1.7, 2.8, String(m.safety_tests), "safety invariant tests");
stat(slide, 6.8, 1.7, 2.8, String(m.e2e_tests), "end-to-end runs with axe, on two viewports");
stat(slide, 9.9, 1.7, 2.8, `${m.search_p95} ms`, `search p95, local load test, ${m.perf_failures} failures`);
card(slide, 0.6, 3.9, 12.13, 2.5, "Testing caught real mistakes", "Partial words classed as exact matches (\"met\" for metformin and metoprolol). Demo accounts that could not sign in. Rate limits that would have grouped all users as one address. A virtual environment copied into images, more than doubling their size.");

// 11
slide = content("What is not done yet matters most", "State these without being asked.");
card(slide, 0.6, 1.7, 5.9, 2.3, "Data", "Shop prices are fictional. Real data is NPPA's legal maximums for part of the market. Jan Aushadhi data needs PMBI's permission.", AMBER_TINT);
card(slide, 6.83, 1.7, 5.9, 2.3, "Evidence", "No real handwriting evaluation. No users, no user research and no measured savings.", AMBER_TINT);
card(slide, 0.6, 4.25, 5.9, 2.3, "Review", "No legal review, including whether this is medical device software. Hindi and Tamil need native review.", AMBER_TINT);
card(slide, 6.83, 4.25, 5.9, 2.3, "Operations", "Not deployed. CI has not run on GitHub. No penetration test, and no test on a real low-end phone.", AMBER_TINT);

// 12
slide = pres.addSlide({ masterName: "DARK" });
slide.addText("What comes next", { placeholder: "title" });
["Get real shop prices, and permission from PMBI", "Get legal review, starting with device classification", "Run a consented, ethics-approved real-data evaluation", "Test with pharmacists and patients"].forEach((item, index) => {
  slide.addShape(pres.ShapeType.ellipse, { x: 0.8, y: 2.95 + index * 0.85, w: 0.55, h: 0.55, fill: { color: WHITE }, line: { color: WHITE }, objectName: `Step ${index + 1}` });
  text(slide, String(index + 1), { x: 0.8, y: 2.95 + index * 0.85, w: 0.55, h: 0.55, fontSize: 18, bold: true, align: "center", valign: "middle", color: C.text2 });
  text(slide, item, { x: 1.6, y: 2.95 + index * 0.85, w: 10.5, h: 0.55, fontSize: 22, valign: "middle", color: C.background1 });
});

(async () => {
  const output = path.join(ROOT, "portfolio/deck.pptx");
  await pres.writeFile({ fileName: output });
  if (process.argv[2]) await require(process.argv[2]).applyTheme(output, THEME);
  console.log("wrote", output);
})();
