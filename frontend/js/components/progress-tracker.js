// js/components/progress-tracker.js

class ProgressTracker {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.steps = [
      { id: 'document_agent', name: 'Document Agent', label: 'RAG Retrieval' },
      { id: 'image_agent', name: 'Image Agent', label: 'Vision Inspection' },
      { id: 'rule_agent', name: 'Rule Agent', label: 'Rule Verification' },
      { id: 'evidence_agent', name: 'Evidence Agent', label: 'Evidence Bundle' },
      { id: 'verdict_agent', name: 'Verdict Agent', label: 'Final Verdict' }
    ];
    this.currentStepIndex = -1;
    this.render();
  }

  render() {
    if (!this.container) return;

    this.container.innerHTML = `
      <div class="pipeline-tracker">
        ${this.steps.map((step, idx) => `
          <div class="pipeline-step pending" id="step-${step.id}">
            <div class="step-node" id="node-${step.id}">${idx + 1}</div>
            <div class="step-details">
              <div class="step-name">${step.name}</div>
              <div class="step-label">${step.label}</div>
            </div>
          </div>
        `).join('')}
      </div>
    `;
  }

  updateNode(nodeId, status) {
    // status: 'active' | 'completed' | 'error' | 'pending'
    const stepEl = document.getElementById(`step-${nodeId}`);
    const nodeEl = document.getElementById(`node-${nodeId}`);
    if (!stepEl || !nodeEl) return;

    // Reset classes
    stepEl.className = `pipeline-step ${status}`;
    
    // Set icon or step number
    const stepIndex = this.steps.findIndex(s => s.id === nodeId);
    if (status === 'completed') {
      nodeEl.innerHTML = `
        <svg style="width: 18px; height: 18px;" fill="none" stroke="currentColor" stroke-width="3" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"></path>
        </svg>
      `;
    } else if (status === 'error') {
      nodeEl.innerHTML = `
        <svg style="width: 18px; height: 18px;" fill="none" stroke="currentColor" stroke-width="3" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"></path>
        </svg>
      `;
    } else {
      nodeEl.textContent = stepIndex + 1;
    }
  }

  setCurrentStep(nodeId) {
    // Mark previous steps as completed if they are still pending/active
    const index = this.steps.findIndex(s => s.id === nodeId);
    if (index === -1) return;

    this.currentStepIndex = index;

    this.steps.forEach((step, idx) => {
      if (idx < index) {
        // Only mark complete if it wasn't already marked error
        const stepEl = document.getElementById(`step-${step.id}`);
        if (!stepEl.classList.contains('error')) {
          this.updateNode(step.id, 'completed');
        }
      } else if (idx === index) {
        this.updateNode(step.id, 'active');
      } else {
        this.updateNode(step.id, 'pending');
      }
    });
  }

  markComplete(nodeId) {
    this.updateNode(nodeId, 'completed');
  }

  markError(nodeId) {
    this.updateNode(nodeId, 'error');
  }

  reset() {
    this.currentStepIndex = -1;
    this.steps.forEach(step => {
      this.updateNode(step.id, 'pending');
    });
  }
}

window.ProgressTracker = ProgressTracker;

if (typeof module !== 'undefined' && module.exports) {
  module.exports = ProgressTracker;
}
