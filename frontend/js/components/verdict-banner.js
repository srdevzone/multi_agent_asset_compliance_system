// js/components/verdict-banner.js

(function () {
  const VerdictBanner = {
    /**
     * Render a verdict banner into the DOM.
     * @param {Object} options
     * @param {HTMLElement|string} options.container - parent element or selector
     * @param {HTMLElement|string} [options.before] - optional reference element/selector to insert before
     * @param {Object} verdict - verdict payload
     * @param {Function} [options.onClose] - optional callback invoked when banner is removed
     * @returns {HTMLElement} the rendered banner element
     */
    render(options, verdict) {
      this.remove();

      const container = typeof options.container === 'string'
        ? document.querySelector(options.container)
        : options.container;
      if (!container) return null;

      let before = null;
      if (options.before) {
        before = typeof options.before === 'string'
          ? document.querySelector(options.before)
          : options.before;
      }

      const status = verdict.compliance_status;
      const badgeClass = window.Utils.getVerdictBadgeClass(status);
      const symbol = window.Utils.getVerdictSymbol(status);
      const confidencePct = Math.round((verdict.confidence || 0) * 100);

      let bannerClass = 'verdict-banner verdict-banner-non-compliant';
      if (status === 'COMPLIANT') bannerClass = 'verdict-banner verdict-banner-compliant';
      else if (status === 'NEEDS_REVIEW') bannerClass = 'verdict-banner verdict-banner-warning';

      const banner = document.createElement('div');
      banner.className = bannerClass;
      banner.id = 'active-verdict-banner';
      banner.innerHTML = `
        <span style="font-size: 28px;">${symbol}</span>
        <div>
          <h4 class="verdict-title">${status} (Confidence: ${confidencePct}%)</h4>
          <p class="body-sm" style="color: inherit; margin: 4px 0 8px 0;">${window.Utils.escapeHtml(verdict.verdict_reasoning)}</p>
          <div class="body-sm">
            <strong>Recommendations:</strong>
            <ul style="margin: 4px 0 0 0; padding-left: 20px;">
              ${(verdict.recommendations || []).map(rec => `<li>${window.Utils.escapeHtml(rec)}</li>`).join('')}
            </ul>
          </div>
        </div>
      `;

      if (before) {
        container.insertBefore(banner, before);
      } else {
        container.appendChild(banner);
      }

      if (options.onClose) {
        this._onClose = options.onClose;
      }

      return banner;
    },

    remove() {
      const existing = document.getElementById('active-verdict-banner');
      if (existing) {
        existing.remove();
        if (typeof this._onClose === 'function') {
          this._onClose();
        }
      }
    }
  };

  window.VerdictBanner = VerdictBanner;
})();
