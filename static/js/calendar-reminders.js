/**
 * LawColab Calendar Reminder System
 * - Polls /calendar/api/reminders every 60 seconds
 * - Fires popup alert modals when an event's reminder window opens
 * - Sends desktop (browser) notifications when permission is granted
 * - Tracks shown reminders in localStorage to avoid duplicates
 * - Queues multiple simultaneous reminders and shows them one at a time
 */
(function () {
  'use strict';

  const POLL_INTERVAL_MS = 60 * 1000; // 1 minute
  const STORAGE_KEY = 'lc_shown_reminders'; // localStorage key
  const SNOOZE_KEY  = 'lc_snoozed_reminders';
  const SNOOZE_MINUTES = 10;

  let reminderQueue = [];
  let isModalOpen   = false;
  let pollTimer     = null;

  // ── localStorage helpers ──────────────────────────────────────────────────
  function getShown() {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}'); } catch { return {}; }
  }
  function markShown(eventId) {
    const shown = getShown();
    shown[eventId] = Date.now();
    // Prune entries older than 7 days
    const cutoff = Date.now() - 7 * 24 * 3600 * 1000;
    Object.keys(shown).forEach(k => { if (shown[k] < cutoff) delete shown[k]; });
    localStorage.setItem(STORAGE_KEY, JSON.stringify(shown));
  }
  function wasShown(eventId) {
    return !!getShown()[eventId];
  }

  function getSnoozed() {
    try { return JSON.parse(localStorage.getItem(SNOOZE_KEY) || '{}'); } catch { return {}; }
  }
  function snoozeEvent(eventId) {
    const s = getSnoozed();
    s[eventId] = Date.now() + SNOOZE_MINUTES * 60 * 1000;
    localStorage.setItem(SNOOZE_KEY, JSON.stringify(s));
  }
  function isSnoozed(eventId) {
    const s = getSnoozed();
    return s[eventId] && Date.now() < s[eventId];
  }
  function clearSnooze(eventId) {
    const s = getSnoozed();
    delete s[eventId];
    localStorage.setItem(SNOOZE_KEY, JSON.stringify(s));
  }

  // ── Browser notification ──────────────────────────────────────────────────
  function requestNotificationPermission() {
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission();
    }
  }

  function sendDesktopNotification(event) {
    if (!('Notification' in window) || Notification.permission !== 'granted') return;
    const opts = {
      body: event.start_display + (event.location ? '\n📍 ' + event.location : ''),
      icon: '/static/img/favicon.ico',
      tag: 'lc-cal-' + event.id,
      requireInteraction: true,
    };
    try {
      const n = new Notification('⚖️ ' + event.type_label + ': ' + event.title, opts);
      n.onclick = () => { window.focus(); window.location.href = event.detail_url; n.close(); };
    } catch (e) { /* ignore */ }
  }

  // ── Icon map ─────────────────────────────────────────────────────────────
  const TYPE_EMOJI = {
    court_date: '⚖️', meeting: '🤝', appointment: '📅', deadline: '⏰', other: '📌'
  };
  const COLOR_MAP = {
    danger: '#dc3545', primary: '#0d6efd', success: '#198754',
    warning: '#ffc107', secondary: '#6c757d'
  };

  // ── Modal rendering ───────────────────────────────────────────────────────
  function buildReminderHTML(event) {
    const now   = Date.now();
    const diff  = event.start_ts - now;
    const mins  = Math.round(diff / 60000);
    let timeMsg = '';
    if (mins <= 0)        timeMsg = '<span class="text-danger fw-bold">Starting now!</span>';
    else if (mins < 60)   timeMsg = `<span class="text-warning fw-bold">In ${mins} minute${mins !== 1 ? 's' : ''}</span>`;
    else if (mins < 1440) { const h = Math.floor(mins/60); const m = mins%60;
                            timeMsg = `<span class="text-primary fw-bold">In ${h}h${m > 0 ? ' '+m+'m' : ''}</span>`; }
    else                  { const d = Math.floor(mins/1440);
                            timeMsg = `<span class="text-info fw-bold">In ${d} day${d !== 1 ? 's' : ''}</span>`; }

    const accent = COLOR_MAP[event.type_color] || '#0d6efd';
    const emoji  = TYPE_EMOJI[event.event_type] || '📌';
    const attendeeStr = event.attendees && event.attendees.length
      ? event.attendees.join(', ') : '';
    const notesBlock = event.notes
      ? `<div class="mt-2 p-2 rounded" style="background:#fff8e1;border-left:3px solid #ffc107;font-size:.85rem;">
           <i class="fas fa-sticky-note text-warning me-1"></i><strong>Notes:</strong> ${escHtml(event.notes)}
         </div>` : '';
    const locationBlock = event.location
      ? `<div><i class="fas fa-map-marker-alt me-1" style="color:${accent};"></i>${escHtml(event.location)}</div>` : '';
    const linkBlock = event.virtual_link
      ? `<div><i class="fas fa-video me-1" style="color:${accent};"></i><a href="${event.virtual_link}" target="_blank" rel="noopener">Join virtual meeting</a></div>` : '';
    const attendeeBlock = attendeeStr
      ? `<div><i class="fas fa-users me-1" style="color:${accent};"></i>${escHtml(attendeeStr)}</div>` : '';

    return `
      <div class="lc-reminder-card" data-event-id="${event.id}">
        <div class="lc-reminder-strip" style="background:${accent};"></div>
        <div class="lc-reminder-body">
          <div class="d-flex align-items-start gap-3 mb-2">
            <div class="lc-reminder-emoji">${emoji}</div>
            <div class="flex-grow-1">
              <div class="lc-reminder-badge" style="background:${accent}20;color:${accent};border:1px solid ${accent}40;">
                ${escHtml(event.type_label)}
              </div>
              <h5 class="lc-reminder-title mt-1 mb-0">${escHtml(event.title)}</h5>
            </div>
          </div>
          <div class="lc-reminder-time mb-2">
            <i class="fas fa-clock me-1"></i>
            ${escHtml(event.start_display)} &nbsp;·&nbsp; ${timeMsg}
          </div>
          <div class="lc-reminder-meta small text-muted">
            ${locationBlock}${linkBlock}${attendeeBlock}
          </div>
          ${notesBlock}
          ${event.description ? `<div class="mt-2 small text-muted">${escHtml(event.description)}</div>` : ''}
          <div class="lc-reminder-actions mt-3 d-flex gap-2 flex-wrap">
            <a href="${event.detail_url}" class="btn btn-sm btn-primary" style="background:${accent};border-color:${accent};">
              <i class="fas fa-eye me-1"></i>View Event
            </a>
            <button class="btn btn-sm btn-outline-secondary lc-snooze-btn" data-event-id="${event.id}">
              <i class="fas fa-bell-slash me-1"></i>Snooze ${SNOOZE_MINUTES}m
            </button>
            <button class="btn btn-sm btn-outline-success lc-dismiss-btn" data-event-id="${event.id}">
              <i class="fas fa-check me-1"></i>Dismiss
            </button>
          </div>
        </div>
      </div>`;
  }

  function escHtml(s) {
    if (!s) return '';
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
            .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
  }

  // ── Popup modal ───────────────────────────────────────────────────────────
  function showNextReminder() {
    if (isModalOpen || reminderQueue.length === 0) return;

    const event = reminderQueue.shift();
    if (!event) return;

    isModalOpen = true;
    const container = document.getElementById('lcReminderContainer');
    if (!container) { isModalOpen = false; return; }

    container.innerHTML = buildReminderHTML(event);
    container.style.display = 'block';
    container.classList.add('lc-reminder-in');

    // Attach button listeners
    container.querySelectorAll('.lc-snooze-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        snoozeEvent(btn.dataset.eventId);
        closeReminder();
      });
    });
    container.querySelectorAll('.lc-dismiss-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        markShown(btn.dataset.eventId);
        clearSnooze(btn.dataset.eventId);
        closeReminder();
      });
    });

    sendDesktopNotification(event);

    // Auto-dismiss after 5 minutes if user ignores it
    setTimeout(() => {
      if (isModalOpen) closeReminder();
    }, 5 * 60 * 1000);
  }

  function closeReminder() {
    const container = document.getElementById('lcReminderContainer');
    if (container) {
      container.classList.remove('lc-reminder-in');
      setTimeout(() => {
        container.style.display = 'none';
        container.innerHTML = '';
        isModalOpen = false;
        // Show next queued reminder after a short pause
        setTimeout(showNextReminder, 500);
      }, 300);
    } else {
      isModalOpen = false;
    }
  }

  // ── Polling & logic ───────────────────────────────────────────────────────
  function checkReminders(events) {
    const now = Date.now();

    events.forEach(ev => {
      // Skip if already dismissed or currently snoozed
      if (wasShown(ev.id) || isSnoozed(ev.id)) return;

      // Fire the reminder if we're past the reminder_fire_ts
      if (now >= ev.reminder_fire_ts) {
        // Don't add duplicates to queue
        const alreadyQueued = reminderQueue.some(q => q.id === ev.id);
        if (!alreadyQueued) {
          reminderQueue.push(ev);
        }
      }
    });

    if (reminderQueue.length > 0) {
      showNextReminder();
    }
  }

  function updateNavBadge(events) {
    const badge = document.getElementById('lc-cal-reminder-badge');
    if (!badge) return;
    const now = Date.now();
    const dueCount = events.filter(ev => {
      return now >= ev.reminder_fire_ts && !wasShown(ev.id) && !isSnoozed(ev.id);
    }).length;
    if (dueCount > 0) {
      badge.textContent = dueCount;
      badge.style.display = 'inline';
    } else {
      badge.style.display = 'none';
    }
  }

  async function pollReminders() {
    try {
      const resp = await fetch('/calendar/api/reminders', {
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
      });
      if (!resp.ok) return;
      const data = await resp.json();
      if (data && Array.isArray(data.events)) {
        checkReminders(data.events);
        updateNavBadge(data.events);
      }
    } catch (e) {
      // Silently fail — network hiccups shouldn't break the UI
    }
  }

  // ── Init ──────────────────────────────────────────────────────────────────
  function init() {
    requestNotificationPermission();
    // First poll immediately, then every minute
    pollReminders();
    pollTimer = setInterval(pollReminders, POLL_INTERVAL_MS);
  }

  // Start when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Expose globally so inline handlers can call closeReminder
  window.lcCalendarReminders = { closeReminder, pollReminders };
})();
