<script setup>
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

const stats = [
  { value: '0–100', label: 'Score with a written reasoning' },
  { value: '40', label: 'Best sellers per run' },
  { value: 'Every 6 h', label: 'Scheduled scrape' },
  { value: 'Live', label: 'Deployed on AWS' },
]

const features = [
  {
    icon: '◈',
    title: 'Amazon best sellers',
    text: 'Playwright opens category pages in a real browser and collects price, rating and reviews.',
  },
  {
    icon: '↗',
    title: 'Google Trends',
    text: 'Demand over the past year is read for every product, so a fading fad scores lower.',
  },
  {
    icon: '★',
    title: 'Past winners',
    text: 'Each product is matched against our own history of best sellers by category and keywords.',
  },
  {
    icon: '⚡',
    title: 'LLM or formula',
    text: 'An LLM writes the score and its reasoning; a transparent formula steps in whenever it cannot.',
  },
]

const stack = [
  'FastAPI',
  'PostgreSQL',
  'SQLAlchemy',
  'Alembic',
  'Redis',
  'Celery',
  'Playwright',
  'Vue 3',
  'Pinia',
  'Docker',
  'GitHub Actions',
  'AWS EC2',
]
</script>

<template>
  <div class="landing">
    <header class="nav">
      <div class="brand">
        <span class="dot" aria-hidden="true"></span>
        <span>Trend Radar</span>
      </div>
      <nav v-if="auth.isAuthenticated">
        <RouterLink :to="{ name: 'dashboard' }" class="nav-link">Dashboard →</RouterLink>
      </nav>
      <nav v-else>
        <RouterLink :to="{ name: 'login' }" class="nav-link">Sign in</RouterLink>
        <RouterLink :to="{ name: 'register' }" class="nav-link accent">Create account</RouterLink>
      </nav>
    </header>

    <section class="hero">
      <div>
        <p class="eyebrow">PRODUCT RESEARCH, AUTOMATED</p>
        <h1>Find the next<br /><span class="dim">best seller</span><br />before it peaks.</h1>
        <p class="lead">
          Trend Radar scrapes Amazon best sellers, checks their demand on Google Trends,
          compares them with past winners and scores each one from 0 to 100 — with the
          reasoning written out.
        </p>
        <div class="actions">
          <RouterLink v-if="auth.isAuthenticated" :to="{ name: 'dashboard' }" class="btn primary">
            Open the dashboard
          </RouterLink>
          <template v-else>
            <RouterLink :to="{ name: 'register' }" class="btn primary">Create account</RouterLink>
            <RouterLink :to="{ name: 'login' }" class="btn">Sign in</RouterLink>
          </template>
        </div>
      </div>

      <div class="stats">
        <div v-for="stat in stats" :key="stat.label" class="stat">
          <span class="muted">{{ stat.label }}</span>
          <strong>{{ stat.value }}</strong>
        </div>
      </div>
    </section>

    <section class="section">
      <p class="eyebrow">HOW IT WORKS</p>
      <div class="features">
        <div v-for="feature in features" :key="feature.title" class="feature">
          <p class="icon">{{ feature.icon }}</p>
          <p class="feature-title">{{ feature.title }}</p>
          <p class="muted">{{ feature.text }}</p>
        </div>
      </div>
    </section>

    <section class="section stack">
      <p class="eyebrow">BUILT WITH</p>
      <div class="tags">
        <span v-for="tech in stack" :key="tech" class="tag">{{ tech }}</span>
      </div>
    </section>

    <section class="section cta">
      <div>
        <p class="eyebrow">TRY IT</p>
        <h2>Start a scrape and watch the scores arrive.</h2>
      </div>
      <RouterLink
        :to="auth.isAuthenticated ? { name: 'dashboard' } : { name: 'register' }"
        class="btn primary"
      >
        {{ auth.isAuthenticated ? 'Open the dashboard' : 'Create a free account' }}
      </RouterLink>
    </section>

    <footer class="footer muted">
      <span>Trend Radar</span>
      <a href="https://github.com/bogdan0089/trend-radar" target="_blank" rel="noopener">
        Source on GitHub
      </a>
    </footer>
  </div>
</template>

<style scoped>
.landing {
  width: 100%;
  max-width: 1100px;
  margin: 0 auto;
  padding: 0 24px;
}

.nav {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 24px 0;
}

.brand {
  display: flex;
  align-items: center;
  gap: 9px;
  font-weight: 600;
  font-size: 16px;
}

.dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 10px var(--accent);
}

nav {
  display: flex;
  gap: 20px;
}

.nav-link {
  color: var(--text-muted);
  text-decoration: none;
  font-size: 14px;
}

.nav-link:hover,
.nav-link.accent {
  color: var(--accent);
}

.hero {
  display: grid;
  grid-template-columns: 1.2fr 1fr;
  gap: 56px;
  align-items: center;
  padding: 64px 0 80px;
}

.eyebrow {
  color: var(--text-muted);
  font-size: 11px;
  letter-spacing: 4px;
  margin: 0 0 20px;
}

h1 {
  font-size: clamp(40px, 6vw, 68px);
  line-height: 1;
  letter-spacing: -2px;
  margin: 0 0 24px;
}

.dim {
  color: var(--text-muted);
}

.lead {
  color: var(--text-muted);
  font-size: 15px;
  line-height: 1.7;
  max-width: 460px;
  margin: 0 0 36px;
}

.actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.btn {
  display: inline-block;
  padding: 13px 28px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text);
  text-decoration: none;
  font-weight: 600;
  font-size: 14px;
}

.btn.primary {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}

.btn.primary:hover {
  background: var(--accent-hover);
}

.stats {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 8px 28px;
}

.stat {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 20px 0;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
}

.stat:last-child {
  border-bottom: none;
}

.stat strong {
  font-size: 22px;
  letter-spacing: -0.5px;
}

.section {
  border-top: 1px solid var(--border);
  padding: 56px 0;
}

.features {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1px;
  background: var(--border);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}

.feature {
  background: var(--surface);
  padding: 32px 24px;
  font-size: 13px;
  line-height: 1.6;
}

.icon {
  font-size: 26px;
  color: var(--accent);
  margin: 0 0 18px;
}

.feature-title {
  font-weight: 700;
  font-size: 13px;
  letter-spacing: 1px;
  text-transform: uppercase;
  margin: 0 0 10px;
}

.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.tag {
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text-muted);
  font-size: 13px;
  padding: 6px 14px;
  border-radius: 999px;
}

.cta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 32px;
  flex-wrap: wrap;
}

.cta h2 {
  font-size: clamp(24px, 3vw, 36px);
  letter-spacing: -1px;
  margin: 0;
  max-width: 560px;
}

.footer {
  display: flex;
  justify-content: space-between;
  border-top: 1px solid var(--border);
  padding: 28px 0 40px;
  font-size: 13px;
}

.footer a {
  color: var(--text-muted);
}

@media (max-width: 860px) {
  .hero {
    grid-template-columns: 1fr;
    gap: 36px;
    padding: 32px 0 56px;
  }

  .features {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 520px) {
  .features {
    grid-template-columns: 1fr;
  }
}
</style>
