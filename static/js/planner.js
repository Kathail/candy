    const CSRF_TOKEN = window.__PLANNER_CSRF__;

    function csrfFormData(data = {}) {
        const fd = new FormData();
        fd.append('csrf_token', CSRF_TOKEN);
        for (const [k, v] of Object.entries(data)) fd.append(k, v);
        return fd;
    }

    function csrfPost(url) {
        return fetch(url, {
            method: 'POST',
            headers: { 'X-CSRFToken': CSRF_TOKEN }
        });
    }

    function csrfJson(url, data, method = 'POST') {
        return fetch(url, {
            method,
            headers: { 'X-CSRFToken': CSRF_TOKEN, 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
    }

    function formatDateLocal(date) {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    }

    function plannerPage() {
        return {
            // Customer pool
            query: '',
            customerFilter: 'all',
            customerSort: 'urgency',
            customers: window.__PLANNER_CUSTOMERS__,
            filteredCustomers: [],

            // Stops
            allStops: {},
            currentStops: [],

            // Week strip
            weekStartDate: null,  // Monday of current week view

            // Calendar
            showCalendar: false,
            calendarYear: new Date().getFullYear(),
            calendarMonth: new Date().getMonth(),
            calendarDays: [],

            // Date selection
            selectedDate: null,

            // Modals
            showCustomerModal: false,
            selectedCustomer: null,
            loadingCustomerDetails: false,
            customerDetails: null,

            showCityBulkAdd: false,
            cityGroups: [],

            showTemplates: false,
            templates: [],

            showCopyRoute: false,
            copySourceDate: '',

            // Drag and drop
            dragIndex: null,

            init() {
                this.filteredCustomers = this.customers;
                this.loadAllStops().then(() => {
                    this.goToToday();
                    this.generateCalendar();
                });
                this.groupCustomersByCity();
                this.sortAndFilterCustomers();
            },

            // ===== WEEK STRIP =====

            get weekDays() {
                if (!this.weekStartDate) return [];
                const days = [];
                for (let i = 0; i < 6; i++) {  // Mon-Sat
                    const d = new Date(this.weekStartDate);
                    d.setDate(d.getDate() + i);
                    const dateStr = formatDateLocal(d);
                    const today = formatDateLocal(new Date());
                    const stops = this.allStops[dateStr] || [];
                    days.push({
                        date: dateStr,
                        dayName: d.toLocaleDateString('en-US', { weekday: 'short' }),
                        dayNum: d.getDate(),
                        monthName: d.toLocaleDateString('en-US', { month: 'short' }),
                        isToday: dateStr === today,
                        isSelected: dateStr === this.selectedDate,
                        stopCount: stops.length,
                    });
                }
                return days;
            },

            prevWeek() {
                const d = new Date(this.weekStartDate);
                d.setDate(d.getDate() - 7);
                this.weekStartDate = formatDateLocal(d);
            },

            nextWeek() {
                const d = new Date(this.weekStartDate);
                d.setDate(d.getDate() + 7);
                this.weekStartDate = formatDateLocal(d);
            },

            goToToday() {
                const today = new Date();
                // Find Monday of this week
                const dayOfWeek = today.getDay();
                const monday = new Date(today);
                monday.setDate(today.getDate() - (dayOfWeek === 0 ? 6 : dayOfWeek - 1));
                this.weekStartDate = formatDateLocal(monday);

                this.selectedDate = formatDateLocal(today);
                this.loadStopsForDate();

                this.calendarYear = today.getFullYear();
                this.calendarMonth = today.getMonth();
            },

            selectDate(dateStr) {
                this.selectedDate = dateStr;
                this.loadStopsForDate();
                this.generateCalendar();
            },

            // ===== CUSTOMER POOL =====

            sortAndFilterCustomers() {
                let filtered = [...this.customers];

                // Text search
                if (this.query) {
                    const q = this.query.toLowerCase();
                    filtered = filtered.filter(c =>
                        c.name.toLowerCase().includes(q) ||
                        c.city.toLowerCase().includes(q)
                    );
                }

                // Filter
                if (this.customerFilter === 'never') {
                    filtered = filtered.filter(c => !c.last_visit);
                } else if (this.customerFilter === 'overdue') {
                    filtered = filtered.filter(c => c.needs_visit);
                } else if (this.customerFilter === 'balance') {
                    filtered = filtered.filter(c => c.balance > 0);
                }

                // Exclude already scheduled
                if (this.selectedDate && this.currentStops.length > 0) {
                    const scheduledIds = this.currentStops.map(s => s.customer_id);
                    filtered = filtered.filter(c => !scheduledIds.includes(c.id));
                }

                // Sort
                if (this.customerSort === 'urgency') {
                    filtered.sort((a, b) => b.days_overdue - a.days_overdue);
                } else if (this.customerSort === 'balance') {
                    filtered.sort((a, b) => b.balance - a.balance);
                } else if (this.customerSort === 'name') {
                    filtered.sort((a, b) => a.name.localeCompare(b.name));
                } else if (this.customerSort === 'city') {
                    filtered.sort((a, b) => a.city.localeCompare(b.city) || a.name.localeCompare(b.name));
                }

                this.filteredCustomers = filtered;
            },

            setFilter(f) {
                this.customerFilter = f;
                this.sortAndFilterCustomers();
            },

            setSort(s) {
                this.customerSort = s;
                this.sortAndFilterCustomers();
            },

            // ===== STOPS =====

            async loadAllStops() {
                try {
                    const response = await fetch('/planner/all-stops');
                    const data = await response.json();
                    this.allStops = data.stops;
                } catch (error) {
                    console.error('Error loading stops:', error);
                }
            },

            loadStopsForDate() {
                if (!this.selectedDate) return;
                this.currentStops = [...(this.allStops[this.selectedDate] || [])];
                this.sortAndFilterCustomers();
            },

            async addToRoute(customer, silent = false) {
                if (!this.selectedDate) {
                    if (!silent) alert('Please select a date first!');
                    return;
                }

                const formData = csrfFormData({
                    'customer_id': customer.id,
                    'route_date': this.selectedDate
                });

                try {
                    const response = await fetch('/planner/add-stop', {
                        method: 'POST',
                        body: formData
                    });

                    const data = await response.json();

                    if (data.success) {
                        this.currentStops.push({
                            id: data.stop_id,
                            customer_id: customer.id,
                            customer_name: data.customer_name || customer.name,
                            customer_city: data.customer_city || customer.city,
                            customer_balance: data.customer_balance || customer.balance || 0,
                            sequence: this.currentStops.length + 1
                        });

                        this.allStops[this.selectedDate] = [...this.currentStops];
                        this.sortAndFilterCustomers();

                        if (!silent) this.showToast(`Added ${customer.name}`);
                    } else if (!silent) {
                        this.showToast(data.error || 'Failed to add', true);
                    }
                } catch (error) {
                    console.error('Error:', error);
                    if (!silent) this.showToast('Failed to add stop', true);
                }
            },

            async removeStop(stopId) {
                try {
                    const response = await csrfPost(`/planner/stop/${stopId}/remove`);
                    const data = await response.json();

                    if (data.success) {
                        this.currentStops = this.currentStops.filter(s => s.id !== stopId);
                        this.allStops[this.selectedDate] = [...this.currentStops];
                        this.sortAndFilterCustomers();
                        this.showToast('Stop removed');
                    }
                } catch (error) {
                    console.error('Error:', error);
                }
            },

            async optimizeRoute() {
                if (!this.selectedDate || this.currentStops.length === 0) return;

                try {
                    const response = await csrfPost(`/planner/route/${this.selectedDate}/optimize`);
                    const data = await response.json();

                    if (data.success) {
                        this.currentStops = data.stops;
                        this.allStops[this.selectedDate] = [...this.currentStops];
                        this.showToast('Route optimized!');
                    }
                } catch (error) {
                    console.error('Error:', error);
                }
            },

            async clearRoute(silent = false) {
                if (!silent && !confirm('Clear all stops from this route?')) return;

                try {
                    const response = await csrfPost(`/planner/route/${this.selectedDate}/clear`);
                    const data = await response.json();

                    if (data.success) {
                        this.currentStops = [];
                        this.allStops[this.selectedDate] = [];
                        this.sortAndFilterCustomers();
                        if (!silent) this.showToast('Route cleared');
                    }
                } catch (error) {
                    console.error('Error:', error);
                }
            },

            // ===== DRAG AND DROP =====

            onDragStart(index) {
                this.dragIndex = index;
            },

            onDragOver(event, index) {
                event.preventDefault();
            },

            async onDrop(index) {
                if (this.dragIndex === null || this.dragIndex === index) {
                    this.dragIndex = null;
                    return;
                }

                const item = this.currentStops.splice(this.dragIndex, 1)[0];
                this.currentStops.splice(index, 0, item);

                // Update sequences locally
                this.currentStops.forEach((s, i) => s.sequence = i + 1);
                this.allStops[this.selectedDate] = [...this.currentStops];
                this.dragIndex = null;

                // Persist to backend
                try {
                    await csrfJson(`/planner/route/${this.selectedDate}/reorder`, {
                        stop_ids: this.currentStops.map(s => s.id)
                    });
                } catch (error) {
                    console.error('Error saving order:', error);
                }
            },

            onDragEnd() {
                this.dragIndex = null;
            },

            // ===== COPY ROUTE =====

            async copyRoute() {
                if (!this.copySourceDate || !this.selectedDate) return;

                const formData = csrfFormData({ 'target_date': this.selectedDate });

                try {
                    const response = await fetch(`/planner/route/${this.copySourceDate}/copy`, {
                        method: 'POST',
                        body: formData
                    });
                    const data = await response.json();

                    if (data.success) {
                        this.currentStops = data.stops;
                        this.allStops[this.selectedDate] = [...this.currentStops];
                        this.sortAndFilterCustomers();
                        this.showCopyRoute = false;
                        this.showToast(`Copied ${data.copied} stops`);
                    } else {
                        this.showToast(data.error || 'Copy failed', true);
                    }
                } catch (error) {
                    console.error('Error:', error);
                    this.showToast('Copy failed', true);
                }
            },

            // ===== CITY BULK ADD =====

            groupCustomersByCity() {
                const cityMap = {};
                this.customers.forEach(c => {
                    const city = c.city || 'Unknown';
                    if (!cityMap[city]) cityMap[city] = { name: city, count: 0, customers: [] };
                    cityMap[city].count++;
                    cityMap[city].customers.push(c);
                });
                this.cityGroups = Object.values(cityMap).sort((a, b) => b.count - a.count);
            },

            async addCityToRoute(cityName) {
                if (!this.selectedDate) {
                    alert('Please select a date first!');
                    return;
                }
                const cityGroup = this.cityGroups.find(c => c.name === cityName);
                if (!cityGroup) return;

                for (const customer of cityGroup.customers) {
                    if (this.currentStops.some(s => s.customer_id === customer.id)) continue;
                    await this.addToRoute(customer, true);
                }
                this.showCityBulkAdd = false;
                this.showToast(`Added ${cityName} customers`);
            },

            // ===== TEMPLATES (server-side) =====

            async loadTemplates() {
                try {
                    const response = await fetch('/planner/templates');
                    const data = await response.json();
                    this.templates = data.templates;
                } catch (error) {
                    console.error('Error loading templates:', error);
                }
            },

            async openTemplates() {
                await this.loadTemplates();
                this.showTemplates = true;
            },

            async saveTemplate() {
                if (!this.selectedDate || this.currentStops.length === 0) return;

                const name = prompt('Template name:', `Route - ${this.formatDate(this.selectedDate)}`);
                if (!name) return;

                try {
                    const response = await csrfJson('/planner/templates', {
                        name: name,
                        route_date: this.selectedDate
                    });
                    const data = await response.json();

                    if (data.success) {
                        this.showToast('Template saved!');
                        await this.loadTemplates();
                    }
                } catch (error) {
                    console.error('Error:', error);
                }
            },

            async applyTemplate(templateId) {
                if (!this.selectedDate) {
                    alert('Please select a date first!');
                    return;
                }

                try {
                    const response = await csrfJson(`/planner/templates/${templateId}/apply`, {
                        target_date: this.selectedDate
                    });
                    const data = await response.json();

                    if (data.success) {
                        this.currentStops = data.stops;
                        this.allStops[this.selectedDate] = [...this.currentStops];
                        this.sortAndFilterCustomers();
                        this.showTemplates = false;
                        this.showToast(`Applied template (${data.added} stops added)`);
                    }
                } catch (error) {
                    console.error('Error:', error);
                }
            },

            async deleteTemplate(templateId) {
                if (!confirm('Delete this template?')) return;

                try {
                    await fetch(`/planner/templates/${templateId}`, {
                        method: 'DELETE',
                        headers: { 'X-CSRFToken': CSRF_TOKEN }
                    });
                    this.templates = this.templates.filter(t => t.id !== templateId);
                    this.showToast('Template deleted');
                } catch (error) {
                    console.error('Error:', error);
                }
            },

            // ===== CUSTOMER MODAL =====

            openCustomerModal(customer) {
                this.selectedCustomer = customer;
                this.showCustomerModal = true;
                this.loadCustomerDetails(customer.id);
            },

            async loadCustomerDetails(customerId) {
                this.loadingCustomerDetails = true;
                this.customerDetails = null;
                try {
                    const response = await fetch(`/customer/${customerId}/details`);
                    this.customerDetails = await response.json();
                } catch (error) {
                    console.error('Error:', error);
                } finally {
                    this.loadingCustomerDetails = false;
                }
            },

            // ===== CALENDAR =====

            generateCalendar() {
                const firstDay = new Date(this.calendarYear, this.calendarMonth, 1);
                const lastDay = new Date(this.calendarYear, this.calendarMonth + 1, 0);
                const prevLastDay = new Date(this.calendarYear, this.calendarMonth, 0);

                const firstDayWeekday = firstDay.getDay();
                const lastDayDate = lastDay.getDate();
                const prevLastDayDate = prevLastDay.getDate();

                const today = new Date();
                today.setHours(0, 0, 0, 0);

                const days = [];

                for (let i = firstDayWeekday - 1; i >= 0; i--) {
                    const day = prevLastDayDate - i;
                    const date = new Date(this.calendarYear, this.calendarMonth - 1, day);
                    days.push(this._createDay(date, day, false));
                }

                for (let day = 1; day <= lastDayDate; day++) {
                    const date = new Date(this.calendarYear, this.calendarMonth, day);
                    days.push(this._createDay(date, day, true));
                }

                const remaining = 42 - days.length;
                for (let day = 1; day <= remaining; day++) {
                    const date = new Date(this.calendarYear, this.calendarMonth + 1, day);
                    days.push(this._createDay(date, day, false));
                }

                this.calendarDays = days;
            },

            _createDay(date, day, isCurrentMonth) {
                const dateStr = formatDateLocal(date);
                const todayStr = formatDateLocal(new Date());
                const stops = this.allStops[dateStr] || [];

                return {
                    date: dateStr,
                    day: day,
                    isCurrentMonth: isCurrentMonth,
                    isToday: dateStr === todayStr,
                    isSelected: dateStr === this.selectedDate,
                    hasStops: stops.length > 0,
                    stopCount: stops.length
                };
            },

            get currentMonthName() {
                return new Date(this.calendarYear, this.calendarMonth)
                    .toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
            },

            previousMonth() {
                if (this.calendarMonth === 0) { this.calendarMonth = 11; this.calendarYear--; }
                else { this.calendarMonth--; }
                this.generateCalendar();
            },

            nextMonth() {
                if (this.calendarMonth === 11) { this.calendarMonth = 0; this.calendarYear++; }
                else { this.calendarMonth++; }
                this.generateCalendar();
            },

            // ===== HELPERS =====

            formatDate(dateStr) {
                const date = new Date(dateStr + 'T00:00:00');
                return date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
            },

            getDayName(dateStr) {
                const date = new Date(dateStr + 'T00:00:00');
                return date.toLocaleDateString('en-US', { weekday: 'long' });
            },

            get routeTotal() {
                return this.currentStops.reduce((sum, s) => sum + (s.customer_balance || 0), 0);
            },

            showToast(message, isError = false) {
                const toast = document.createElement('div');
                toast.className = `fixed bottom-4 right-4 ${isError ? 'bg-danger' : 'bg-good'} text-white px-4 py-3 rounded-lg shadow-lg z-50 text-sm font-semibold`;
                toast.textContent = message;
                document.body.appendChild(toast);
                setTimeout(() => toast.remove(), 2000);
            }
        };
    }
