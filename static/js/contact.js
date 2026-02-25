/**
 * =========================================
 * FARMERMAN SYSTEMS - CONTACT ENGINE
 * =========================================
 * Handles asynchronous message submission,
 * UI state management, and success animations.
 */

document.addEventListener("DOMContentLoaded", function() {
    'use strict';

    const contactForm = document.getElementById('contactForm');
    const submitBtn = document.getElementById('submitContactBtn');
    const formContainer = document.getElementById('formContainer');

    if (contactForm && submitBtn) {
        contactForm.addEventListener('submit', async function(e) {
            e.preventDefault();

            // 1. Form Validation State
            if (!contactForm.checkValidity()) {
                e.stopPropagation();
                contactForm.classList.add('was-validated');
                return;
            }

            // 2. UI Loading State
            const originalBtnHTML = submitBtn.innerHTML;
            submitBtn.disabled = true;
            submitBtn.innerHTML = `
                <span class="spinner-grow spinner-grow-sm me-2" role="status" aria-hidden="true"></span>
                Processing...
            `;

            // 3. Prepare Data
            const formData = new FormData(contactForm);
            
            try {
                // 4. Real Async Submission
                // Note: Pointing to your existing /contact POST route in main.py
                const response = await fetch('/contact', {
                    method: 'POST',
                    body: formData,
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                });

                if (response.ok) {
                    showSuccessState();
                } else {
                    throw new Error('Network response was not ok.');
                }
            } catch (error) {
                console.error('Submission Error:', error);
                resetButton(submitBtn, originalBtnHTML);
                alert('We encountered an issue sending your message. Please try again or email info@farmermansystems.com directly.');
            }
        });
    }

    /**
     * Resets button to original state on error
     */
    function resetButton(btn, html) {
        btn.disabled = false;
        btn.innerHTML = html;
    }

    /**
     * Handles the transition to the success UI using GSAP
     */
    function showSuccessState() {
        if (typeof gsap !== 'undefined') {
            // Smooth exit for the form
            gsap.to(contactForm, {
                opacity: 0,
                y: -20,
                duration: 0.5,
                onComplete: () => {
                    renderSuccessHTML();
                    // Smooth entrance for success message
                    gsap.from(".success-message", {
                        opacity: 0,
                        scale: 0.9,
                        duration: 0.8,
                        ease: "back.out(1.7)"
                    });
                }
            });
        } else {
            renderSuccessHTML();
        }
    }

    /**
     * Injects the success HTML into the container
     */
    function renderSuccessHTML() {
        formContainer.innerHTML = `
            <div class="text-center py-5 success-message">
                <div class="display-1 mb-3" style="color: var(--plant-green);">
                    <i class="bi bi-envelope-check-fill"></i>
                </div>
                <h3 class="fw-bold" style="color: var(--soil-brown);">Inquiry Received</h3>
                <p class="text-muted mx-auto" style="max-width: 400px;">
                    Thank you for reaching out. Our team in Kakamega will review your request and respond within 24 business hours.
                </p>
                <button class="btn btn-outline-success mt-3 rounded-pill px-4" onclick="location.reload()">
                    Send Another Message
                </button>
            </div>
        `;
    }
});