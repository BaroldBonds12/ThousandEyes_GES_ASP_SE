#!/usr/bin/env node
/**
 * Fetches configured RSS feeds and writes docs/data/feed.json.
 * Sections: industry, cisco, thousandeyes (blog + changelog).
 */

import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import Parser from 'rss-parser';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');
const CONFIG_PATH = join(ROOT, 'feeds.config.json');
const OUTPUT_PATH = join(ROOT, 'docs', 'data', 'feed.json');

const BROWSER_UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36';

const parser = new Parser({
  timeout: 15000,
  headers: { 'User-Agent': 'ThousandEyes-SE-Hub-FeedBot/1.0' }
});

function loadConfig() {
  return JSON.parse(readFileSync(CONFIG_PATH, 'utf8'));
}

function loadExistingFeed() {
  try {
    return JSON.parse(readFileSync(OUTPUT_PATH, 'utf8'));
  } catch {
    return { updatedAt: null, industry: { items: [] }, cisco: { items: [] }, thousandeyes: { items: [] } };
  }
}

function normalizeDate(raw) {
  if (!raw) return null;
  const d = new Date(raw);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

function dedupeAndSort(items, maxItems) {
  const seen = new Set();
  const unique = [];

  for (const item of items) {
    if (!item.url || seen.has(item.url)) continue;
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

async function fetchRssFeed(feed, extraFields = {}) {
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
      published: normalizeDate(item.isoDate || item.pubDate || item.published),
      topics: feed.topics || [],
      ...extraFields
    })).filter((item) => item.url);
  } catch (err) {
    console.warn(`Failed to fetch ${feed.name} (${feed.url}): ${err.message}`);
    return [];
  }
}

async function fetchSectionFeeds(feeds, maxItems, extraFields = {}) {
  const results = [];
  for (const feed of feeds || []) {
    results.push(await fetchRssFeed(feed, extraFields));
  }
  return dedupeAndSort(results.flat(), maxItems);
}

