(function() {
    'use strict';
    
    // Theme functionality
    const root = document.documentElement;
    const toggle = document.getElementById('themeToggle');
    const STORAGE_KEY = 'ui-theme';

    function applyTheme(theme) {
        if (theme === 'dark') {
            root.setAttribute('data-theme', 'dark');
        } else {
            root.removeAttribute('data-theme');
        }
        try {
            localStorage.setItem(STORAGE_KEY, theme);
        } catch (e) {
            console.warn('Local storage not available');
        }
        if (toggle) {
            toggle.innerHTML = theme === 'dark' 
                ? '<i class="fas fa-sun"></i><span class="label">Light</span>' 
                : '<i class="fas fa-moon"></i><span class="label">Dark</span>';
        }
    }

    function initTheme() {
        let saved = null;
        try {
            saved = localStorage.getItem(STORAGE_KEY);
        } catch (e) {
            console.warn('Local storage not available');
            saved = 'light'; // Default fallback
        }
        if (saved === 'light' || saved === 'dark') {
            applyTheme(saved);
            return;
        }
        // Default to light theme
        applyTheme('light');
    }

    if (toggle) {
        toggle.addEventListener('click', function() {
            const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
            applyTheme(isDark ? 'light' : 'dark');
        });
    }

    // Initialize theme
    initTheme();
    
    // Enhanced password toggles with duplicate-binding guard
    function bindPasswordToggles() {
        const toggles = document.querySelectorAll('[data-toggle-password]');
        toggles.forEach(function(btn) {
            if (btn.dataset.bound === '1') return; // prevent duplicate listener
            btn.dataset.bound = '1';
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                const targetId = btn.getAttribute('data-toggle-password');
                const input = document.getElementById(targetId);
                if (!input) return;
                const isPassword = (input.getAttribute('type') || input.type) === 'password';
                // Set both attribute and property for maximum compatibility
                input.setAttribute('type', isPassword ? 'text' : 'password');
                try { input.type = isPassword ? 'text' : 'password'; } catch (e) {}
                const icon = btn.querySelector('i');
                if (icon) {
                    icon.classList.toggle('fa-eye');
                    icon.classList.toggle('fa-eye-slash');
                } else {
                    btn.innerHTML = isPassword ? '<i class="far fa-eye-slash"></i>' : '<i class="far fa-eye"></i>';
                }
                input.focus();
            }, false);
        });
    }

    // Enhanced 3D click animations
    function bind3DClicks() {
        const clickable = document.querySelectorAll('a, button, .card');
        clickable.forEach(function(el) {
            el.addEventListener('mousedown', function() {
                if (el.classList.contains('btn') || el.tagName === 'BUTTON') {
                    el.style.transform = 'translateY(1px) scale(0.98)';
                }
            });
            el.addEventListener('mouseup', function() {
                if (el.classList.contains('btn') || el.tagName === 'BUTTON') {
                    el.style.transform = '';
                }
            });
            el.addEventListener('mouseleave', function() {
                if (el.classList.contains('btn') || el.tagName === 'BUTTON') {
                    el.style.transform = '';
                }
            });
        });
    }
    bind3DClicks();

    // Add active state to current page in sidebar
    function setActiveNav() {
        const currentPath = window.location.pathname;
        const navLinks = document.querySelectorAll('.sidebar a.nav-icon');
        
        navLinks.forEach(link => {
            if (link.getAttribute('href') === currentPath) {
                link.classList.add('active');
            }
        });
    }
    setActiveNav();

    // Add loading states to forms with proper handling
    function enhanceForms() {
        const forms = document.querySelectorAll('form');
        forms.forEach(form => {
            form.addEventListener('submit', function(e) {
                const submitBtn = this.querySelector('button[type="submit"]');
                if (submitBtn) {
                    submitBtn.classList.add('loading');
                    submitBtn.disabled = true;
                    
                    // Remove loading state if form submission fails
                    setTimeout(() => {
                        if (submitBtn.classList.contains('loading')) {
                            submitBtn.classList.remove('loading');
                            submitBtn.disabled = false;
                        }
                    }, 10000); // Safety timeout after 10 seconds
                }
            });
        });
        
        // Remove loading state when page is about to unload (navigation)
        window.addEventListener('beforeunload', function() {
            const loadingButtons = document.querySelectorAll('.loading');
            loadingButtons.forEach(btn => {
                btn.classList.remove('loading');
                btn.disabled = false;
            });
        });
    }
    enhanceForms();

    // Handle sidebar layout adjustment
    function adjustLayout() {
        const sidebar = document.querySelector('.sidebar');
        const layout = document.querySelector('.layout');
        
        if (sidebar && layout) {
            sidebar.addEventListener('mouseenter', function() {
                this.classList.add('hovered');
                layout.style.paddingLeft = '250px';
            });
            
            sidebar.addEventListener('mouseleave', function() {
                this.classList.remove('hovered');
                layout.style.paddingLeft = '90px';
            });
        }
    }
    adjustLayout();

    // Enhanced card animations
    function enhanceCards() {
        const cards = document.querySelectorAll('.card');
        cards.forEach(card => {
            card.addEventListener('mouseenter', function() {
                this.style.transform = 'translateY(-6px) scale(1.02)';
            });
            
            card.addEventListener('mouseleave', function() {
                this.style.transform = '';
            });
        });
    }
    enhanceCards();

    // Smooth scroll for anchor links
    function initSmoothScroll() {
        const links = document.querySelectorAll('a[href^="#"]');
        links.forEach(link => {
            link.addEventListener('click', function(e) {
                const targetId = this.getAttribute('href').substring(1);
                const targetElement = document.getElementById(targetId);
                
                if (targetElement) {
                    e.preventDefault();
                    targetElement.scrollIntoView({
                        behavior: 'smooth',
                        block: 'start'
                    });
                }
            });
        });
    }
    initSmoothScroll();

    // Initialize all functionality when DOM is loaded
    document.addEventListener('DOMContentLoaded', function() {
        // Re-bind all event listeners for dynamically loaded content
        bindPasswordToggles();
        bind3DClicks();
        setActiveNav();
        enhanceForms();
        enhanceCards();
        initSmoothScroll();
    });

    // Handle window resize for responsive adjustments
    let resizeTimeout;
    window.addEventListener('resize', function() {
        clearTimeout(resizeTimeout);
        resizeTimeout = setTimeout(function() {
            // Recalculate any size-dependent elements
            adjustLayout();
        }, 250);
    });

})();