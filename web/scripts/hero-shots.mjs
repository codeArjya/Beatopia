// Screenshots of the scroll hero, and the still image that phones and reduced-motion visitors see.
//
// Playwright is not a dependency of this app. Install it anywhere once, then point this script at it:
//   mkdir -p /tmp/pw && cd /tmp/pw && npm init -y && npm i playwright-core && npx playwright-core install chromium
//   cd web && pnpm dev            (in another terminal)
//   PLAYWRIGHT_DIR=/tmp/pw node scripts/hero-shots.mjs                 # 0/30/60/85/100% + 390px wide
//   PLAYWRIGHT_DIR=/tmp/pw node scripts/hero-shots.mjs --still         # re-capture public/hero/sampler-still.jpg
//
// Options: --url http://localhost:3000   --out docs/screenshots/hero   --headed   --at 0,30,60,85,100
//          --size 1440x900 (desktop viewport)
//
// Re-run with --still after changing the device, its colors, the assembled camera pose or the backdrop.

import { mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const web = path.join(here, "..");
const requireFrom = createRequire(
  process.env.PLAYWRIGHT_DIR ? path.join(path.resolve(process.env.PLAYWRIGHT_DIR), "index.js") : import.meta.url,
);
const { chromium } = requireFrom("playwright-core");

const args = process.argv.slice(2);
const option = (name, fallback) => {
  const index = args.indexOf(`--${name}`);
  return index >= 0 && args[index + 1] ? args[index + 1] : fallback;
};
const url = option("url", "http://localhost:3000");
const out = path.resolve(web, option("out", "docs/screenshots/hero"));
const stops = option("at", "0,30,60,85,100").split(",").map(Number);
const still = args.includes("--still");
const [sizeWidth, sizeHeight] = option("size", "1440x900").split("x").map(Number);
const DESKTOP = { width: sizeWidth, height: sizeHeight };

const browser = await chromium.launch({
  channel: "chromium",
  headless: !args.includes("--headed"),
  // Use the real GPU, so the frames match what a visitor's laptop draws.
  args: ["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist", "--enable-webgl"],
});

const problems = [];
const watch = (page, label) => {
  page.on("console", (message) => {
    if (message.type() === "error") problems.push(`[${label}] console error: ${message.text()}`);
  });
  page.on("pageerror", (error) => problems.push(`[${label}] page error: ${error.message}`));
};
const sideways = (page) =>
  page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
const waitForCanvas = (page) => page.waitForSelector('[data-hero-canvas="ready"]', { timeout: 60_000 });

/** Scrolls to a fraction of the pinned hero (0 = pin starts, 1 = pin ends) and lets the scrub settle. */
async function scrollHero(page, fraction) {
  await page.evaluate((f) => {
    const section = document.querySelector("section[aria-labelledby='hero-title']");
    const stage = section.querySelector("[data-hero-stage]");
    const top = section.getBoundingClientRect().top + window.scrollY;
    const start = top - (parseFloat(getComputedStyle(stage).top) || 0);
    const end = top + section.offsetHeight - window.innerHeight;
    window.scrollTo(0, start + (end - start) * f);
  }, fraction);
  await page.waitForTimeout(2200);
}

mkdirSync(out, { recursive: true });

if (still) {
  // The still is a crop of the real assembled scene, time and grain frozen (?hero-still), text hidden.
  const context = await browser.newContext({ viewport: DESKTOP, deviceScaleFactor: 2 });
  const page = await context.newPage();
  watch(page, "still");
  await page.goto(`${url}/?hero-still`, { waitUntil: "networkidle" });
  await waitForCanvas(page);
  await page.addStyleTag({
    content: "[data-hero-stage] > div:nth-child(2), [data-hero-line], [data-hero-dot] { visibility: hidden !important }",
  });
  await page.waitForTimeout(1500);
  // The exact square the still image occupies in the layout, so the canvas later fades in right over it.
  const slot = await page.evaluate(() => {
    const rect = document.querySelector("[data-hero-still]").getBoundingClientRect();
    return { x: rect.x, y: rect.y, side: rect.height };
  });
  const side = Math.round(slot.side);
  const file = path.join(web, "public/hero/sampler-still.jpg");
  mkdirSync(path.dirname(file), { recursive: true });
  await page.screenshot({
    path: file,
    type: "jpeg",
    quality: 88,
    clip: { x: Math.round(slot.x), y: Math.round(slot.y), width: side, height: side },
  });
  console.log(`still → ${path.relative(web, file)} (${side * 2}px square)`);
  await context.close();
} else {
  const desktop = await browser.newContext({ viewport: DESKTOP, deviceScaleFactor: 1 });
  const page = await desktop.newPage();
  watch(page, "desktop");
  await page.goto(url, { waitUntil: "networkidle" });
  await waitForCanvas(page);
  await page.waitForTimeout(1200);
  for (const stop of stops) {
    await scrollHero(page, stop / 100);
    const file = path.join(out, `desktop-${String(stop).padStart(3, "0")}.jpg`);
    await page.screenshot({ path: file, type: "jpeg", quality: 90 });
    console.log(`${stop}% → ${path.relative(web, file)}  (sideways overflow: ${await sideways(page)}px)`);
  }
  await desktop.close();

  // Phone: no WebGL at all, the still image and the same text, stacked.
  const phone = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
  });
  const mobile = await phone.newPage();
  watch(mobile, "phone");
  await mobile.goto(url, { waitUntil: "networkidle" });
  await mobile.waitForTimeout(800);
  const canvases = await mobile.locator("canvas").count();
  const file = path.join(out, "phone-390.jpg");
  // Just the hero (the search page below it is unchanged).
  await mobile.locator("section[aria-labelledby='hero-title']").screenshot({ path: file, type: "jpeg", quality: 90 });
  console.log(`390px → ${path.relative(web, file)}  (canvases: ${canvases}, sideways overflow: ${await sideways(mobile)}px)`);
  if (canvases > 0) problems.push("[phone] a canvas was created at 390px wide");
  await phone.close();
}

await browser.close();
if (problems.length) {
  console.error(`\n${problems.length} problem(s):\n${problems.join("\n")}`);
  process.exitCode = 1;
} else {
  console.log("\nNo console errors.");
}
