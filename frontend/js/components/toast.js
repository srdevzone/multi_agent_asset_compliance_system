/* Toast Component - Asset Compliance AI */

(function () {
  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  class ToastManager {
    constructor() {
      this.container = null;
      this.ensureContainer();
    }

    ensureContainer() {
      if (this.container) return;
      this.container = document.getElementById('toast-container');
      if (!this.container) {
        this.container = document.createElement('div');
      this.container.id = 'toast-container';
      this.container.setAttribute('aria-live', 'assertive');
      this.container.setAttribute('role', 'status');
      
      // CSS Style rules for Toast positioning
      Object.assign(this.container.style, {
          position: 'fixed',
          top: '24px',
          right: '24px',
          zIndex: '9999',
          display: 'flex',
          flexDirection: 'column',
          gap: '12px',
          maxWidth: '380px',
          width: 'calc(100% - 48px)'
        });
        document.body.appendChild(this.container);
      }
    }

    /**
     * Show a toast message to the user
     * @param {string} message Text message to display
     * @param {string} type Theme type ('info' | 'success' | 'warning' | 'error')
     * @param {number} duration Expiry time in milliseconds
     */
    show(message, type = 'info', duration = 4000) {
      this.ensureContainer();

      const toast = document.createElement('div');
      toast.className = `alert alert-${type === 'error' ? 'error' : type === 'success' ? 'success' : type === 'warning' ? 'warning' : 'info'}`;
      
      // Inline styles to ensure visual cohesion & animation entry
      Object.assign(toast.style, {
        margin: '0',
        boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.4), 0 4px 6px -2px rgba(0, 0, 0, 0.2)',
        opacity: '0',
        transform: 'translateY(-20px)',
        transition: 'all 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
        backdropFilter: 'blur(8px)'
      });

      // Type-specific icons using SVG or text symbols for styling consistency
      let icon = '⚡';
      if (type === 'success') icon = '✓';
      if (type === 'warning') icon = '⚠';
      if (type === 'error') icon = '✕';

      toast.innerHTML = `
        <span style="
          display: flex;
          align-items: center;
          justify-content: center;
          width: 20px;
          height: 20px;
          border-radius: var(--radius-full);
          font-size: 11px;
          font-weight: 700;
          flex-shrink: 0;
          background-color: var(--${type === 'error' ? 'rose-error' : type === 'success' ? 'emerald-success' : type === 'warning' ? 'amber-warning' : 'cobalt-primary'});
          color: #0b0e14;
        ">${icon}</span>
        <div class="toast-message" style="flex-grow: 1; font-family: var(--font-body); font-size: var(--fs-body-md); color: var(--on-surface); line-height: 1.25;"></div>
        <button aria-label="Dismiss" style="
          background: none;
          border: none;
          color: var(--on-surface-variant);
          cursor: pointer;
          font-size: 18px;
          padding: 0 4px;
          line-height: 1;
          align-self: center;
        ">&times;</button>
      `;

      // Set message safely using textContent
      const msgDiv = toast.querySelector('.toast-message');
      msgDiv.textContent = escapeHtml(message);

      // Set dismiss action
      const closeBtn = toast.querySelector('button');
      closeBtn.addEventListener('click', () => this.dismiss(toast));

      this.container.appendChild(toast);

      // Force recalculation for browser layout updates
      toast.offsetHeight;

      // Animate entry
      toast.style.opacity = '1';
      toast.style.transform = 'translateY(0)';

      // Auto dismiss setup
      if (duration > 0) {
        setTimeout(() => {
          this.dismiss(toast);
        }, duration);
      }

      return toast;
    }

    success(message, duration) {
      return this.show(message, 'success', duration);
    }

    error(message, duration) {
      return this.show(message, 'error', duration);
    }

    warning(message, duration) {
      return this.show(message, 'warning', duration);
    }

    info(message, duration) {
      return this.show(message, 'info', duration);
    }

    dismiss(toast) {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(-10px)';
      
      const onTransitionEnd = () => {
        toast.removeEventListener('transitionend', onTransitionEnd);
        toast.remove();
      };
      
      toast.addEventListener('transitionend', onTransitionEnd);
    }
  }

  window.Toast = new ToastManager();
})();
