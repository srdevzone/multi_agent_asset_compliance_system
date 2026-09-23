/* Dashboard Page Controller - Asset Compliance AI */

(function () {
  window.PageControllers = window.PageControllers || {};

  window.PageControllers.dashboard = {
    healthInterval: null,

    init() {
      console.log('Dashboard controller initialized');
      
      this.healthBadge = document.getElementById('health-status-badge');
      this.endpointLabel = document.getElementById('telemetry-endpoint');
      this.latencyLabel = document.getElementById('telemetry-latency');
      this.statusLabel = document.getElementById('telemetry-status');
      this.activityTableBody = document.getElementById('activity-log-body');
      
      this._boundHandleClearLogs = this.handleClearLogs.bind(this);
      this._boundShowAuditOverview = this.showAuditOverview.bind(this);
      this._boundHandleActivityLogEvent = this.handleActivityLogEvent.bind(this);

      const clearLogsBtn = document.getElementById('clear-logs-btn');
      if (clearLogsBtn) {
        clearLogsBtn.addEventListener('click', this._boundHandleClearLogs);
      }

      const triggerBtn = document.getElementById('trigger-audit-btn');
      if (triggerBtn) {
        triggerBtn.addEventListener('click', this._boundShowAuditOverview);
      }

      // Initial execution and schedule polling loop
      this.pollHealth();
      this.healthInterval = setInterval(() => this.pollHealth(), 5000);

      this.renderActivityLogs();

      window.addEventListener('activityLogChanged', this._boundHandleActivityLogEvent);
    },

    handleActivityLogEvent(e) {
      this.renderActivityLogs(e.detail);
    },

    async pollHealth() {
      const startTime = Date.now();
      const base = window.Config ? window.Config.getApiBaseUrl() : 'http://localhost:8000';
      
      if (this.endpointLabel) {
        this.endpointLabel.innerText = `${base.replace(/\/$/, '')}/health`;
      }

      try {
        // Fetch health endpoint
        const data = await window.ApiClient.get('/health');
        const latency = Date.now() - startTime;
        
        this.updateHealthUI(true, latency, data);
      } catch (error) {
        console.warn('Dashboard health poll failed:', error);
        this.updateHealthUI(false, null, error.message);
      }
    },

    updateHealthUI(isOnline, latency, details) {
      if (this.healthBadge) {
        this.healthBadge.className = 'badge ' + (isOnline ? 'badge-compliant' : 'badge-non-compliant');
        this.healthBadge.innerText = isOnline ? 'ONLINE' : 'OFFLINE';
      }

      if (this.latencyLabel) {
        this.latencyLabel.innerText = isOnline ? `${latency} ms` : '--';
        this.latencyLabel.style.color = isOnline ? 'var(--emerald-success)' : 'var(--on-surface-dim)';
      }

      if (this.statusLabel) {
        if (isOnline) {
          this.statusLabel.innerText = 'System Operational';
          this.statusLabel.style.color = 'var(--on-surface)';
        } else {
          this.statusLabel.innerText = 'Connection Failed';
          this.statusLabel.style.color = 'var(--rose-error)';
        }
      }
    },

    renderActivityLogs(logs = null) {
      if (!this.activityTableBody) return;

      const entries = logs || (window.Config ? window.Config.getActivityLog() : []);

      if (entries.length === 0) {
        this.activityTableBody.innerHTML = `
          <tr>
            <td colspan="4" style="padding: 24px; text-align: center; color: var(--on-surface-dim);">
              No recent activity recorded. Run audit jobs or update configurations to log operations.
            </td>
          </tr>
        `;
        return;
      }

      this.activityTableBody.innerHTML = entries.map(entry => {
        const dateStr = window.Utils.formatDate(entry.timestamp);
        let badgeClass = 'badge-insufficient';
        if (entry.status === 'success') badgeClass = 'badge-compliant';
        if (entry.status === 'warning') badgeClass = 'badge-warning';
        if (entry.status === 'error') badgeClass = 'badge-non-compliant';

        return `
          <tr class="activity-row" style="border-bottom: 1px solid var(--slate-800);">
            <td style="padding: 12px 16px; font-family: var(--font-code); font-size: var(--fs-code-sm); color: var(--on-surface-variant); white-space: nowrap;">
              ${dateStr}
            </td>
            <td style="padding: 12px 16px; font-weight: 600; color: var(--on-surface);">
              ${window.Utils.escapeHtml(entry.action)}
            </td>
            <td style="padding: 12px 16px; color: var(--on-surface-variant); max-width: 400px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
              ${window.Utils.escapeHtml(entry.details)}
            </td>
            <td style="padding: 12px 16px; text-align: right;">
              <span class="badge ${badgeClass}" style="font-size: 10px;">${entry.status.toUpperCase()}</span>
            </td>
          </tr>
        `;
      }).join('');
    },

    handleClearLogs() {
      if (window.Modal) {
        window.Modal.create({
          title: 'Clear Activity Logs',
          content: 'Are you sure you want to clear your local activity history? This action is permanent and only affects this browser.',
          confirmText: 'Clear Logs',
          cancelText: 'Cancel',
          variant: 'danger',
          onConfirm: (close) => {
            if (window.Config) {
              window.Config.clearActivityLog();
              window.Config.addActivity('System Log', 'Activity history cleared', 'info');
            }
            close();
            if (window.Toast) {
              window.Toast.info('Activity logs cleared.');
            }
          }
        });
      } else {
        if (confirm('Clear activity history?')) {
          if (window.Config) {
            window.Config.clearActivityLog();
          }
        }
      }
    },

    showAuditOverview() {
      if (window.Modal) {
        window.Modal.create({
          title: 'Compliance Agent Auditing',
          content: `
            <div style="display: flex; flex-direction: column; gap: 12px;">
              <p>The Asset Compliance system utilizes a multi-agent framework to audit ingestion assets:</p>
              <ul style="padding-left: 20px; margin: 0; display: flex; flex-direction: column; gap: 8px;">
                <li><strong>Ingestion Agent:</strong> Extracts contents and structure from raw files.</li>
                <li><strong>Regulation RAG Agent:</strong> Searches legal documents to match governing sections.</li>
                <li><strong>Validation Agent:</strong> Reasons about compliance risks and yields the final verdict.</li>
              </ul>
              <p style="margin-top: 8px;">Upload folders or assets via the <em>Ingest Assets</em> page to run live compliance audits.</p>
            </div>
          `,
          confirmText: 'Go to Ingest',
          cancelText: 'Dismiss',
          onConfirm: (close) => {
            close();
            window.location.hash = '#/ingest';
          }
        });
      }
    },

    destroy() {
      console.log('Dashboard controller destroyed');
      if (this.healthInterval) {
        clearInterval(this.healthInterval);
        this.healthInterval = null;
      }
      if (this._boundHandleActivityLogEvent) {
        window.removeEventListener('activityLogChanged', this._boundHandleActivityLogEvent);
      }
    }
  };
})();
