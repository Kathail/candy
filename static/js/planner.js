    const CSRF_TOKEN = window.__PLANNER_CSRF__;

    // Helper: add CSRF to FormData
    function csrfFormData(data = {}) {
        const fd = new FormData();
        fd.append('csrf_token', CSRF_TOKEN);
        for (const [k, v] of Object.entries(data)) fd.append(k, v);
        return fd;
    }

    // Helper: POST with CSRF header (for JSON responses)
    function csrfPost(url) {
        return fetch(url, {
            method: 'POST',
            headers: { 'X-CSRFToken': CSRF_TOKEN }
        });
    }

    // Helper function to format date as YYYY-MM-DD in local timezone
    function formatDateLocal(date) {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    }

    function plannerPage() {
        return {
            query: '',
            customerFilter: 'all',
            customers: window.__PLANNER_CUSTOMERS__,
            filteredCustomers: [],
            allStops: {},
            currentStops: [],

            showCustomerModal: false,
            selectedCustomer: null,
            loadingCustomerDetails: false,
            customerDetails: null,

            showCityBulkAdd: false,
            cityGroups: [],

            showTemplates: false,
            templates: [],

            showRecurring: false,
            selectedTemplateId: null,
            recurringInterval: 7,
            recurringUnit: 'days',
            recurringStartDate: formatDateLocal(new Date()),
            recurringCount: 4,

            selectedDate: null,
            calendarYear: new Date().getFullYear(),
            calendarMonth: new Date().getMonth(),
            calendarDays: [],

            init() {
                this.filteredCustomers = this.customers;
                this.loadAllStops();
                this.generateCalendar();
                this.goToToday();
                this.groupCustomersByCity();
                this.loadTemplates();
            },

            groupCustomersByCity() {
                const cityMap = {};
                this.customers.forEach(c => {
                    const city = c.city || 'Unknown';
                    if (!cityMap[city]) {
                        cityMap[city] = { name: city, count: 0, customers: [] };
                    }
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
                    // Check if already scheduled
                    if (this.currentStops.some(s => s.customer_id === customer.id)) continue;

                    await this.addToRoute(customer, true); // silent mode
                }

                this.showCityBulkAdd = false;
                this.showToast(`✓ Added all ${cityName} customers`);
            },

            loadTemplates() {
                const stored = localStorage.getItem('routeTemplates');
                this.templates = stored ? JSON.parse(stored) : [];
            },

            saveTemplate() {
                if (this.currentStops.length === 0) return;

                const name = prompt('Template name:', `Route - ${this.formatDate(this.selectedDate)}`);
                if (!name) return;

                const template = {
                    id: Date.now(),
                    name: name,
                    stops: this.currentStops.map(s => ({
                        customer_id: s.customer_id,
                        customer_name: s.customer_name,
                        customer_city: s.customer_city
                    }))
                };

                this.templates.push(template);
                localStorage.setItem('routeTemplates', JSON.stringify(this.templates));
                this.showToast('✓ Template saved!');
            },

            async applyTemplate(templateId) {
                if (!this.selectedDate) {
                    alert('Please select a date first!');
                    return;
                }

                const template = this.templates.find(t => t.id === templateId);
                if (!template) return;

                // Clear current route
                if (this.currentStops.length > 0) {
                    await this.clearRoute(true); // silent mode
                }

                // Add all stops from template
                for (const stop of template.stops) {
                    const customer = this.customers.find(c => c.id === stop.customer_id);
                    if (customer) {
                        await this.addToRoute(customer, true); // silent mode
                    }
                }

                this.showTemplates = false;
                this.showToast(`✓ Applied template: ${template.name}`);
            },

            async applyRecurring() {
                const template = this.templates.find(t => t.id === this.selectedTemplateId);
                if (!template) return;

                const startDate = new Date(this.recurringStartDate);
                const intervalDays = this.recurringUnit === 'weeks' ? this.recurringInterval * 7 : this.recurringInterval;

                for (let i = 0; i < this.recurringCount; i++) {
                    const targetDate = new Date(startDate);
                    targetDate.setDate(targetDate.getDate() + (intervalDays * i));
                    const dateStr = targetDate.toISOString().split('T')[0];

                    // Add stops for this date
                    for (const stop of template.stops) {
                        const customer = this.customers.find(c => c.id === stop.customer_id);
                        if (!customer) continue;

                        const formData = csrfFormData({
                            'customer_id': customer.id,
                            'route_date': dateStr
                        });

                        try {
                            await fetch('/planner/add-stop', {
                                method: 'POST',
                                body: formData
                            });
                        } catch (error) {
                            console.error('Error:', error);
                        }
                    }
                }

                // Reload all stops
                await this.loadAllStops();
                this.generateCalendar();

                this.showRecurring = false;
                this.showTemplates = false;
                this.showToast(`✓ Created ${this.recurringCount} recurring routes!`);
            },

            deleteTemplate(templateId) {
                if (!confirm('Delete this template?')) return;

                this.templates = this.templates.filter(t => t.id !== templateId);
                localStorage.setItem('routeTemplates', JSON.stringify(this.templates));
                this.showToast('✓ Template deleted');
            },

            async loadAllStops() {
                try {
                    const response = await fetch('/planner/all-stops');
                    const data = await response.json();
                    this.allStops = data.stops;
                    this.generateCalendar();
                } catch (error) {
                    console.error('Error loading stops:', error);
                }
            },

            filterCustomers() {
                let filtered = this.customers;

                if (this.query) {
                    const q = this.query.toLowerCase();
                    filtered = filtered.filter(c =>
                        c.name.toLowerCase().includes(q) ||
                        c.city.toLowerCase().includes(q)
                    );
                }

                if (this.customerFilter === 'never') {
                    filtered = filtered.filter(c => !c.last_visit);
                } else if (this.customerFilter === 'overdue') {
                    filtered = filtered.filter(c => c.needs_visit);
                }

                if (this.selectedDate && this.currentStops.length > 0) {
                    const scheduledIds = this.currentStops.map(s => s.customer_id);
                    filtered = filtered.filter(c => !scheduledIds.includes(c.id));
                }

                this.filteredCustomers = filtered;
            },

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
                    const data = await response.json();
                    this.customerDetails = data;
                } catch (error) {
                    console.error('Error loading customer details:', error);
                } finally {
                    this.loadingCustomerDetails = false;
                }
            },

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
                    days.push(this.createDayObject(date, day, false));
                }

                for (let day = 1; day <= lastDayDate; day++) {
                    const date = new Date(this.calendarYear, this.calendarMonth, day);
                    days.push(this.createDayObject(date, day, true));
                }

                const remainingDays = 42 - days.length;
                for (let day = 1; day <= remainingDays; day++) {
                    const date = new Date(this.calendarYear, this.calendarMonth + 1, day);
                    days.push(this.createDayObject(date, day, false));
                }

                this.calendarDays = days;
            },

            createDayObject(date, day, isCurrentMonth) {
                const dateStr = formatDateLocal(date);
                const today = new Date();
                today.setHours(0, 0, 0, 0);

                const stops = this.allStops[dateStr] || [];

                return {
                    date: dateStr,
                    day: day,
                    isCurrentMonth: isCurrentMonth,
                    isToday: date.getTime() === today.getTime(),
                    isSelected: dateStr === this.selectedDate,
                    hasStops: stops.length > 0,
                    stopCount: stops.length
                };
            },

            get currentMonthName() {
                const date = new Date(this.calendarYear, this.calendarMonth);
                return date.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
            },

            previousMonth() {
                if (this.calendarMonth === 0) {
                    this.calendarMonth = 11;
                    this.calendarYear--;
                } else {
                    this.calendarMonth--;
                }
                this.generateCalendar();
            },

            nextMonth() {
                if (this.calendarMonth === 11) {
                    this.calendarMonth = 0;
                    this.calendarYear++;
                } else {
                    this.calendarMonth++;
                }
                this.generateCalendar();
            },

            goToToday() {
                const today = new Date();
                this.selectedDate = formatDateLocal(today);
                this.calendarYear = today.getFullYear();
                this.calendarMonth = today.getMonth();
                this.loadStopsForDate();
                this.generateCalendar();
            },

            selectDate(dateStr) {
                this.selectedDate = dateStr;
                this.loadStopsForDate();
                this.generateCalendar();
            },

            formatDate(dateStr) {
                const date = new Date(dateStr + 'T00:00:00');
                return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
            },

            getDayName(dateStr) {
                const date = new Date(dateStr + 'T00:00:00');
                return date.toLocaleDateString('en-US', { weekday: 'long' });
            },

            async loadStopsForDate() {
                if (!this.selectedDate) return;

                this.currentStops = this.allStops[this.selectedDate] || [];
                this.filterCustomers();
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
                            customer_name: customer.name,
                            customer_city: customer.city,
                            sequence: this.currentStops.length + 1
                        });

                        this.allStops[this.selectedDate] = this.currentStops;
                        this.generateCalendar();
                        this.filterCustomers();

                        if (!silent) this.showToast(`✓ Added ${customer.name} to route`);
                    }
                } catch (error) {
                    console.error('Error:', error);
                    if (!silent) alert('Failed to add stop');
                }
            },

            async removeStop(stopId) {
                try {
                    const response = await csrfPost(`/planner/stop/${stopId}/remove`);

                    const data = await response.json();

                    if (data.success) {
                        this.currentStops = this.currentStops.filter(s => s.id !== stopId);
                        this.allStops[this.selectedDate] = this.currentStops;
                        this.generateCalendar();
                        this.filterCustomers();
                        this.showToast('✓ Stop removed');
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
                        this.allStops[this.selectedDate] = this.currentStops;
                        this.showToast('✓ Route optimized!');
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
                        this.generateCalendar();
                        this.filterCustomers();
                        if (!silent) this.showToast('✓ Route cleared');
                    }
                } catch (error) {
                    console.error('Error:', error);
                }
            },

            showToast(message) {
                const toast = document.createElement('div');
                toast.className = 'fixed bottom-4 right-4 bg-good text-white px-4 py-3 rounded-lg shadow-lg z-50';
                toast.textContent = message;
                document.body.appendChild(toast);
                setTimeout(() => toast.remove(), 2000);
            }
        };
    }
