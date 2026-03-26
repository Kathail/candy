/**
 * Candy Route Planner - Main Application JavaScript
 * Centralized utilities and common functionality
 */

// ============================================
// Modal Management
// ============================================

const Modal = {
    /**
     * Open a modal by ID
     * @param {string} modalId - The ID of the modal wrapper element
     */
    open(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.style.display = 'block';
            document.body.style.overflow = 'hidden';
        }
    },

    /**
     * Close a modal by ID
     * @param {string} modalId - The ID of the modal wrapper element
     */
    close(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.style.display = 'none';
            document.body.style.overflow = '';
            // Reset any forms inside the modal
            const form = modal.querySelector('form');
            if (form) form.reset();
        }
    },

    /**
     * Load content into a modal via fetch
     * @param {string} modalId - The modal wrapper ID
     * @param {string} contentId - The content container ID inside the modal
     * @param {string} url - URL to fetch content from
     */
    async loadContent(modalId, contentId, url) {
        const modal = document.getElementById(modalId);
        const content = document.getElementById(contentId);

        if (!modal || !content) return;

        modal.style.display = 'block';
        document.body.style.overflow = 'hidden';

        // Show loading state
        content.innerHTML = `
            <div class="text-center py-4">
                <div class="animate-spin w-8 h-8 border-4 border-brand border-t-transparent rounded-full mx-auto"></div>
                <div class="text-xs text-muted mt-2">Loading...</div>
            </div>
        `;

        try {
            const response = await fetch(url);
            if (!response.ok) throw new Error('Network response was not ok');
            const html = await response.text();
            content.innerHTML = html;
        } catch (error) {
            console.error('Error loading modal content:', error);
            Modal.close(modalId);
            Toast.error('Failed to load content');
        }
    }
};

// ============================================
// Toast Notifications
// ============================================

const Toast = {
    /**
     * Show a toast notification
     * @param {string} message - The message to display
     * @param {string} type - 'success', 'error', 'warning', 'info'
     * @param {number} duration - Duration in ms (default 3000)
     */
    show(message, type = 'info', duration = 3000) {
        const colors = {
            success: 'bg-good text-white',
            error: 'bg-danger text-white',
            warning: 'bg-warn text-black',
            info: 'bg-brand text-white'
        };

        const icons = {
            success: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>',
            error: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>',
            warning: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>',
            info: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>'
        };

        const toast = document.createElement('div');
        toast.className = `fixed bottom-4 right-4 ${colors[type]} px-4 py-3 rounded-lg shadow-lg z-50 flex items-center gap-2 animate-fade-in`;
        toast.innerHTML = `
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                ${icons[type]}
            </svg>
            <span>${message}</span>
        `;

        document.body.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transition = 'opacity 0.3s';
            setTimeout(() => toast.remove(), 300);
        }, duration);
    },

    success(message, duration) {
        this.show(message, 'success', duration);
    },

    error(message, duration) {
        this.show(message, 'error', duration);
    },

    warning(message, duration) {
        this.show(message, 'warning', duration);
    },

    info(message, duration) {
        this.show(message, 'info', duration);
    }
};

// ============================================
// API / Fetch Helpers
// ============================================

const Api = {
    /**
     * Get CSRF token from the page
     */
    getCsrfToken() {
        const input = document.querySelector('input[name="csrf_token"]');
        return input ? input.value : '';
    },

    /**
     * Make a POST request with CSRF token
     * @param {string} url - The URL to post to
     * @param {object} data - Data to send (will be form-encoded)
     */
    async post(url, data = {}) {
        const formData = new URLSearchParams();
        formData.append('csrf_token', this.getCsrfToken());

        for (const [key, value] of Object.entries(data)) {
            formData.append(key, value);
        }

        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: formData
        });

        return response;
    },

    /**
     * Make a JSON POST request
     * @param {string} url - The URL to post to
     * @param {object} data - Data to send as JSON
     */
    async postJson(url, data = {}) {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCsrfToken()
            },
            body: JSON.stringify(data)
        });

        return response.json();
    }
};

// ============================================
// Utility Functions
// ============================================

const Utils = {
    /**
     * Format a number as currency
     * @param {number} amount
     */
    formatCurrency(amount) {
        return '$' + parseFloat(amount).toFixed(2);
    },

    /**
     * Format a date string
     * @param {string} dateStr - ISO date string
     * @param {object} options - Intl.DateTimeFormat options
     */
    formatDate(dateStr, options = { month: 'short', day: 'numeric', year: 'numeric' }) {
        return new Date(dateStr).toLocaleDateString('en-US', options);
    },

    /**
     * Debounce a function
     * @param {function} func - Function to debounce
     * @param {number} wait - Wait time in ms
     */
    debounce(func, wait = 300) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    },

    /**
     * Copy text to clipboard
     * @param {string} text
     */
    async copyToClipboard(text) {
        try {
            await navigator.clipboard.writeText(text);
            Toast.success('Copied to clipboard');
        } catch (err) {
            Toast.error('Failed to copy');
        }
    }
};

