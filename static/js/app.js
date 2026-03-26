/**
 * Candy Route Planner — app.js
 */

// ---- Modal Management ----

const Modal = {
    open(modalId) {
        const el = document.getElementById(modalId);
        if (!el) return;
        el.style.display = 'block';
        document.body.style.overflow = 'hidden';
    },

    close(modalId) {
        const el = document.getElementById(modalId);
        if (!el) return;
        el.style.display = 'none';
        document.body.style.overflow = '';
    },

    async loadContent(modalId, contentId, url) {
        const modal = document.getElementById(modalId);
        const content = document.getElementById(contentId);
        if (!modal || !content) return;

        modal.style.display = 'block';
        document.body.style.overflow = 'hidden';
        content.innerHTML = '<div class="text-center py-4"><div class="loading-spinner mx-auto"></div></div>';

        try {
            const res = await fetch(url);
            if (!res.ok) throw new Error(res.status);
            content.innerHTML = await res.text();
        } catch (e) {
            Modal.close(modalId);
        }
    }
};

// ---- Toast Notifications ----

const Toast = {
    show(message, type = 'info', duration = 3000) {
        const colors = { success: 'bg-good', error: 'bg-danger', warning: 'bg-warn text-black', info: 'bg-brand' };
        const el = document.createElement('div');
        el.className = `fixed bottom-20 left-4 right-4 md:bottom-4 md:left-auto md:right-4 md:w-auto ${colors[type] || colors.info} text-white px-4 py-3 rounded-lg shadow-lg z-50 text-center text-sm font-semibold`;
        el.textContent = message;
        document.body.appendChild(el);
        setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity 0.3s'; setTimeout(() => el.remove(), 300); }, duration);
    },
    success(msg) { this.show(msg, 'success'); },
    error(msg) { this.show(msg, 'error'); }
};

// ---- Utils ----

const Utils = {
    formatCurrency(amount) { return '$' + parseFloat(amount).toFixed(2); }
};

// ---- Confirm Dialog ----

const Confirm = {
    show({ title = 'Are you sure?', message = 'This action cannot be undone.', confirmText = 'Confirm', type = 'danger' } = {}) {
        return new Promise((resolve) => {
            const colors = { danger: 'bg-danger hover:bg-red-600', warning: 'bg-warn hover:bg-yellow-500 text-black', info: 'bg-brand hover:bg-blue-700' };
            const el = document.createElement('div');
            el.className = 'fixed inset-0 z-[100] flex items-center justify-center p-4';
            el.innerHTML = `
                <div class="fixed inset-0 bg-black/50" data-action="cancel"></div>
                <div class="relative bg-panel rounded-xl shadow-2xl max-w-sm w-full p-6">
                    <h3 class="text-lg font-semibold mb-2">${title}</h3>
                    <p class="text-sm text-muted mb-6">${message}</p>
                    <div class="flex gap-3">
                        <button data-action="cancel" class="flex-1 bg-panel2 hover:bg-border text-white text-sm font-semibold px-4 py-3 rounded-md transition">Cancel</button>
                        <button data-action="confirm" class="flex-1 ${colors[type]} text-white text-sm font-semibold px-4 py-3 rounded-md transition">${confirmText}</button>
                    </div>
                </div>`;
            document.body.appendChild(el);
            document.body.style.overflow = 'hidden';

            const done = (result) => { document.body.style.overflow = ''; el.remove(); resolve(result); };
            el.addEventListener('click', (e) => {
                const action = e.target.dataset.action;
                if (action === 'confirm') done(true);
                else if (action === 'cancel') done(false);
            });
            const esc = (e) => { if (e.key === 'Escape') { document.removeEventListener('keydown', esc); done(false); } };
            document.addEventListener('keydown', esc);
        });
    },

    delete(name = 'this item') {
        return this.show({ title: 'Delete Confirmation', message: `Delete ${name}? This cannot be undone.`, confirmText: 'Delete', type: 'danger' });
    }
};

// ---- Global Handlers (called from HTMX-loaded partials) ----

window.confirmDeleteCustomer = async (name) => { if (await Confirm.delete(name)) document.getElementById('delete-customer-form').submit(); };
window.confirmDeleteLead = async (name) => { if (await Confirm.delete(name)) document.getElementById('delete-lead-form').submit(); };
window.confirmDeleteUser = async (form, name) => { if (await Confirm.delete(name)) form.submit(); };
window.toggleAddTransaction = () => { const f = document.getElementById('add-transaction-form'); if (f) f.style.display = f.style.display === 'none' ? 'block' : 'none'; };
window.toggleQuickPayment = (id) => { const f = document.getElementById('quick-payment-' + id); const b = document.getElementById('payment-btn-' + id); if (f && b) { f.classList.toggle('hidden'); b.classList.toggle('hidden'); } };
window.setQuickPayment = (id, amt) => { const f = document.getElementById('quick-payment-' + id); if (f) { const i = f.querySelector('input[name="amount"]'); if (i) i.value = amt.toFixed(2); } };

// ---- Init ----

document.addEventListener('DOMContentLoaded', () => {
    // Escape closes modals
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') document.querySelectorAll('[id$="-modal-wrapper"]').forEach(m => { if (m.style.display === 'block') Modal.close(m.id); });
    });

    // HTMX global loading bar
    const loader = document.getElementById('global-loader');
    if (loader) {
        document.body.addEventListener('htmx:beforeRequest', () => { loader.style.transform = 'scaleX(0.3)'; });
        document.body.addEventListener('htmx:afterRequest', () => { loader.style.transform = 'scaleX(1)'; setTimeout(() => { loader.style.transform = 'scaleX(0)'; }, 200); });
    }
});

// ---- Exports ----

window.Modal = Modal;
window.Toast = Toast;
window.Utils = Utils;
window.Confirm = Confirm;
