/// <reference types="vite/client" />
/**
 * Home-route + service-worker freshness guards (owner live test 2026-09-08).
 *
 * The owner opened the server root (`/`) and got the app's own 404 page —
 * the route table started at /beanie and fell through to NotFoundPage.
 * Home is the conversation (charter §5): `/` must redirect to /chat.
 *
 * The service worker also served a stale cached shell after rebuilds (old
 * hashed asset names 404'd), so navigations must be NETWORK-FIRST and the
 * cache name must be bumped so every client's stale cache is deleted.
 */
import { describe, it, expect } from 'vitest';
import appSource from '../App.tsx?raw';
import swSource from '../../public/sw.js?raw';

describe('home route', () => {
  it('routes `/` (redirect to the conversation) before the catch-all', () => {
    expect(appSource).toMatch(/path="\/"\s+element=\{<Navigate to="\/chat" replace \/>}/);
    const rootRouteIndex = appSource.indexOf('path="/"');
    const catchAllIndex = appSource.indexOf('path="*"');
    expect(rootRouteIndex).toBeGreaterThan(-1);
    expect(catchAllIndex).toBeGreaterThan(rootRouteIndex);
  });
});

describe('service worker freshness', () => {
  it('bumps the cache name so stale caches are deleted on activate', () => {
    expect(swSource).toMatch(/CACHE_NAME = 'arena-v2'/);
  });

  it('is network-first for navigations (shell always fresh when online)', () => {
    const navigateBranch = swSource.slice(
      swSource.indexOf("request.mode === 'navigate'"),
      swSource.indexOf("url.pathname.startsWith('/assets/')"),
    );
    expect(navigateBranch).toContain('fetch(request)');
    // Network resolves FIRST; the cached shell is only the offline fallback.
    const fetchPos = navigateBranch.indexOf('fetch(request)');
    const cacheFallbackPos = navigateBranch.indexOf("caches.match('/index.html')");
    expect(fetchPos).toBeGreaterThan(-1);
    expect(cacheFallbackPos).toBeGreaterThan(fetchPos);
  });

  it('keeps immutable build assets cache-first', () => {
    const assetsBranch = swSource.slice(swSource.indexOf("url.pathname.startsWith('/assets/')"));
    const cachePos = assetsBranch.indexOf('caches.match(request)');
    const fetchPos = assetsBranch.indexOf('fetch(request)');
    expect(cachePos).toBeGreaterThan(-1);
    expect(fetchPos).toBeGreaterThan(cachePos);
  });
});
