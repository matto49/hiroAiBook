import fs from "node:fs";
import path from "node:path";
import { chromium } from "/Users/matto/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs";

const root = "/Users/matto/github/person/hiroAiBook/docs/claude code/visual-articles";
const articles = [
  {
    slug: "end-to-end-workflow",
    url: "https://y-agent.github.io/inside-claude-code/01-end-to-end-workflow.html",
  },
  {
    slug: "multi-agent-orchestration",
    url: "https://y-agent.github.io/inside-claude-code/07-multi-agent-orchestration.html",
  },
];

const browser = await chromium.launch({
  headless: true,
  executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
});
const context = await browser.newContext({
  viewport: { width: 1800, height: 1400 },
  deviceScaleFactor: 2,
});

for (const article of articles) {
  const assets = path.join(root, article.slug, "assets");
  const manifest = JSON.parse(fs.readFileSync(path.join(assets, "manifest.json"), "utf8"));
  const figures = manifest.filter((item) => item.kind === "mermaid");
  const page = await context.newPage();
  await page.goto(article.url, { waitUntil: "networkidle", timeout: 120000 });
  await page.waitForSelector("main figure svg", { state: "visible", timeout: 120000 });
  const rendered = page.locator("main figure");
  const count = await rendered.count();
  if (count !== figures.length) {
    throw new Error(`${article.slug}: expected ${figures.length} figures, found ${count}`);
  }
  for (let index = 0; index < count; index += 1) {
    const figure = rendered.nth(index);
    const diagram = figure.locator(":scope > div").first();
    await diagram.scrollIntoViewIfNeeded();
    await diagram.screenshot({
      path: path.join(assets, figures[index].file),
      animations: "disabled",
    });
  }
  await page.close();
}

await browser.close();
