// Offline support for Candy Route Planner
// Uses IndexedDB to queue actions when offline

const DB_NAME = 'CandyRouteOffline';
const DB_VERSION = 1;
const STORE_NAME = 'offlineActions';

class OfflineManager {
    constructor() {
        this.db = null;
        this.isOnline = navigator.onLine;
        this.init();
    }

    async init() {
        // Initialize IndexedDB
        this.db = await this.openDB();

        // Set up online/offline listeners
        window.addEventListener('online', () => this.handleOnline());
        window.addEventListener('offline', () => this.handleOffline());

        // Update UI indicator
        this.updateIndicator();

        // Listen for service worker messages
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.addEventListener('message', (event) => {
                if (event.data.type === 'SYNC_REQUESTED') {
                    this.syncQueue();
                }
            });
        }

        // Try to sync any pending actions on load
        if (this.isOnline) {
            this.syncQueue();
        }
    }

    openDB() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(DB_NAME, DB_VERSION);

            request.onerror = () => reject(request.error);
            request.onsuccess = () => resolve(request.result);

            request.onupgradeneeded = (event) => {
                const db = event.target.result;
                if (!db.objectStoreNames.contains(STORE_NAME)) {
                    const store = db.createObjectStore(STORE_NAME, {
                        keyPath: 'id',
                        autoIncrement: true
                    });
                    store.createIndex('timestamp', 'timestamp', { unique: false });
                    store.createIndex('type', 'type', { unique: false });
                }
            };
        });
    }

    handleOnline() {
        this.isOnline = true;
        this.updateIndicator();
        this.syncQueue();
        console.log('Back online - syncing queued actions');
    }

    handleOffline() {
        this.isOnline = false;
        this.updateIndicator();
        console.log('Gone offline - actions will be queued');
    }

    updateIndicator() {
        const indicator = document.getElementById('offline-indicator');
        if (indicator) {
            if (this.isOnline) {
                indicator.classList.add('hidden');
            } else {
                indicator.classList.remove('hidden');
            }
        }
    }

    async queueAction(action) {
        if (!this.db) return;

        const transaction = this.db.transaction([STORE_NAME], 'readwrite');
        const store = transaction.objectStore(STORE_NAME);

        const record = {
            ...action,
            timestamp: Date.now(),
            synced: false
        };

        return new Promise((resolve, reject) => {
            const request = store.add(record);
            request.onsuccess = () => {
                console.log('Action queued for offline sync:', action.type);
                resolve(request.result);
            };
            request.onerror = () => reject(request.error);
        });
    }

    async getQueuedActions() {
        if (!this.db) return [];

        const transaction = this.db.transaction([STORE_NAME], 'readonly');
        const store = transaction.objectStore(STORE_NAME);

        return new Promise((resolve, reject) => {
            const request = store.getAll();
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    async removeAction(id) {
        if (!this.db) return;

        const transaction = this.db.transaction([STORE_NAME], 'readwrite');
        const store = transaction.objectStore(STORE_NAME);

        return new Promise((resolve, reject) => {
            const request = store.delete(id);
            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    }

    async syncQueue() {
        if (!this.isOnline) return;

        const actions = await this.getQueuedActions();
        console.log(`Syncing ${actions.length} queued actions`);

        for (const action of actions) {
            try {
                await this.executeAction(action);
                await this.removeAction(action.id);
                console.log('Synced action:', action.type);
            } catch (error) {
                console.error('Failed to sync action:', action.type, error);
                // Keep action in queue for retry
            }
        }

        // Refresh page after sync if there were actions
        if (actions.length > 0) {
            this.showSyncNotification(actions.length);
        }
    }

    async executeAction(action) {
        const response = await fetch(action.url, {
            method: action.method,
            headers: action.headers || {
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            body: action.body
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        return response;
    }

    showSyncNotification(count) {
        // Create a toast notification
        const toast = document.createElement('div');
        toast.className = 'fixed bottom-4 right-4 bg-good text-white px-4 py-3 rounded-lg shadow-lg z-50 animate-fade-in';
        toast.innerHTML = `
            <div class="flex items-center gap-2">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
                </svg>
                <span>${count} offline action${count > 1 ? 's' : ''} synced</span>
            </div>
        `;
        document.body.appendChild(toast);

        // Remove after 3 seconds
        setTimeout(() => {
            toast.remove();
        }, 3000);
    }

    // Helper method to wrap form submissions for offline support
    wrapFormSubmit(form, actionType) {
        form.addEventListener('submit', async (e) => {
            if (!this.isOnline) {
                e.preventDefault();

                const formData = new FormData(form);
                const urlEncodedData = new URLSearchParams(formData).toString();

                await this.queueAction({
                    type: actionType,
                    url: form.action,
                    method: form.method.toUpperCase(),
                    body: urlEncodedData
                });

                // Show offline queued notification
                this.showQueuedNotification();
            }
        });
    }

    showQueuedNotification() {
        const toast = document.createElement('div');
        toast.className = 'fixed bottom-4 right-4 bg-warn text-black px-4 py-3 rounded-lg shadow-lg z-50';
        toast.innerHTML = `
            <div class="flex items-center gap-2">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
                <span>Action queued - will sync when online</span>
            </div>
        `;
        document.body.appendChild(toast);

        setTimeout(() => {
            toast.remove();
        }, 3000);
    }
}

// Initialize offline manager
const offlineManager = new OfflineManager();

// Export for use in other scripts
window.offlineManager = offlineManager;
