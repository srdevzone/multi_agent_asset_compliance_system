// js/utils.js

(function () {
  const Utils = {
    escapeHtml(str) {
      if (!str) return '';
      return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    },

    getVerdictBadgeClass(status) {
      switch (status) {
        case 'COMPLIANT': return 'badge-compliant';
        case 'NON_COMPLIANT': return 'badge-non-compliant';
        case 'NEEDS_REVIEW': return 'badge-needs-review';
        default: return 'badge-insufficient';
      }
    },

    getVerdictSymbol(status) {
      switch (status) {
        case 'COMPLIANT': return '✅';
        case 'NEEDS_REVIEW': return '⚠️';
        default: return '❌';
      }
    },

    formatDate(isoString) {
      try {
        return new Date(isoString).toLocaleString();
      } catch (_) {
        return isoString;
      }
    },

    formatBytes(bytes, decimals = 2) {
      if (bytes === 0) return '0 Bytes';
      const k = 1024;
      const dm = decimals < 0 ? 0 : decimals;
      const sizes = ['Bytes', 'KB', 'MB', 'GB'];
      const i = Math.floor(Math.log(bytes) / Math.log(k));
      return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
    },

    renderApiKeyStatus(badgeElement, key) {
      if (key) {
        badgeElement.textContent = 'Configured';
        badgeElement.className = 'badge badge-success';
      } else {
        badgeElement.textContent = 'Not Configured';
        badgeElement.className = 'badge badge-danger';
      }
    }
  };

  window.Utils = Utils;
})();
