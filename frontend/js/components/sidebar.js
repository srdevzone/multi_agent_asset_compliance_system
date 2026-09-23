/* Sidebar Component - Asset Compliance AI */

(function () {
  const Sidebar = {
    init() {
      // Setup Logout button handler
      const logoutBtn = document.getElementById('sidebar-logout-btn');
      if (logoutBtn) {
        // Remove existing listener if any (to prevent multiple event firing)
        const newLogoutBtn = logoutBtn.cloneNode(true);
        logoutBtn.parentNode.replaceChild(newLogoutBtn, logoutBtn);
        
        newLogoutBtn.addEventListener('click', (e) => {
          e.preventDefault();
          
          if (window.Modal) {
            window.Modal.create({
              title: 'Confirm Sign Out',
              content: 'Are you sure you want to sign out? Your API key will be cleared from local storage.',
              confirmText: 'Sign Out',
              cancelText: 'Cancel',
              variant: 'danger',
              onConfirm: (close) => {
                if (window.Config) {
                  window.Config.set('apiKey', '');
                  window.Config.addActivity('Authentication', 'User manually signed out', 'info');
                }
                close();
                window.location.hash = '#/login';
              }
            });
          } else {
            // Fallback if Modal is not loaded
            if (confirm('Sign out of Asset Compliance AI?')) {
              if (window.Config) {
                window.Config.set('apiKey', '');
              }
              window.location.hash = '#/login';
            }
          }
        });
      }

      // Handle mobile responsive navigation sidebar toggle
      const mobileToggle = document.getElementById('mobile-sidebar-toggle');
      const sidebarContainer = document.querySelector('.sidebar-container');
      if (mobileToggle && sidebarContainer) {
        mobileToggle.addEventListener('click', () => {
          sidebarContainer.classList.toggle('active');
        });
        
        // Close sidebar on navigate in mobile view
        const navLinks = document.querySelectorAll('.sidebar-nav-link');
        navLinks.forEach(link => {
          link.addEventListener('click', () => {
            sidebarContainer.classList.remove('active');
          });
        });
      }

      // Handle desktop sidebar collapse/expand toggle
      this.initCollapse();
    },

    initCollapse() {
      const toggleBtn = document.getElementById('desktop-sidebar-toggle');
      const sidebarContainer = document.querySelector('.sidebar-container');
      const mainViewport = document.querySelector('.main-viewport');
      
      if (!toggleBtn || !sidebarContainer || !mainViewport) {
        console.log('Sidebar collapse elements not found:', { toggleBtn: !!toggleBtn, sidebarContainer: !!sidebarContainer, mainViewport: !!mainViewport });
        return;
      }

      // Restore saved state from localStorage
      const savedState = localStorage.getItem('sidebarCollapsed');
      if (savedState === 'true') {
        sidebarContainer.classList.add('collapsed');
        mainViewport.classList.add('sidebar-collapsed');
        this.updateToggleIcon(toggleBtn, true);
      }

      // Toggle button click handler
      toggleBtn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        
        const isCollapsed = sidebarContainer.classList.contains('collapsed');
        
        if (isCollapsed) {
          // Expand sidebar
          sidebarContainer.classList.remove('collapsed');
          mainViewport.classList.remove('sidebar-collapsed');
          localStorage.setItem('sidebarCollapsed', 'false');
          this.updateToggleIcon(toggleBtn, false);
        } else {
          // Collapse sidebar
          sidebarContainer.classList.add('collapsed');
          mainViewport.classList.add('sidebar-collapsed');
          localStorage.setItem('sidebarCollapsed', 'true');
          this.updateToggleIcon(toggleBtn, true);
        }
      });
    },

    updateToggleIcon(button, isCollapsed) {
      if (isCollapsed) {
        button.innerHTML = '»'; // Right chevron when collapsed
        button.title = 'Expand sidebar';
      } else {
        button.innerHTML = '«'; // Left chevron when expanded
        button.title = 'Collapse sidebar';
      }
    }
  };

  window.Sidebar = Sidebar;
  
  // Run on layout initialization
  document.addEventListener('DOMContentLoaded', () => {
    Sidebar.init();
  });
})();
