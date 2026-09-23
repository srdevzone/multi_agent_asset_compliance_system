/* Audit Assets Page Controller - Asset Compliance AI */

(function () {
  window.PageControllers = window.PageControllers || {};

  window.PageControllers.audit = {
    init() {
      console.log('Audit controller initialized');

      this.form = document.getElementById('ingest-form');
      this.pathInput = document.getElementById('ingest-path');
      this.submitBtn = document.getElementById('ingest-submit-btn');
      this.consoleEl = document.getElementById('ingest-console');
      this.badgeStatus = document.getElementById('audit-status-badge');
      this.citationsContainer = document.getElementById('citations-container');
      this.noCitationsMsg = document.getElementById('no-citations-msg');

      this._boundHandleSubmit = this.handleSubmit.bind(this);
      if (this.form) {
        this.form.addEventListener('submit', this._boundHandleSubmit);
      }
      
      // Clean dynamic verdict banners if they exist from previous runs
      window.VerdictBanner.remove();
    },

    async handleSubmit(e) {
      e.preventDefault();

      const assetPath = this.pathInput.value.trim();
      if (!assetPath) return;

      this.setRunningState(true);
      this.clearConsole();
      this.clearCitations();
      window.VerdictBanner.remove();

      this.logToConsole('Initializing compliance pipeline request...', 'info');

      const assetId = 'asset_' + Math.random().toString(36).substring(2, 8);
      const runId = 'run_' + Date.now();
      
      const payload = {
        asset_id: assetId,
        run_id: runId,
        asset_spec: {
          name: assetPath.split('/').pop() || assetPath,
          category: assetPath.includes('solar') ? 'solar_inverter' : 'generic_equipment',
          manufacturer: 'Standard OEM'
        },
        s3_image_keys: ['assets/field_photo.jpg'], // Mandatory at least 1 image key in backend schema
        auditor_remarks: `Initiated compliance audit for asset file: ${assetPath}`
      };

      try {
        // Test backend availability first
        await window.ApiClient.get('/health');
        
        this.logToConsole(`Backend online. Submitting audit run '${runId}'...`, 'info');
        
        await window.ApiClient.streamRequest(
          '/api/v1/audit/run',
          payload,
          (chunk) => this.handleStreamChunk(chunk),
          (error) => this.handleStreamError(error),
          () => this.handleStreamComplete()
        );

      } catch (err) {
        console.warn('Backend unavailable or streaming failed. Offering simulation mode.', err);
        this.logToConsole(`[ERROR] Connection failed: ${err.message}`, 'error');
        
        if (window.Modal) {
          window.Modal.create({
            title: 'Simulation Mode',
            content: 'The Asset Compliance backend is currently offline or unreachable. Would you like to run the audit in Simulation Mode to test the frontend telemetry logs and citation panels?',
            confirmText: 'Run Simulation',
            cancelText: 'Cancel',
            variant: 'primary',
            onConfirm: (close) => {
              close();
              this.runAuditSimulation(payload);
            },
            onCancel: (close) => {
              close();
              this.setRunningState(false);
              this.logToConsole('Audit aborted due to connectivity failure.', 'error');
            }
          });
        } else {
          this.setRunningState(false);
        }
      }
    },

    handleStreamChunk(chunk) {
      if (chunk.event === 'node_complete') {
        const progressPct = Math.round(chunk.progress * 100);
        this.logToConsole(`[PROGRESS ${progressPct}%] Node '${chunk.node}' successfully completed execution.`, 'success');
        
        // Update badge percentage
        if (this.badgeStatus) {
          this.badgeStatus.innerText = `RUNNING (${progressPct}%)`;
          this.badgeStatus.className = 'badge badge-warning';
        }
      } else if (chunk.event === 'verdict') {
        this.renderFinalVerdict(chunk.verdict);
      }
    },

    handleStreamError(error) {
      this.logToConsole(`[FATAL ERROR] Stream terminated unexpectedly: ${error.message}`, 'error');
      this.setRunningState(false);
      if (window.Toast) {
        window.Toast.error(`Audit run failed: ${error.message}`);
      }
    },

    handleStreamComplete() {
      this.logToConsole('Compliance audit pipeline finished processing.', 'info');
      this.setRunningState(false);
    },

    // UI Log helpers
    logToConsole(text, type = 'info') {
      if (!this.consoleEl) return;
      
      const entry = document.createElement('div');
      entry.className = 'log-entry';
      if (type === 'success') entry.classList.add('log-success');
      if (type === 'error') entry.classList.add('log-error');
      if (type === 'warning') entry.classList.add('log-warning');
      if (type === 'info') entry.classList.add('log-info');

      const timestamp = new Date().toLocaleTimeString();
      entry.innerText = `[${timestamp}] ${text}`;
      
      this.consoleEl.appendChild(entry);
      this.consoleEl.scrollTop = this.consoleEl.scrollHeight;
    },

    clearConsole() {
      if (this.consoleEl) {
        this.consoleEl.innerHTML = '';
      }
    },

    clearCitations() {
      if (this.citationsContainer) {
        this.citationsContainer.innerHTML = '';
      }
      if (this.noCitationsMsg) {
        this.noCitationsMsg.style.display = 'block';
      }
    },

    setRunningState(isRunning) {
      if (!this.submitBtn) return;
      
      this.submitBtn.disabled = isRunning;
      if (isRunning) {
        this.submitBtn.innerText = 'Analyzing Asset...';
        if (this.badgeStatus) {
          this.badgeStatus.innerText = 'RUNNING';
          this.badgeStatus.className = 'badge badge-warning';
        }
      } else {
        this.submitBtn.innerText = '⚡ Begin Audit Check';
      }
    },

    // RAG Citations builder
    addCitationCard(title, text, score, url) {
      if (this.noCitationsMsg) {
        this.noCitationsMsg.style.display = 'none';
      }

      if (!this.citationsContainer) return;

      window.CitationCard.render(this.citationsContainer, {
        title,
        text,
        score,
        url
      });
    },

    renderFinalVerdict(verdict) {
      this.logToConsole(`Audit decision completed. Compliance status: ${verdict.compliance_status}`, 'success');
      
      if (this.badgeStatus) {
        const badgeClass = window.Utils.getVerdictBadgeClass(verdict.compliance_status);
        this.badgeStatus.innerText = verdict.compliance_status;
        this.badgeStatus.className = `badge ${badgeClass}`;
      }

      // Add to local activity log
      if (window.Config) {
        window.Config.addActivity(
          'Asset Audit', 
          `Audit complete for asset ${verdict.asset_id}: status is ${verdict.compliance_status}`, 
          verdict.compliance_status === 'COMPLIANT' ? 'success' : verdict.compliance_status === 'NON_COMPLIANT' ? 'error' : 'warning'
        );
      }

      // Insert verdict banner in UI
      const chatLayoutEl = document.querySelector('.chat-layout');
      if (chatLayoutEl) {
        window.VerdictBanner.render(
          { container: chatLayoutEl.parentNode, before: chatLayoutEl },
          verdict
        );
      }

      if (window.Toast) {
        if (verdict.compliance_status === 'COMPLIANT') {
          window.Toast.success('Asset compliance verified: COMPLIANT');
        } else {
          window.Toast.warning(`Compliance alert issued: ${verdict.compliance_status}`);
        }
      }
    },

    // SIMULATION MODE
    runAuditSimulation(payload) {
      this.logToConsole('BOOTING DUMMY LANGGRAPH MULTI-AGENT STATE ENGINE...', 'info');
      
      const steps = [
        {
          node: 'document_agent',
          delay: 1200,
          progress: 0.2,
          log: '[DOCUMENT AGENT] Scanning and indexing PDF specifications... Parsed 25 text blocks. Generated vector mappings.',
          citations: []
        },
        {
          node: 'image_agent',
          delay: 2400,
          progress: 0.4,
          log: '[IMAGE AGENT] Analyzing installation photo labels via OCR and LLM Vision... Extracted model metadata: "Grid-Tied Solar System Model Inverter v2.0". Verified structural coordinates.',
          citations: [
            {
              title: 'Installation Specs v2',
              text: 'All commercial grid-tied solar modules must maintain a physical setback spacing clearance of no less than 36 inches from high-power distribution transformers.',
              score: 0.94,
              url: 'http://example.com/spec-2'
            }
          ]
        },
        {
          node: 'rule_agent',
          delay: 3800,
          progress: 0.6,
          log: '[RULE AGENT] Fetching matched regulations from Vector database... Identified Governing Code: National Electrical Code (NEC) Clause 110.26 (Working space clearances) and Clause 690.4 (PV system clearances).',
          citations: [
            {
              title: 'NEC Clause 110.26',
              text: 'Working space in the direction of access to live parts operating at 600V or less shall not be less than 3 feet (36 inches) deep to ensure safe electrical work clearances.',
              score: 0.88,
              url: 'http://example.com/nec-110-26'
            }
          ]
        },
        {
          node: 'evidence_agent',
          delay: 5000,
          progress: 0.8,
          log: '[EVIDENCE AGENT] Validating layout measurements against electrical code specifications. Verdict calculation starting...',
          citations: []
        },
        {
          node: 'verdict_agent',
          delay: 6200,
          progress: 1.0,
          log: '[VERDICT AGENT] Multi-agent consensus reached. Compiling final compliance audit review report.',
          citations: []
        }
      ];

      steps.forEach((step) => {
        setTimeout(() => {
          this.logToConsole(step.log, 'success');
          
          if (this.badgeStatus) {
            this.badgeStatus.innerText = `RUNNING (${Math.round(step.progress * 100)}%)`;
          }

          // Add any step citations
          step.citations.forEach(c => {
            this.addCitationCard(c.title, c.text, c.score, c.url);
          });

          // Final verdict step trigger
          if (step.node === 'verdict_agent') {
            const isCompliantSim = payload.asset_spec.name.toLowerCase().includes('compliant');
            const simVerdict = {
              asset_id: payload.asset_id,
              run_id: payload.run_id,
              compliance_status: isCompliantSim ? 'COMPLIANT' : 'NON_COMPLIANT',
              confidence: 0.91,
              verdict_reasoning: isCompliantSim 
                ? 'All physical clearance spacing and working space depths meet National Electrical Code (NEC) guidelines. Inverter installation exhibits sufficient access setbacks.'
                : 'Asset compliance check failed. Clearances on installation photo show setback depth of 28 inches, violating the 36-inch minimum safety distance requirement specified by NEC Clause 110.26.',
              recommendations: isCompliantSim
                ? ['Approve asset installation certification.', 'Schedule next routine maintenance audit in 12 months.']
                : ['Relocate inverter to ensure at least 36 inches clear spacing.', 'Re-submit compliance photos after correction.']
            };
            this.renderFinalVerdict(simVerdict);
            this.setRunningState(false);
          }
        }, step.delay);
      });
    },

    destroy() {
      console.log('Audit controller destroyed');
      if (this.form && this._boundHandleSubmit) {
        this.form.removeEventListener('submit', this._boundHandleSubmit);
      }
    }
  };
})();