async function fetchHtml(url) {
  const res = await fetch(url, {
    headers: {
      'User-Agent': BROWSER_UA,
      Accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
      'Accept-Language': 'en-US,en;q=0.9'
    },
    signal: AbortSignal.timeout(15000)
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.text();
}

function extractMeta(html, property) {
  const re = new RegExp(
    '<meta[^>]+(?:property|name)="' + property + '"[^>]+content="([^"]+)"',
    'i'
  );
  const match = html.match(re);
  if (match) return match[1];
  const re2 = new RegExp(
    '<meta[^>]+content="([^"]+)"[^>]+(?:property|name)="' + property + '"',
    'i'
  );
  const match2 = html.match(re2);
  return match2 ? match2[1] : null;
}

function slugToTitle(slug) {
  return slug
    .split('-')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

async function fetchThousandEyesBlog(config) {
  const listingUrl = config.blogListingUrl || 'https://www.thousandeyes.com/blog/';
  const maxPosts = config.blogMaxPosts || 8;
  const exclude = new Set(['author', 'index', 'success', 'category', 'tag']);

  try {
    const html = await fetchHtml(listingUrl);
    const slugs = new Set();

    for (const match of html.matchAll(/href="(\/blog\/([a-z0-9-]+))"/gi)) {
      const slug = match[2];
      if (exclude.has(slug) || slug.startsWith('author')) continue;
      slugs.add(slug);
    }

    const items = [];
    for (const slug of [...slugs].slice(0, maxPosts + 5)) {
      if (items.length >= maxPosts) break;
      const url = `https://www.thousandeyes.com/blog/${slug}`;
      try {
        const postHtml = await fetchHtml(url);
        const title = extractMeta(postHtml, 'og:title') || slugToTitle(slug);
        const publishMs = extractMeta(postHtml, 'publishDate');
        const published =
          normalizeDate(publishMs ? new Date(Number(publishMs)).toISOString() : null) ||
          normalizeDate(extractMeta(postHtml, 'article:published_time')) ||
          normalizeDate(extractMeta(postHtml, 'og:updated_time'));
        items.push({
          title: title.replace(/\s*\|\s*ThousandEyes.*$/i, '').trim(),
          url,
          source: 'ThousandEyes Blog',
          published,
          type: 'blog'
        });
      } catch (err) {
        console.warn(`Failed to fetch TE blog post ${slug}: ${err.message}`);
        items.push({
          title: slugToTitle(slug),
          url,
          source: 'ThousandEyes Blog',
          published: null,
          type: 'blog'
        });
      }
    }

    return items;
  } catch (err) {
    console.warn(`Failed to fetch TE blog listing: ${err.message}`);
    return [];
  }
}

function parseChangelogMarkdown(md) {
  const items = [];
  const lines = md.split('\n');
  let currentDate = null;
  let currentHeading = null;
  const changelogBase = 'https://docs.thousandeyes.com/whats-new/changelog';

  for (const line of lines) {
    const dateMatch = line.match(/^##\s+(\d{4}-\d{2}-\d{2})\s*$/);
    if (dateMatch) {
      if (currentHeading && currentDate) {
        items.push(buildChangelogItem(currentDate, currentHeading, changelogBase));
      }
      currentDate = dateMatch[1];
      currentHeading = `Changelog — ${currentDate}`;
      continue;
    }

    const sectionMatch = line.match(/^###\s+(.+)$/);
    if (sectionMatch && currentDate) {
      if (currentHeading && currentHeading !== `Changelog — ${currentDate}`) {
        items.push(buildChangelogItem(currentDate, currentHeading, changelogBase));
      }
      currentHeading = sectionMatch[1].trim();
    }
  }

  if (currentHeading && currentDate) {
    items.push(buildChangelogItem(currentDate, currentHeading, changelogBase));
  }

  return items;
}

function buildChangelogItem(date, title, baseUrl) {
  const anchor = title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');
  return {
    title,
    url: `${baseUrl}#${anchor}`,
    source: 'Release Notes',
    published: normalizeDate(date),
    type: 'release'
  };
}

async function fetchThousandEyesChangelog(config) {
  const url = config.changelogUrl || 'https://docs.thousandeyes.com/whats-new/changelog.md';
  try {
    const res = await fetch(url, {
      headers: { 'User-Agent': 'ThousandEyes-SE-Hub-FeedBot/1.0' },
      signal: AbortSignal.timeout(15000)
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const md = await res.text();
    return parseChangelogMarkdown(md).slice(0, 10);
  } catch (err) {
    console.warn(`Failed to fetch TE changelog: ${err.message}`);
    return [];
  }
}

async function fetchThousandEyesSection(config, maxItems) {
  const [blogItems, changelogItems] = await Promise.all([
    fetchThousandEyesBlog(config),
    fetchThousandEyesChangelog(config)
  ]);
  return dedupeAndSort([...blogItems, ...changelogItems], maxItems);
}

function sectionItems(existing, key) {
  if (existing[key]?.items) return existing[key].items;
  if (Array.isArray(existing[key])) return existing[key];
  if (Array.isArray(existing.items) && key === 'industry') return existing.items;
  return [];
}

async function main() {
  const config = loadConfig();
  const existing = loadExistingFeed();
  const max = config.maxItems || { industry: 25, cisco: 15, thousandeyes: 15 };

  const industry = await fetchSectionFeeds(config.industry, max.industry || 25);
  const cisco = await fetchSectionFeeds(config.cisco, max.cisco || 15, { type: 'article' });

  let thousandeyes = [];
  if (config.thousandeyes) {
    thousandeyes = await fetchThousandEyesSection(config.thousandeyes, max.thousandeyes || 15);
  }

  const output = {
    updatedAt: new Date().toISOString(),
    industry: {
      items: industry.length ? industry : sectionItems(existing, 'industry')
    },
    cisco: {
      items: cisco.length ? cisco : sectionItems(existing, 'cisco')
    },
    thousandeyes: {
      items: thousandeyes.length ? thousandeyes : sectionItems(existing, 'thousandeyes')
    }
  };

  if (!industry.length && sectionItems(existing, 'industry').length) {
    console.warn('Industry feeds failed — keeping existing items');
  }
  if (!cisco.length && sectionItems(existing, 'cisco').length) {
    console.warn('Cisco feeds failed — keeping existing items');
  }
  if (!thousandeyes.length && sectionItems(existing, 'thousandeyes').length) {
    console.warn('ThousandEyes feeds failed — keeping existing items');
  }

  writeFileSync(OUTPUT_PATH, JSON.stringify(output, null, 2) + '\n');
  console.log(
    `Wrote feeds: industry=${output.industry.items.length}, cisco=${output.cisco.items.length}, thousandeyes=${output.thousandeyes.items.length}`
  );
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
