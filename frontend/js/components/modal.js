/* Modal Component - Asset Compliance AI */

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

  class ModalManager {
    constructor() {
      // Configuration
    }

    /**
     * Create and display a modal overlay
     * @param {object} params Modal configuration params
     * @param {string} params.title Title string
     * @param {string} params.content Body content HTML or text (callers must sanitize user data)
     * @param {string} params.confirmText Confirm button text
     * @param {string} params.cancelText Cancel button text
     * @param {function} params.onConfirm Callback on confirm click (passes close helper)
     * @param {function} params.onCancel Callback on cancel click (passes close helper)
     * @param {string} params.variant Theme variant ('primary' | 'danger' | 'warning')
     * @returns {object} Close handler
     */
    create({
      title,
      content,
      confirmText = 'Confirm',
      cancelText = 'Cancel',
      onConfirm = null,
      onCancel = null,
      variant = 'primary'
    }) {
      // Create modal backdrop container
      const backdrop = document.createElement('div');
      backdrop.setAttribute('role', 'dialog');
      backdrop.setAttribute('aria-modal', 'true');
      Object.assign(backdrop.style, {
        position: 'fixed',
        top: '0',
        left: '0',
        right: '0',
        bottom: '0',
        backgroundColor: 'rgba(5, 7, 10, 0.75)',
        backdropFilter: 'blur(4px)',
        zIndex: '999',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '24px',
        opacity: '0',
        transition: 'opacity 0.2s ease-in-out'
      });

      // Create modal layout panel
      const modal = document.createElement('div');
      modal.className = 'card';
      Object.assign(modal.style, {
        backgroundColor: 'var(--slate-800)',
        border: '1px solid var(--slate-700)',
        boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5), 0 10px 10px -5px rgba(0, 0, 0, 0.4)',
        maxWidth: '520px',
        width: '100%',
        padding: '24px',
        transform: 'scale(0.95)',
        transition: 'transform 0.2s cubic-bezier(0.16, 1, 0.3, 1)'
      });

      // Set primary action buttons color-coding based on type
      let confirmBtnClass = 'btn-primary';
      if (variant === 'danger') confirmBtnClass = 'btn-danger';
      if (variant === 'warning') confirmBtnClass = 'btn-warning';

      const titleId = `modal-title-${Date.now()}`;
      backdrop.setAttribute('aria-labelledby', titleId);

      modal.innerHTML = `
        <div class="card-header" style="border-bottom: 1px solid var(--slate-700); margin-bottom: 16px; padding-bottom: 12px;">
          <h3 class="card-title modal-title" id="${titleId}" style="font-family: var(--font-headings); font-size: var(--fs-headline-sm); font-weight: var(--fw-headline-sm); color: var(--on-surface);"></h3>
          <button class="modal-close-btn" aria-label="Close" style="
            background: none;
            border: none;
            color: var(--on-surface-variant);
            cursor: pointer;
            font-size: 24px;
            line-height: 1;
            padding: 0 4px;
          ">&times;</button>
        </div>
        <div class="card-body modal-content" style="color: var(--on-surface-variant); margin-bottom: 24px; font-family: var(--font-body); font-size: var(--fs-body-md); line-height: 1.5;">
        </div>
        <div class="card-footer" style="border-top: none; padding-top: 0; display: flex; justify-content: flex-end; gap: 12px; margin-top: 0;">
          <button class="btn btn-secondary modal-cancel-btn"></button>
          <button class="btn ${confirmBtnClass} modal-confirm-btn"></button>
        </div>
      `;

      // Set values safely using textContent
      modal.querySelector('.modal-title').textContent = escapeHtml(title);
      modal.querySelector('.modal-content').innerHTML = content; // Callers must sanitize
      modal.querySelector('.modal-cancel-btn').textContent = cancelText;
      modal.querySelector('.modal-confirm-btn').textContent = confirmText;

      backdrop.appendChild(modal);
      document.body.appendChild(backdrop);

      // Force paint rendering and animate in
      backdrop.offsetHeight;
      backdrop.style.opacity = '1';
      modal.style.transform = 'scale(1)';

      const close = () => {
        backdrop.style.opacity = '0';
        modal.style.transform = 'scale(0.95)';
        
        const cleanup = () => {
          backdrop.removeEventListener('transitionend', cleanup);
          backdrop.remove();
        };
        
        backdrop.addEventListener('transitionend', cleanup);
      };

      // Button listener attachments
      const cancelBtn = modal.querySelector('.modal-cancel-btn');
      const confirmBtn = modal.querySelector('.modal-confirm-btn');
      const closeBtn = modal.querySelector('.modal-close-btn');

      cancelBtn.addEventListener('click', () => {
        if (onCancel) {
          onCancel(close);
        } else {
          close();
        }
      });

      confirmBtn.addEventListener('click', () => {
        if (onConfirm) {
          onConfirm(close);
        } else {
          close();
        }
      });

      closeBtn.addEventListener('click', () => {
        close();
      });

      // Close modal on click of outside wrapper
      backdrop.addEventListener('click', (e) => {
        if (e.target === backdrop) {
          close();
        }
      });

      // Accessible ESC key dismiss handler
      const keyHandler = (e) => {
        if (e.key === 'Escape') {
          document.removeEventListener('keydown', keyHandler);
          close();
        }
      };
      document.addEventListener('keydown', keyHandler);

      return { close };
    }
  }

  window.Modal = new ModalManager();

  /**
   * Bind standard open/close modal triggers.
   * @param {string} modalId - DOM id of the modal element
   * @param {Array<HTMLElement>} openTriggers - elements that open the modal
   * @param {Array<HTMLElement>} closeTriggers - elements that close the modal
   * @returns {{modal: HTMLElement, closeModal: Function}}
   */
  window.Modal.bindStandardModal = function (modalId, openTriggers, closeTriggers) {
    const modal = document.getElementById(modalId);
    const closeModal = () => modal.classList.remove('open');

    openTriggers.forEach(trigger => {
      trigger.addEventListener('click', () => modal.classList.add('open'));
    });

    closeTriggers.forEach(trigger => {
      trigger.addEventListener('click', closeModal);
    });

    return { modal, closeModal };
  };
})();
