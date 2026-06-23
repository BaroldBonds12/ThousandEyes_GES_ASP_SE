#!/usr/bin/env node
/**
 * Fetches configured RSS feeds and writes docs/data/feed.json.
 * Used locally and in GitHub Actions (update-feed.yml).
 */

import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import Parser from 'rss-parser';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');
const CONFIG_PATH = join(ROOT, 'feeds.config.json');
const OUTPUT_PATH = join(ROOT, 'docs', 'data', 'feed.json');

const parser = new Parser({
  timeout: 15000,
  headers: {
    'User-Agent': 'ThousandEyes-SE-Hub-FeedBot/1.0'
  }
});

function loadConfig() {
  return JSON.parse(readFileSync(CONFIG_PATH, 'utf8'));
}

function loadExistingFeed() {
  try {
    return JSON.parse(readFileSync(OUTPUT_PATH, 'utf8'));
  } catch {
    return { updatedAt: null, items: [] };
  }
}

function normalizeDate(entry) {
  const raw = entry.isoDate || entry.pubDate || entry.published;
  if (!raw) return null;
  const d = new Date(raw);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

async function fetchFeed(feed) {
  const timeoutMs = 12000;
  try {
    const result = await Promise.race([
      parser.parseURL(feed.url),
      new Promise(function (_, reject) {
        setTimeout(function () { reject(new Error('timeout')); }, timeoutMs);
      })
    ]);
    return (result.items || []).map((item) => ({
      title: (item.title || 'Untitled').trim(),
      url: (item.link || item.guid || '').trim(),
      source: feed.name,
      published: normalizeDate(item),
      topics: feed.topics || []
    })).filter((item) => item.url);
  } catch (err) {
    console.warn(`Failed to fetch ${feed.name} (${feed.url}): ${err.message}`);
    return [];
  }
}

function dedupeAndSort(items, maxItems) {
  const seen = new Set();
  const unique = [];

  for (const item of items) {
    if (seen.has(item.url)) continue;
    seen.add(item.url);
    unique.push(item);
  }

  unique.sort((a, b) => {
    const ta = a.published ? new Date(a.published).getTime() : 0;
    const tb = b.published ? new Date(b.published).getTime() : 0;
    return tb - ta;
  });

  return unique.slice(0, maxItems);
}

async function main() {
  const config = loadConfig();
  const existing = loadExistingFeed();
  const maxItems = config.maxItems || 30;

  const results = [];
  for (const feed of config.feeds || []) {
    results.push(await fetchFeed(feed));
  }

  const fresh = results.flat();
  let items;

  if (fresh.length > 0) {
    items = dedupeAndSort(fresh, maxItems);
  } else if (existing.items?.length) {
    console.warn('All feeds failed — keeping existing items');
    items = existing.items;
  } else {
    items = [];
  }

  const output = {
    updatedAt: new Date().toISOString(),
    items
  };

  writeFileSync(OUTPUT_PATH, JSON.stringify(output, null, 2) + '\n');
  console.log(`Wrote ${items.length} items to ${OUTPUT_PATH}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