// ============================================
// Initialize on DOM Ready
// ============================================

document.addEventListener('DOMContentLoaded', () => {
    // Close modals on escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            document.querySelectorAll('[id$="-modal-wrapper"]').forEach(modal => {
                if (modal.style.display === 'block') {
                    Modal.close(modal.id);
                }
            });
        }
    });

    // Add fade-in animation class
    const style = document.createElement('style');
    style.textContent = `
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .animate-fade-in {
            animation: fadeIn 0.3s ease-out;
        }
    `;
    document.head.appendChild(style);

    // HTMX loading indicator setup
    const globalLoader = document.getElementById('global-loader');
    if (globalLoader) {
        document.body.addEventListener('htmx:beforeRequest', () => {
            globalLoader.style.transform = 'scaleX(0.3)';
        });
        document.body.addEventListener('htmx:afterRequest', () => {
            globalLoader.style.transform = 'scaleX(1)';
            setTimeout(() => {
                globalLoader.style.transform = 'scaleX(0)';
            }, 200);
        });
    }
});

// ============================================
// Confirmation Dialog
// ============================================

const Confirm = {
    /**
     * Show a confirmation dialog
     * @param {object} options - Configuration options
     * @param {string} options.title - Dialog title
     * @param {string} options.message - Dialog message
     * @param {string} options.confirmText - Confirm button text (default: 'Confirm')
     * @param {string} options.cancelText - Cancel button text (default: 'Cancel')
     * @param {string} options.type - 'danger', 'warning', 'info' (default: 'danger')
     * @returns {Promise<boolean>} - Resolves true if confirmed, false if cancelled
     */
    show(options = {}) {
        return new Promise((resolve) => {
            const {
                title = 'Are you sure?',
                message = 'This action cannot be undone.',
                confirmText = 'Confirm',
                cancelText = 'Cancel',
                type = 'danger'
            } = options;

            const colors = {
                danger: 'bg-danger hover:bg-red-600',
                warning: 'bg-warn hover:bg-yellow-500 text-black',
                info: 'bg-brand hover:bg-blue-700'
            };

            // Create modal HTML
            const modal = document.createElement('div');
            modal.id = 'confirm-dialog';
            modal.className = 'fixed inset-0 z-[100] flex items-center justify-center p-4';
            modal.innerHTML = `
                <div class="fixed inset-0 bg-black/50" id="confirm-overlay"></div>
                <div class="relative bg-panel rounded-xl shadow-2xl max-w-md w-full p-6 animate-fade-in">
                    <h3 class="text-lg font-semibold mb-2">${title}</h3>
                    <p class="text-sm text-muted mb-6">${message}</p>
                    <div class="flex gap-3">
                        <button id="confirm-cancel" class="flex-1 bg-panel2 hover:bg-border text-white text-sm font-semibold px-4 py-2 rounded-md transition">
                            ${cancelText}
                        </button>
                        <button id="confirm-ok" class="flex-1 ${colors[type]} text-white text-sm font-semibold px-4 py-2 rounded-md transition">
                            ${confirmText}
                        </button>
                    </div>
                </div>
            `;

            document.body.appendChild(modal);
            document.body.style.overflow = 'hidden';

            const cleanup = (result) => {
                document.body.style.overflow = '';
                modal.remove();
                resolve(result);
            };

            modal.querySelector('#confirm-ok').addEventListener('click', () => cleanup(true));
            modal.querySelector('#confirm-cancel').addEventListener('click', () => cleanup(false));
            modal.querySelector('#confirm-overlay').addEventListener('click', () => cleanup(false));

            // Handle escape key
            const handleEscape = (e) => {
                if (e.key === 'Escape') {
                    document.removeEventListener('keydown', handleEscape);
                    cleanup(false);
                }
            };
            document.addEventListener('keydown', handleEscape);
        });
    },

    /**
     * Show a delete confirmation
     * @param {string} itemName - Name of item being deleted
     */
    delete(itemName = 'this item') {
        return this.show({
            title: 'Delete Confirmation',
            message: `Are you sure you want to delete ${itemName}? This action cannot be undone.`,
            confirmText: 'Delete',
            type: 'danger'
        });
    }
};

// Export for use in other scripts
window.Modal = Modal;
window.Toast = Toast;
window.Api = Api;
window.Utils = Utils;
window.Confirm = Confirm;
