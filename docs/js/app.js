(function () {
  'use strict';

  const REPO_BASE = 'https://github.com/BaroldBonds12/ThousandEyes_GES_ASP_SE';
  const ISSUE_NEW_PROJECT = REPO_BASE + '/issues/new?template=new-project.yml';

  const CATEGORIES = {
    all: { label: 'All Projects', badge: 'badge-blue' },
    workproduct: { label: 'Workproduct', badge: 'badge-blue' },
    workflow: { label: 'Workflow', badge: 'badge-green' },
    discovery: { label: 'Discovery', badge: 'badge-purple' },
    automation: { label: 'Automation', badge: 'badge-yellow' },
    showcase: { label: 'Showcase', badge: 'badge-red' }
  };

  const STATUS_BADGE = {
    active: 'badge-green',
    beta: 'badge-yellow',
    archived: 'badge-red'
  };

  const TOPIC_LABELS = {
    ai: 'AI',
    networking: 'Networking',
    observability: 'Observability',
    monitoring: 'Monitoring',
    development: 'Development'
  };

  let projects = [];
  let feedItems = [];
  let activeCategory = 'all';
  let activeTopic = 'all';
  let searchQuery = '';

  function repoUrl(path) {
    if (!path) return REPO_BASE;
    if (path.startsWith('http')) return path;
    return REPO_BASE + (path.startsWith('/') ? '' : '/') + path.replace(/^BaroldBonds12\/ThousandEyes_GES_ASP_SE\/?/, '');
  }

  function formatDate(iso) {
    if (!iso) return '';
    try {
      return new Date(iso).toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
      });
    } catch {
      return '';
    }
  }

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  function renderMetrics() {
    const total = projects.length;
    const featured = projects.filter(function (p) { return p.featured; }).length;
    const active = projects.filter(function (p) { return p.status === 'active'; }).length;
    const categories = new Set(projects.map(function (p) { return p.category; })).size;

    document.getElementById('metric-total').textContent = total;
    document.getElementById('metric-featured').textContent = featured;
    document.getElementById('metric-active').textContent = active;
    document.getElementById('metric-categories').textContent = categories;
  }

  function renderCategoryTabs() {
    const container = document.getElementById('category-tabs');
    container.innerHTML = '';

    Object.keys(CATEGORIES).forEach(function (key) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'tab' + (key === activeCategory ? ' active' : '');
      btn.textContent = CATEGORIES[key].label;
      btn.dataset.category = key;
      btn.addEventListener('click', function () {
        activeCategory = key;
        renderCategoryTabs();
        renderProjects();
      });
      container.appendChild(btn);
    });
  }

  function filteredProjects() {
    return projects.filter(function (p) {
      if (activeCategory !== 'all' && p.category !== activeCategory) return false;
      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        const haystack = [
          p.name,
          p.description,
          p.category,
          (p.tags || []).join(' ')
        ].join(' ').toLowerCase();
        if (haystack.indexOf(q) === -1) return false;
      }
      return true;
    });
  }

  function renderProjects() {
    const grid = document.getElementById('project-grid');
    const empty = document.getElementById('projects-empty');
    const list = filteredProjects();

    if (list.length === 0) {
      grid.innerHTML = '';
      empty.classList.remove('hidden');
      return;
    }

    empty.classList.add('hidden');
    grid.innerHTML = list.map(function (p) {
      const cat = CATEGORIES[p.category] || CATEGORIES.all;
      const statusClass = STATUS_BADGE[p.status] || 'badge-blue';
      const tags = (p.tags || []).map(function (t) {
        return '<span class="tag">' + escapeHtml(t) + '</span>';
      }).join('');

      const links = [];
      if (p.repo) {
        links.push('<a href="' + escapeHtml(repoUrl(p.repo)) + '" target="_blank" rel="noopener noreferrer">View repo</a>');
      }
      if (p.demo) {
        links.push('<a href="' + escapeHtml(p.demo) + '" target="_blank" rel="noopener noreferrer">Demo</a>');
      }

      return (
        '<article class="project-card' + (p.featured ? ' featured' : '') + '">' +
          '<div class="project-header">' +
            '<div class="project-name">' + escapeHtml(p.name) + '</div>' +
            '<span class="badge ' + statusClass + '">' + escapeHtml(p.status) + '</span>' +
          '</div>' +
          '<span class="badge ' + cat.badge + '" style="align-self:flex-start;margin-bottom:10px;">' + escapeHtml(cat.label) + '</span>' +
          '<p class="project-desc">' + escapeHtml(p.description) + '</p>' +
          '<div class="project-tags">' + tags + '</div>' +
          '<div class="project-footer">' +
            '<span class="maintainers">' + escapeHtml((p.maintainers || []).join(', ')) + '</span>' +
            '<span>' + links.join(' · ') + '</span>' +
          '</div>' +
        '</article>'
      );
    }).join('');
  }

  function renderTopicChips() {
    const container = document.getElementById('topic-chips');
    container.innerHTML = '';

    const allBtn = document.createElement('button');
    allBtn.type = 'button';
    allBtn.className = 'topic-chip' + (activeTopic === 'all' ? ' active' : '');
    allBtn.textContent = 'All topics';
    allBtn.addEventListener('click', function () {
      activeTopic = 'all';
      renderTopicChips();
      renderFeed();
    });
    container.appendChild(allBtn);

    Object.keys(TOPIC_LABELS).forEach(function (key) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'topic-chip' + (activeTopic === key ? ' active' : '');
      btn.textContent = TOPIC_LABELS[key];
      btn.addEventListener('click', function () {
        activeTopic = key;
        renderTopicChips();
        renderFeed();
      });
      container.appendChild(btn);
    });
  }

  function filteredFeed() {
    if (activeTopic === 'all') return feedItems;
    return feedItems.filter(function (item) {
      return (item.topics || []).indexOf(activeTopic) !== -1;
    });
  }

  function renderFeed() {
    const list = document.getElementById('feed-list');
    const empty = document.getElementById('feed-empty');
    const updated = document.getElementById('feed-updated');
    const items = filteredFeed();

    if (feedUpdatedAt) {
      updated.textContent = 'Last updated: ' + formatDate(feedUpdatedAt);
    } else {
      updated.textContent = 'Feed refreshes daily via GitHub Actions';
    }

    if (items.length === 0) {
      list.innerHTML = '';
      empty.classList.remove('hidden');
      return;
    }

    empty.classList.add('hidden');
    list.innerHTML = items.slice(0, 20).map(function (item) {
      const topics = (item.topics || []).map(function (t) {
        const label = TOPIC_LABELS[t] || t;
        return '<span class="badge badge-blue">' + escapeHtml(label) + '</span>';
      }).join(' ');

      return (
        '<div class="feed-item">' +
          '<a class="feed-title" href="' + escapeHtml(item.url) + '" target="_blank" rel="noopener noreferrer">' +
            escapeHtml(item.title) +
          '</a>' +
          '<div class="feed-meta">' +
            '<span>' + escapeHtml(item.source) + '</span>' +
            '<span>' + formatDate(item.published) + '</span>' +
            topics +
          '</div>' +
        '</div>'
      );
    }).join('');
  }

  let feedUpdatedAt = null;

  function initSearch() {
    const input = document.getElementById('project-search');
    input.addEventListener('input', function (e) {
      searchQuery = e.target.value.trim();
      renderProjects();
    });
  }

  function initCtaLinks() {
    document.querySelectorAll('[data-issue-link]').forEach(function (el) {
      el.href = ISSUE_NEW_PROJECT;
    });
    document.querySelectorAll('[data-contrib-link]').forEach(function (el) {
      el.href = REPO_BASE + '/blob/main/CONTRIBUTING.md';
    });
  }

  async function loadData() {
    try {
      const [projectsRes, feedRes] = await Promise.all([
        fetch('data/projects.json'),
        fetch('data/feed.json')
      ]);

      if (projectsRes.ok) {
        const data = await projectsRes.json();
        projects = data.projects || [];
      }

      if (feedRes.ok) {
        const data = await feedRes.json();
        feedItems = data.items || [];
        feedUpdatedAt = data.updatedAt;
      }
    } catch (err) {
      console.warn('Failed to load hub data:', err);
    }

    renderMetrics();
    renderCategoryTabs();
    renderProjects();
    renderTopicChips();
    renderFeed();
  }

  document.addEventListener('DOMContentLoaded', function () {
    initSearch();
    initCtaLinks();
    loadData();
  });
})();
