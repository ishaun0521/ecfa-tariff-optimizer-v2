/**
 * ECFA Tariff Optimizer - Frontend Usage Tracking
 * 
 * 追蹤內容：
 * - 頁面瀏覽（page view）
 * - 使用者操作（按鈕點擊、表單提交）
 * - IP、國家、瀏覽器資訊（從後端取得）
 * 
 * 資料只會傳到後端儲存，只有管理員能看
 */

(function() {
  'use strict';

  // Config
  const API_ENDPOINT = '/api/track';
  const SESSION_ID = 'ecfa_session_' + Math.random().toString(36).substr(2, 9);
  const SESSION_START = Date.now();

  // Store session info
  let sessionInfo = {
    sessionId: SESSION_ID,
    sessionStart: new Date().toISOString(),
    referrer: document.referrer || 'direct',
    screenWidth: window.screen.width,
    screenHeight: window.screen.height,
    language: navigator.language || 'unknown',
    platform: navigator.platform || 'unknown',
  };

  /**
   * Send tracking data to backend
   */
  function sendEvent(eventType, eventData) {
    const payload = {
      timestamp: new Date().toISOString(),
      event_type: eventType,
      session_id: SESSION_ID,
      session_start: sessionInfo.sessionStart,
      page_url: window.location.href,
      page_path: window.location.pathname,
      page_title: document.title,
      referrer: sessionInfo.referrer,
      user_agent: navigator.userAgent,
      screen: {
        width: sessionInfo.screenWidth,
        height: sessionInfo.screenHeight,
      },
      language: sessionInfo.language,
      event_data: eventData || {},
    };

    // Send to backend (fail silently if endpoint not available)
    if (navigator.sendBeacon) {
      const blob = new Blob([JSON.stringify(payload)], { type: 'application/json' });
      navigator.sendBeacon(API_ENDPOINT, blob);
    } else {
      // Fallback for older browsers
      fetch(API_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        keepalive: true,
      }).catch(function() {});
    }
  }

  /**
   * Track page view
   */
  function trackPageView() {
    sendEvent('page_view', {
      url: window.location.href,
      path: window.location.pathname,
    });
  }

  /**
   * Track button clicks
   */
  function trackButtonClick(e) {
    const target = e.target;
    
    // Skip if it's not a button, link, or clickable element
    if (!target.matches('button, a, [role="button"]')) {
      return;
    }

    const eventData = {
      element_tag: target.tagName.toLowerCase(),
      element_id: target.id || null,
      element_class: target.className || null,
      element_text: (target.textContent || target.innerText || '').trim().substring(0, 100),
      href: target.href || null,
    };

    // Check for specific actions
    if (target.id) {
      eventData.action = target.id;
    } else if (target.className) {
      eventData.action = target.className;
    }

    sendEvent('click', eventData);
  }

  /**
   * Track form submissions
   */
  function trackFormSubmit(e) {
    const target = e.target;
    const formId = target.id || 'anonymous-form';
    const formAction = target.action || '';
    
    // Get form data (but don't send sensitive info)
    const formData = new FormData(target);
    const data = {};
    for (let [key, value] of formData.entries()) {
      // Skip sensitive fields
      if (key.toLowerCase().includes('password') || key.toLowerCase().includes('token')) {
        data[key] = '[REDACTED]';
      } else if (typeof value === 'string' && value.length > 200) {
        data[key] = value.substring(0, 200) + '...';
      } else {
        data[key] = value;
      }
    }

    sendEvent('form_submit', {
      form_id: formId,
      form_action: formAction,
      form_method: target.method || 'unknown',
      fields: Object.keys(data),
    });
  }

  /**
   * Track API calls (intercepted)
   */
  function trackApiCall(endpoint, method, responseStatus) {
    sendEvent('api_call', {
      endpoint: endpoint,
      method: method,
      status: responseStatus,
    });
  }

  /**
   * Track scroll depth
   */
  let maxScrollDepth = 0;
  function trackScroll() {
    const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
    const scrollHeight = document.documentElement.scrollHeight - window.innerHeight;
    const scrollPercent = Math.round((scrollTop / scrollHeight) * 100);
    
    if (scrollPercent > maxScrollDepth) {
      maxScrollDepth = scrollPercent;
      // Only track meaningful scroll milestones
      if (maxScrollDepth === 25 || maxScrollDepth === 50 || maxScrollDepth === 75 || maxScrollDepth === 100) {
        sendEvent('scroll', {
          depth_percent: maxScrollDepth,
          page_path: window.location.pathname,
        });
      }
    }
  }

  /**
   * Track time on page
   */
  function trackTimeOnPage() {
    const timeOnPage = Date.now() - SESSION_START;
    sendEvent('time_on_page', {
      seconds: Math.round(timeOnPage / 1000),
      page_path: window.location.pathname,
    });
  }

  // Initialize tracking
  function init() {
    // Track initial page view
    trackPageView();

    // Track button/link clicks (delegated)
    document.addEventListener('click', trackButtonClick, true);

    // Track form submissions
    document.addEventListener('submit', trackFormSubmit, true);

    // Track scroll (debounced)
    let scrollTimeout;
    window.addEventListener('scroll', function() {
      if (scrollTimeout) clearTimeout(scrollTimeout);
      scrollTimeout = setTimeout(trackScroll, 100);
    }, { passive: true });

    // Track when user leaves page
    window.addEventListener('beforeunload', function() {
      trackTimeOnPage();
    });

    // Track if user is idle for a while (engagement)
    let idleTimeout;
    function resetIdle() {
      if (idleTimeout) clearTimeout(idleTimeout);
      idleTimeout = setTimeout(function() {
        sendEvent('user_idle', {
          idle_started: new Date().toISOString(),
          page_path: window.location.pathname,
        });
      }, 30000); // 30 seconds idle
    }
    window.addEventListener('mousemove', resetIdle, { passive: true });
    window.addEventListener('keydown', resetIdle, { passive: true });
    resetIdle();

    // Track URL changes (for SPAs or multi-page)
    (function() {
      var originalPushState = history.pushState;
      history.pushState = function() {
        originalPushState.apply(this, arguments);
        trackPageView();
      };
      window.addEventListener('popstate', trackPageView);
    })();
  }

  // Start when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
