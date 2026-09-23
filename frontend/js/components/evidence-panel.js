// js/components/evidence-panel.js

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

class EvidencePanel {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
  }

  render(evidenceList = []) {
    if (!this.container) return;

    if (evidenceList.length === 0) {
      this.container.innerHTML = `
        <div class="card">
          <h3 class="headline-sm card-title">Compliance Evidence Bundle</h3>
          <p class="body-md" style="color: var(--slate-500); font-style: italic;">No evidence compiled for this audit run.</p>
        </div>
      `;
      return;
    }

    this.container.innerHTML = `
      <div class="card" style="margin-bottom: 24px;">
        <h3 class="headline-sm card-title" style="margin-bottom: 20px;">Compliance Evidence Bundle</h3>
        
        <div class="evidence-accordion">
          ${evidenceList.map((item, idx) => {
            let title = '';
            let typeBadge = '';
            let detailsHtml = '';

            if (item.source_type === 'document') {
              title = `${escapeHtml(item.filename) || 'Document'} ${item.page ? `(Page ${item.page})` : ''}`;
              typeBadge = `<span class="evidence-type-badge type-document">Document</span>`;
              
              const scorePct = item.relevance_score ? Math.round(item.relevance_score * 100) : 0;
              detailsHtml = `
                ${item.relevance_score !== null && item.relevance_score !== undefined ? `
                  <div class="evidence-meta-item" style="margin-bottom: 8px;">
                    <span class="evidence-meta-label">Relevance Alignment</span>
                    <div class="relevance-bar-container">
                      <div class="relevance-bar">
                        <div class="relevance-fill" style="width: ${scorePct}%;"></div>
                      </div>
                      <span class="relevance-score">${item.relevance_score.toFixed(2)}</span>
                    </div>
                  </div>
                ` : ''}
                
                ${item.excerpt ? `
                  <div class="citation-box">${escapeHtml(item.excerpt)}</div>
                ` : ''}

                <div class="evidence-meta-row">
                  <div class="evidence-meta-item">
                    <span class="evidence-meta-label">Document ID</span>
                    <span class="evidence-meta-value code-sm">${escapeHtml(item.doc_id) || 'N/A'}</span>
                  </div>
                  <div class="evidence-meta-item">
                    <span class="evidence-meta-label">Document Type</span>
                    <span class="evidence-meta-value code-sm">${escapeHtml(item.doc_type) || 'N/A'}</span>
                  </div>
                  <div class="evidence-meta-item">
                    <span class="evidence-meta-label">Finding Description</span>
                    <span class="evidence-meta-value">${escapeHtml(item.finding) || 'N/A'}</span>
                  </div>
                </div>
              `;
            } else if (item.source_type === 'image') {
              title = `Audit Photograph: ${item.s3_key ? escapeHtml(item.s3_key.split('/').pop()) : 'Unspecified Key'}`;
              typeBadge = `<span class="evidence-type-badge type-image">Image Agent</span>`;

              let condBadgeClass = 'badge-info';
              if (item.condition === 'critical' || item.condition === 'poor') condBadgeClass = 'badge-danger';
              else if (item.condition === 'fair') condBadgeClass = 'badge-warning';
              else if (item.condition === 'good') condBadgeClass = 'badge-success';

              detailsHtml = `
                <div class="evidence-meta-row">
                  <div class="evidence-meta-item">
                    <span class="evidence-meta-label">S3 Bucket Path</span>
                    <span class="evidence-meta-value code-sm">${escapeHtml(item.s3_key) || 'N/A'}</span>
                  </div>
                  <div class="evidence-meta-item">
                    <span class="evidence-meta-label">Visual Condition</span>
                    <div>
                      <span class="badge ${condBadgeClass}">${escapeHtml(item.condition) || 'Unknown'}</span>
                    </div>
                  </div>
                </div>

                <div class="citation-box" style="font-family: var(--font-body); font-size: 13px;">${escapeHtml(item.image_finding || item.finding)}</div>
              `;
            } else if (item.source_type === 'auditor_remark') {
              title = 'Auditor Site Remark';
              typeBadge = `<span class="evidence-type-badge type-remark">Remark</span>`;
              detailsHtml = `
                <div class="citation-box" style="font-family: var(--font-body); font-size: 13px;">${escapeHtml(item.remark_text || item.finding)}</div>
              `;
            }

            return `
              <div class="evidence-item" id="evidence-item-${idx}">
                <div class="evidence-header" data-index="${idx}">
                  <div class="evidence-header-left">
                    <span class="evidence-index">#${idx + 1}</span>
                    ${typeBadge}
                    <span class="evidence-title">${title}</span>
                  </div>
                  <span class="evidence-toggle-icon">▼</span>
                </div>
                <div class="evidence-body">
                  <div class="evidence-content">
                    ${detailsHtml}
                  </div>
                </div>
              </div>
            `;
          }).join('')}
        </div>
      </div>
    `;

    // Add toggle event listeners
    this.container.querySelectorAll('.evidence-header').forEach(header => {
      header.addEventListener('click', (e) => {
        const item = e.currentTarget.closest('.evidence-item');
        item.classList.toggle('expanded');
      });
    });
  }

  highlightIndex(index) {
    const item = document.getElementById(`evidence-item-${index}`);
    if (!item) return;

    // Expand if collapsed
    item.classList.add('expanded');

    // Scroll into view
    item.scrollIntoView({ behavior: 'smooth', block: 'center' });

    // Flash highlight style
    item.classList.add('highlighted');
    setTimeout(() => {
      item.classList.remove('highlighted');
    }, 2000);
  }
}

window.EvidencePanel = EvidencePanel;
