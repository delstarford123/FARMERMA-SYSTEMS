/**
 * =========================================
 * FARMERMAN SYSTEMS - CORE ENGINE
 * =========================================
 * Modular controller for UI interactions,
 * brand animations, and global utilities.
 */

const FarmermanApp = (() => {
    'use strict';

    // Private Brand Configuration
    const CONFIG = {
        colors: {
            plantGreen: '#2E7D32',
            soilBrown: '#5D4037',
            skyBlue: '#0288D1'
        },
        alertDuration: 5000,
        scrollOffset: 80
    };

    /**
     * Handles Global UI Animations
     */
    const initAnimations = () => {
        const mainContent = document.querySelector('main');
        if (mainContent) {
            // Apply standard fade-in defined in style.css
            mainContent.classList.add('fade-in');
        }

        // Initialize GSAP reveals if the library is present
        if (typeof gsap !== 'undefined') {
            gsap.from(".navbar", {
                y: -100,
                opacity: 0,
                duration: 1,
                ease: "power4.out"
            });
        }
    };

    /**
     * Initializes Bootstrap components with performance optimization
     */
    const initBootstrapComponents = () => {
        // Initialize Tooltips using modern selector spread
        const tooltips = [...document.querySelectorAll('[data-bs-toggle="tooltip"]')];
        tooltips.map(el => new bootstrap.Tooltip(el));

        // Auto-dismiss logic for transactional alerts
        const autoDismissAlerts = document.querySelectorAll('.alert-auto-dismiss');
        autoDismissAlerts.forEach(alert => {
            setTimeout(() => {
                const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
                if (bsAlert) bsAlert.close();
            }, CONFIG.alertDuration);
        });
    };

    /**
     * Optimized Smooth Scrolling for anchor links
     */
    const initSmoothScroll = () => {
        document.querySelectorAll('a[href^="#"]').forEach(anchor => {
            anchor.addEventListener('click', function(e) {
                const targetId = this.getAttribute('href');
                if (targetId === '#') return;

                const targetElement = document.querySelector(targetId);
                if (targetElement) {
                    e.preventDefault();
                    window.scrollTo({
                        top: targetElement.offsetTop - CONFIG.scrollOffset,
                        behavior: 'smooth'
                    });
                }
            });
        });
    };

    /**
     * Brand-specific interactions (Magnetic buttons, etc.)
     */
    const initBrandInteractions = () => {
        const magneticBtns = document.querySelectorAll('.magnetic-btn');
        
        if (typeof gsap !== 'undefined' && magneticBtns.length > 0) {
            magneticBtns.forEach(btn => {
                btn.addEventListener('mousemove', (e) => {
                    const rect = btn.getBoundingClientRect();
                    const x = (e.clientX - rect.left - rect.width / 2) * 0.3;
                    const y = (e.clientY - rect.top - rect.height / 2) * 0.3;
                    gsap.to(btn, { x, y, duration: 0.3 });
                });

                btn.addEventListener('mouseleave', () => {
                    gsap.to(btn, { x: 0, y: 0, duration: 0.3 });
                });
            });
        }
    };

    /**
     * Public Initialization Method
     */
    const init = () => {
        console.log('FARMERMAN SYSTEMS: Initializing Engine...');
        initAnimations();
        initBootstrapComponents();
        initSmoothScroll();
        initBrandInteractions();
    };

    return { init };
})();
// --- Agripreneur Training Module Interactions ---

document.addEventListener('DOMContentLoaded', () => {
    // 1. Smooth fade-in for tabs (if you are using GSAP)
    const trainingTabs = document.querySelectorAll('button[data-bs-toggle="pill"]');
    
    trainingTabs.forEach(tab => {
        tab.addEventListener('shown.bs.tab', function (event) {
            // Target the newly active tab pane
            const targetPaneId = event.target.getAttribute('data-bs-target');
            const targetPane = document.querySelector(targetPaneId);
            
            // Simple GSAP animation for content revealing
            if (typeof gsap !== 'undefined') {
                gsap.fromTo(targetPane, 
                    { opacity: 0, y: 20 }, 
                    { opacity: 1, y: 0, duration: 0.5, ease: "power2.out" }
                );
            }
        });
    });

    // 2. Track Resource Downloads
    const downloadLinks = document.querySelectorAll('.download-link');
    downloadLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            const fileName = e.target.innerText;
            // You can replace this with an actual API call to track what your farmers are downloading
            console.log(`[Analytics] Pro User downloaded: ${fileName}`);
            
            // Optional UI feedback
            const originalText = e.target.innerText;
            e.target.innerHTML = `<i class="fas fa-spinner fa-spin"></i> Downloading...`;
            e.target.style.pointerEvents = 'none';
            
            setTimeout(() => {
                e.target.innerText = originalText;
                e.target.style.pointerEvents = 'auto';
            }, 2000);
        });
    });
});
// Execution
document.addEventListener('DOMContentLoaded', FarmermanApp.init);


