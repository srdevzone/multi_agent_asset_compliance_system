/* Client-Side Router - Asset Compliance AI */

(function () {
  const routes = {
    '#/login': {
      html: '/pages/login.html',
      js: '/js/pages/login.js',
      name: 'login',
      requiresAuth: false
    },
    '#/dashboard': {
      html: '/pages/dashboard.html',
      js: '/js/pages/dashboard.js',
      name: 'dashboard',
      requiresAuth: true
    },
    '#/ingest': {
      html: '/pages/ingest.html',
      js: '/js/pages/ingest.js',
      name: 'ingest',
      requiresAuth: true
    },
    '#/audit': {
      html: '/pages/audit.html',
      js: '/js/pages/audit.js',
      name: 'audit',
      requiresAuth: true
    },
    '#/chat': {
      html: '/pages/chat.html',
      js: '/js/pages/chat.js',
      name: 'chat',
      requiresAuth: true
    },
    '#/admin': {
      html: '/pages/admin.html',
      js: '/js/pages/admin.js',
      name: 'admin',
      requiresAuth: true
    },
    '#/settings': {
      html: '/pages/settings.html',
      js: '/js/pages/settings.js',
      name: 'settings',
      requiresAuth: true
    }
  };

  const DEFAULT_ROUTE = '#/dashboard';
  const LOGIN_ROUTE = '#/login';

  class Router {
    constructor() {
      this.mainContainerId = 'main-content';
      this.currentRoute = null;
      this.currentController = null;
    }

    init() {
      window.addEventListener('hashchange', () => this.handleRoute());
      window.addEventListener('load', () => this.handleRoute());
    }

    async handleRoute() {
      let hash = window.location.hash || DEFAULT_ROUTE;
      
      // Normalize routing for slash variants (e.g. #/login/ -> #/login)
      if (hash.endsWith('/') && hash.length > 2) {
        hash = hash.slice(0, -1);
      }

      // Check route validity
      let route = routes[hash];
      if (!route) {
        // Fallback to default
        window.location.hash = DEFAULT_ROUTE;
        return;
      }

      // Authentication check
      const apiKey = window.Config ? window.Config.getApiKey() : '';
      if (route.requiresAuth && !apiKey) {
        console.warn('Authentication required. Redirecting to login.');
        window.location.hash = LOGIN_ROUTE;
        return;
      }

      // If already logged in and trying to access login, redirect to dashboard
      if (hash === LOGIN_ROUTE && apiKey) {
        window.location.hash = DEFAULT_ROUTE;
        return;
      }

      this.currentRoute = hash;

      // Update layout sidebar display
      if (hash === LOGIN_ROUTE) {
        document.body.classList.add('no-sidebar');
      } else {
        document.body.classList.remove('no-sidebar');
      }

      // Load view content
      await this.loadView(route);
    }

    async loadView(route) {
      const container = document.getElementById(this.mainContainerId);
      if (!container) {
        console.error(`Router container #${this.mainContainerId} not found.`);
        return;
      }

      // Call destroy on current controller if it exists
      if (this.currentController && typeof this.currentController.destroy === 'function') {
        try {
          this.currentController.destroy();
        } catch (e) {
          console.error('Error destroying controller:', e);
        }
      }
      this.currentController = null;

      try {
        // Show loading state
        container.innerHTML = '<div class="flex-column align-center justify-between" style="padding: 100px 0;"><div class="badge badge-pending">Loading view...</div></div>';

        // Fetch HTML content with cache-busting
        const response = await fetch(`${route.html}?_cb=${Date.now()}`);
        if (!response.ok) {
          throw new Error(`Failed to load view HTML: ${response.status}`);
        }
        const contentType = response.headers.get('content-type') || '';
        if (!contentType.includes('text/html') && !contentType.includes('text/plain')) {
          throw new Error('Unexpected content type from view HTML endpoint');
        }
        const htmlContent = await response.text();
        // Trusted content: HTML files are served from the app's own /pages/ directory.
        // No user-controlled data flows into these template files.
        container.innerHTML = htmlContent;

        // Load and execute script
        await this.loadScript(route.js);

        // Initialize controller
        if (window.PageControllers && window.PageControllers[route.name]) {
          this.currentController = window.PageControllers[route.name];
          if (typeof this.currentController.init === 'function') {
            this.currentController.init();
          }
        }

        // Update active sidebar nav item
        this.updateActiveNav(this.currentRoute);

      } catch (error) {
        console.error(`Error loading route ${this.currentRoute}:`, error);
        container.innerHTML = `
          <div class="alert alert-error">
            <strong>Navigation Error:</strong> Failed to render page. ${error.message}
          </div>
        `;
      }
    }

    loadScript(src) {
      return new Promise((resolve, reject) => {
        // Remove existing instance of the script to re-evaluate it
        const existing = document.querySelector(`script[data-route-script="${src}"]`);
        if (existing) {
          existing.remove();
        }

        const script = document.createElement('script');
        script.src = `${src}?_cb=${Date.now()}`;
        script.type = 'text/javascript';
        script.setAttribute('data-route-script', src);
        script.onload = () => resolve();
        script.onerror = () => reject(new Error(`Failed to load controller script: ${src}`));
        document.body.appendChild(script);
      });
    }

    updateActiveNav(hash) {
      const navLinks = document.querySelectorAll('.sidebar-nav-link');
      navLinks.forEach(link => {
        const href = link.getAttribute('href');
        if (href === hash) {
          link.classList.add('active');
        } else {
          link.classList.remove('active');
        }
      });
    }

    // Force page navigation helper
    navigate(hash) {
      window.location.hash = hash;
    }
  }

  // Instantiate and run the Router
  window.Router = new Router();
  
  // Initialize when the DOM is ready
  document.addEventListener('DOMContentLoaded', () => {
    window.Router.init();
  });
})();
