// js/components/verdict-card.js

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

class VerdictCard {
  constructor(containerId, options = {}) {
    this.container = document.getElementById(containerId);
    this.options = options;
  }

  render(verdict) {
    if (!this.container || !verdict) return;

    const {
      compliance_status,
      confidence,
      triggered_rules = [],
      recommendations = [],
      verdict_reasoning = "",
      generated_at
    } = verdict;

    // Get color theme based on compliance status
    let statusClass = 'status-insufficient';
    let statusLabel = 'INSUFFICIENT DATA';
    let statusColor = 'var(--slate-600)';
    let statusBg = 'rgba(71, 85, 105, 0.1)';
    let statusBorder = 'rgba(71, 85, 105, 0.2)';

    if (compliance_status === 'COMPLIANT') {
      statusClass = 'status-compliant';
      statusLabel = 'COMPLIANT';
      statusColor = 'var(--emerald-success)';
      statusBg = 'rgba(16, 185, 129, 0.1)';
      statusBorder = 'rgba(16, 185, 129, 0.3)';
    } else if (compliance_status === 'NON_COMPLIANT') {
      statusClass = 'status-noncompliant';
      statusLabel = 'NON-COMPLIANT';
      statusColor = 'var(--rose-error)';
      statusBg = 'rgba(244, 63, 94, 0.1)';
      statusBorder = 'rgba(244, 63, 94, 0.3)';
    } else if (compliance_status === 'NEEDS_REVIEW') {
      statusClass = 'status-needsreview';
      statusLabel = 'NEEDS REVIEW';
      statusColor = 'var(--amber-warning)';
      statusBg = 'rgba(245, 158, 11, 0.1)';
      statusBorder = 'rgba(245, 158, 11, 0.3)';
    }

    const confidencePct = Math.round(confidence * 100);
    const dateStr = generated_at ? new Date(generated_at).toLocaleString() : 'N/A';

    const strokeDashoffset = 314.16 - (314.16 * confidencePct) / 100;

    this.container.innerHTML = `
      <!-- Verdict Banner -->
      <div class="verdict-banner" style="background-color: ${statusBg}; border: 1px solid ${statusBorder};">
        <div>
          <div class="label-caps" style="color: var(--on-surface-variant); margin-bottom: 4px;">Audit Verdict</div>
          <div class="verdict-status-title" style="color: ${statusColor};">${statusLabel}</div>
        </div>
        <div style="text-align: right;">
          <div class="body-sm" style="color: var(--on-surface-variant);">Generated At</div>
          <div class="code-sm" style="color: var(--on-surface); font-weight: 500;">${dateStr}</div>
        </div>
      </div>

      <!-- Verdict Main Grid -->
      <div class="verdict-grid">
        <!-- Left Column: Reasoning & Recommendations -->
        <div style="display: flex; flex-direction: column; gap: 24px;">
          <!-- Reasoning -->
          <div class="card">
            <h3 class="headline-sm card-title">Verdict Explanation</h3>
            <p class="body-md" style="color: var(--on-surface-variant); white-space: pre-line; line-height: 1.6;">
              ${escapeHtml(verdict_reasoning) || "No reasoning text generated."}
            </p>
          </div>

          <!-- Recommendations -->
          <div class="card">
            <h3 class="headline-sm card-title">Actionable Recommendations</h3>
            ${recommendations.length > 0 ? `
              <ul class="recommendations-list">
                ${recommendations.map(rec => `<li>${escapeHtml(rec)}</li>`).join('')}
              </ul>
            ` : `
              <p class="body-md" style="color: var(--slate-500); font-style: italic;">No recommendations generated.</p>
            `}
          </div>
        </div>

        <!-- Right Column: Confidence Gauge -->
        <div class="gauge-container">
          <h3 class="label-caps" style="margin-bottom: 16px; color: var(--on-surface-variant);">Confidence Rating</h3>
          <div style="position: relative; width: 120px; height: 120px;">
            <svg class="gauge-svg">
              <circle class="gauge-bg" cx="60" cy="60" r="50"></circle>
              <circle class="gauge-fill" cx="60" cy="60" r="50" 
                style="stroke: ${statusColor}; stroke-dashoffset: ${strokeDashoffset};">
              </circle>
            </svg>
            <div style="position: absolute; top: 0; left: 0; right: 0; bottom: 0; display: flex; align-items: center; justify-content: center;">
              <span style="font-family: var(--font-heading); font-size: 24px; font-weight: 700; color: var(--on-surface);">${confidencePct}%</span>
            </div>
          </div>
          <p class="body-sm" style="margin-top: 16px; color: var(--on-surface-variant);">
            Based on compliance consistency and completeness of evidence.
          </p>
        </div>
      </div>

      <!-- Triggered Rules Table -->
      <div class="card" style="margin-bottom: 24px;">
        <h3 class="headline-sm card-title">Triggered Compliance Rules</h3>
        ${triggered_rules.length > 0 ? `
          <div style="overflow-x: auto;">
            <table class="rules-table">
              <thead>
                <tr>
                  <th style="width: 15%">Rule ID</th>
                  <th style="width: 45%">Requirement Description</th>
                  <th style="width: 15%">Severity</th>
                  <th style="width: 25%">Evidence References</th>
                </tr>
              </thead>
              <tbody>
                ${triggered_rules.map(rule => {
                  const severityClass = `severity-${rule.severity}`;
                  const refs = rule.evidence_refs || [];
                  return `
                    <tr>
                      <td class="code-sm" style="color: var(--on-surface); font-weight: 700;">${escapeHtml(rule.rule_id)}</td>
                      <td>
                        <div style="font-weight: 600; margin-bottom: 4px; color: var(--on-surface);">${escapeHtml(rule.rule_description)}</div>
                        ${rule.violation_reason ? `<div style="font-size: 12px; color: var(--rose-error); margin-top: 4px; font-style: italic;">Violation: ${escapeHtml(rule.violation_reason)}</div>` : ''}
                      </td>
                      <td>
                        <span class="severity-badge ${severityClass}">${escapeHtml(rule.severity)}</span>
                      </td>
                      <td>
                        ${refs.length > 0 ? 
                          refs.map(refIdx => `<button class="ref-badge" data-ref-idx="${refIdx}">#${refIdx + 1}</button>`).join('')
                          : `<span style="color: var(--slate-500); font-size: 12px;">No specific references</span>`
                        }
                      </td>
                    </tr>
                  `;
                }).join('')}
              </tbody>
            </table>
          </div>
        ` : `
          <p class="body-md" style="color: var(--emerald-success); font-weight: 500; display: flex; align-items: center; gap: 8px;">
            <span>✅</span> All compliance checks passed. No rules triggered.
          </p>
        `}
      </div>
    `;

    // Add event listeners to reference badges
    this.container.querySelectorAll('.ref-badge').forEach(badge => {
      badge.addEventListener('click', (e) => {
        const refIdx = parseInt(e.currentTarget.getAttribute('data-ref-idx'));
        if (this.options.onRefClick) {
          this.options.onRefClick(refIdx);
        }
      });
    });
  }
}

window.VerdictCard = VerdictCard;
