(function () {
  'use strict';

  const REPO_BASE = 'https://github.com/BaroldBonds12/ThousandEyes_GES_ASP_SE';
  const ISSUE_NEW_PROJECT = REPO_BASE + '/issues/new?template=new-project.yml';

  const CATEGORIES = {
    all: { label: 'All', badge: 'badge-blue', color: 'blue', icon: 'A' },
    workproduct: { label: 'Workproduct', badge: 'badge-blue', color: 'blue', icon: 'W' },
    workflow: { label: 'Workflow', badge: 'badge-green', color: 'green', icon: 'F' },
    discovery: { label: 'Discovery', badge: 'badge-purple', color: 'purple', icon: 'D' },
    automation: { label: 'Automation', badge: 'badge-yellow', color: 'orange', icon: 'A' },
    showcase: { label: 'Showcase', badge: 'badge-red', color: 'red', icon: 'S' }
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
  let industryItems = [];
  let ciscoItems = [];
  let teItems = [];
  let activeCategory = 'all';
  let activeTopic = 'all';
  let searchQuery = '';
  let feedUpdatedAt = null;

  function dataUrl(path) {
    return new URL(path, window.location.href).href;
  }

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

  function renderFeaturedTiles() {
    const container = document.getElementById('featured-tiles');
    const featured = projects.filter(function (p) { return p.featured; });

    if (featured.length === 0) {
      container.innerHTML = '<p class="empty-state">No featured projects yet.</p>';
      return;
    }

    container.innerHTML = featured.map(function (p) {
      const cat = CATEGORIES[p.category] || CATEGORIES.all;
      const statusClass = STATUS_BADGE[p.status] || 'badge-blue';
      const tags = (p.tags || []).slice(0, 3).map(function (t) {
        return '<span class="tag">' + escapeHtml(t) + '</span>';
      }).join('');

      const links = [];
      if (p.repo) {
        links.push('<a href="' + escapeHtml(repoUrl(p.repo)) + '" target="_blank" rel="noopener noreferrer">Repo</a>');
      }
      if (p.demo) {
        links.push('<a href="' + escapeHtml(p.demo) + '" target="_blank" rel="noopener noreferrer">Demo</a>');
      }

      return (
        '<article class="featured-tile ' + cat.color + '">' +
          '<div class="featured-tile-icon">' + escapeHtml(cat.icon) + '</div>' +
          '<div class="featured-tile-body">' +
            '<div class="featured-tile-header">' +
              '<h3 class="featured-tile-title">' +
                '<a href="' + escapeHtml(repoUrl(p.repo)) + '" target="_blank" rel="noopener noreferrer">' +
                  escapeHtml(p.name) +
                '</a>' +
              '</h3>' +
              '<span class="badge ' + statusClass + '">' + escapeHtml(p.status) + '</span>' +
            '</div>' +
            '<span class="badge ' + cat.badge + ' featured-tile-cat">' + escapeHtml(cat.label) + '</span>' +
            '<p class="featured-tile-desc">' + escapeHtml(p.description) + '</p>' +
            '<div class="featured-tile-tags">' + tags + '</div>' +
            '<div class="featured-tile-footer">' +
              '<span class="maintainers">' + escapeHtml((p.maintainers || []).join(', ')) + '</span>' +
              '<span>' + links.join(' · ') + '</span>' +
            '</div>' +
          '</div>' +
          '<span class="featured-tile-star" title="Featured">★</span>' +
        '</article>'
      );
    }).join('');
  }

  function renderCategoryTabs() {
    const container = document.getElementById('category-tabs');
    container.innerHTML = '';

    Object.keys(CATEGORIES).forEach(function (key) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'tab' + (key === activeCategory ? ' active' : '');
      btn.textContent = CATEGORIES[key].label;
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
        const haystack = [p.name, p.description, p.category, (p.tags || []).join(' ')].join(' ').toLowerCase();
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
        links.push('<a href="' + escapeHtml(repoUrl(p.repo)) + '" target="_blank" rel="noopener noreferrer">Repo</a>');
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
          '<span class="badge ' + cat.badge + '" style="align-self:flex-start;margin-bottom:8px;">' + escapeHtml(cat.label) + '</span>' +
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
    allBtn.textContent = 'All';
    allBtn.addEventListener('click', function () {
      activeTopic = 'all';
      renderTopicChips();
      renderIndustryFeed();
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
        renderIndustryFeed();
      });
      container.appendChild(btn);
    });
  }

  function filteredIndustry() {
    if (activeTopic === 'all') return industryItems;
    return industryItems.filter(function (item) {
      return (item.topics || []).indexOf(activeTopic) !== -1;
    });
  }

  function renderFeedItems(listEl, emptyEl, items, options) {
    options = options || {};
    const limit = options.limit || 25;
    const showTopics = options.showTopics !== false;

    if (items.length === 0) {
      listEl.innerHTML = '';
      emptyEl.classList.remove('hidden');
      return;
    }

    emptyEl.classList.add('hidden');
    listEl.innerHTML = items.slice(0, limit).map(function (item) {
      const topics = showTopics
        ? (item.topics || []).slice(0, 2).map(function (t) {
            const label = TOPIC_LABELS[t] || t;
            return '<span class="badge badge-blue">' + escapeHtml(label) + '</span>';
          }).join(' ')
        : '';

      const typeBadge = item.type === 'release'
        ? '<span class="badge badge-purple">Release</span>'
        : item.type === 'blog'
          ? '<span class="badge badge-green">Blog</span>'
          : '';

      return (
        '<div class="feed-item">' +
          '<span class="feed-dot"></span>' +
          '<div class="feed-body">' +
            '<a class="feed-title" href="' + escapeHtml(item.url) + '" target="_blank" rel="noopener noreferrer">' +
              escapeHtml(item.title) +
            '</a>' +
            '<div class="feed-meta">' +
              '<span>' + escapeHtml(item.source) + '</span>' +
              '<span>' + formatDate(item.published) + '</span>' +
              typeBadge +
              topics +
            '</div>' +
          '</div>' +
        '</div>'
      );
    }).join('');
  }

  function setUpdatedLabel(elId) {
    const el = document.getElementById(elId);
    if (!el) return;
    el.textContent = feedUpdatedAt ? 'Updated ' + formatDate(feedUpdatedAt) : 'Daily refresh';
  }

  function renderIndustryFeed() {
    renderFeedItems(
      document.getElementById('industry-list'),
      document.getElementById('industry-empty'),
      filteredIndustry()
    );
    setUpdatedLabel('industry-updated');
  }

  function renderCiscoFeed() {
    renderFeedItems(
      document.getElementById('cisco-list'),
      document.getElementById('cisco-empty'),
      ciscoItems,
      { showTopics: false, limit: 15 }
    );
    setUpdatedLabel('cisco-updated');
  }

  function renderTeFeed() {
    renderFeedItems(
      document.getElementById('te-list'),
      document.getElementById('te-empty'),
      teItems,
      { showTopics: false, limit: 15 }
    );
    setUpdatedLabel('te-updated');
  }

  function initFeedCollapse(toggleId, panelId, defaultExpanded) {
    const toggle = document.getElementById(toggleId);
    const panel = document.getElementById(panelId);
    if (!toggle || !panel) return;

    const section = toggle.closest('.feed-section');
    let expanded = defaultExpanded;

    function setExpanded(next) {
      expanded = next;
      section.dataset.collapsed = expanded ? 'false' : 'true';
      toggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
      panel.classList.toggle('hidden', !expanded);
    }

    toggle.addEventListener('click', function () {
      setExpanded(!expanded);
    });

    setExpanded(defaultExpanded);
  }

  function initFeedCollapses() {
    initFeedCollapse('industry-toggle', 'industry-panel', false);
    initFeedCollapse('cisco-toggle', 'cisco-panel', false);
    initFeedCollapse('te-toggle', 'te-panel', false);
  }

  function initSearch() {
    document.getElementById('project-search').addEventListener('input', function (e) {
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

  function initNavigation() {
    const navItems = document.querySelectorAll('.sidebar-nav .nav-item[data-section]');
    const sections = document.querySelectorAll('.dash-section');

    function setActive(sectionId) {
      navItems.forEach(function (item) {
        item.classList.toggle('active', item.dataset.section === sectionId);
      });
    }

    navItems.forEach(function (item) {
      item.addEventListener('click', function () {
        const id = item.dataset.section;
        const target = document.getElementById(id);
        if (target) {
          target.scrollIntoView({ behavior: 'smooth', block: 'start' });
          setActive(id);
        }
      });
    });

    document.querySelectorAll('[data-goto]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        const id = btn.dataset.goto;
        const target = document.getElementById(id);
        if (target) {
          target.scrollIntoView({ behavior: 'smooth', block: 'start' });
          setActive(id);
        }
      });
    });

    if ('IntersectionObserver' in window) {
      const observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            setActive(entry.target.id);
          }
        });
      }, { rootMargin: '-30% 0px -60% 0px', threshold: 0 });

      sections.forEach(function (section) {
        observer.observe(section);
      });
    }
  }

  const FETCH_OPTS = { cache: 'no-store' };

  async function loadDeployInfo() {
    try {
      const res = await fetch(dataUrl('build-info.json'), FETCH_OPTS);
      if (!res.ok) return;
      const info = await res.json();
      const el = document.getElementById('deploy-version');
      if (el && info.version) {
        el.textContent = 'deploy: ' + info.version;
      }
    } catch {
      /* optional */
    }
  }

  function normalizeFeedSection(data, key) {
    if (data[key]?.items) return data[key].items;
    if (Array.isArray(data[key])) return data[key];
    if (Array.isArray(data.items) && key === 'industry') return data.items;
    return [];
  }

  async function loadData() {
    try {
      const [projectsRes, feedRes] = await Promise.all([
        fetch(dataUrl('data/projects.json'), FETCH_OPTS),
        fetch(dataUrl('data/feed.json'), FETCH_OPTS)
      ]);

      if (projectsRes.ok) {
        const data = await projectsRes.json();
        projects = data.projects || [];
      }

      if (feedRes.ok) {
        const data = await feedRes.json();
        industryItems = normalizeFeedSection(data, 'industry');
        ciscoItems = normalizeFeedSection(data, 'cisco');
        teItems = normalizeFeedSection(data, 'thousandeyes');
        feedUpdatedAt = data.updatedAt;
      }
    } catch (err) {
      console.warn('Failed to load hub data:', err);
    }

    renderFeaturedTiles();
    renderCategoryTabs();
    renderProjects();
    renderTopicChips();
    renderIndustryFeed();
    renderCiscoFeed();
    renderTeFeed();
  }

  document.addEventListener('DOMContentLoaded', function () {
    initSearch();
    initCtaLinks();
    initNavigation();
    initFeedCollapses();
    loadDeployInfo();
    loadData();
  });
})();
