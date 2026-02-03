class MetroAPI {
    constructor() {
        this.baseUrl = 'http://localhost:5000/api';
    }

    // Generic API Call Function
    async call(endpoint, method = 'GET', body = null) {
        const options = {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include' // Important for cookies
        };

        if (body) {
            options.body = JSON.stringify(body);
        }

        try {
            const response = await fetch(`${this.baseUrl}${endpoint}`, options);
            
            // 1. Parse JSON first (so we can read server error messages)
            let data = {};
            try {
                data = await response.json();
            } catch (err) {
                console.warn('Response was not JSON', err);
            }

            // 2. Handle 401 (Unauthorized)
            if (response.status === 401) {
                // EXCEPTION: If we are trying to Log In, return the failure to the form
                // so it can show "Invalid Password" instead of redirecting.
                if (endpoint === '/login') {
                    return data; 
                }

                // For all other checks (like /me), handle redirection
                const path = window.location.pathname;
                
                // If we are INSIDE the app (Dashboard/Profile), kick user out
                if (path.includes('dashboard') || path.includes('profile') || path.includes('ticket')) {
                    window.location.href = 'login.html';
                    throw new Error('Session expired. Redirecting...');
                }
                
                // If we are on Login/Register page, just return failure silently
                return { success: false, error: 'Not logged in' };
            }

            // 3. Handle General Errors
            if (!data.success && !data.message && !data.token) {
                // If the server says success: false, throw error
                throw new Error(data.error || 'API Error');
            }

            return data;
        } catch (error) {
            console.error("API Call Failed:", error);
            throw error;
        }
    }

    // Strict Auth Check (For Dashboard)
    async requireAuth() {
        const result = await this.call('/me');
        if (result && result.success) {
            return result.user;
        } else {
            window.location.href = 'login.html';
            return null;
        }
    }

    // Passive Auth Check (For Login Page)
    async checkAuth() {
        // We don't catch here anymore because call() handles the silence for us
        const result = await this.call('/me');
        if (result && result.success) {
            // User IS logged in -> Go to Dashboard
            const path = window.location.pathname;
            if (path.includes('login.html') || path.includes('register.html') || path === '/' || path.includes('index.html')) {
                window.location.href = 'dashboard.html';
            }
            return result.user;
        }
        return null;
    }
    
    // --- Helper Functions ---

    formatDate(dateStr) {
        if (!dateStr) return '';
        const date = new Date(dateStr);
        return date.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
    }

    formatDateTime(dateStr) {
        if (!dateStr) return '';
        const date = new Date(dateStr);
        return date.toLocaleString('en-US', { 
            year: 'numeric', month: 'short', day: 'numeric', 
            hour: '2-digit', minute: '2-digit' 
        });
    }

    showAlert(message, type = 'info') {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} fixed-top m-3 shadow`;
        alertDiv.style.zIndex = '9999';
        alertDiv.innerHTML = `<i class="fas fa-info-circle me-2"></i>${message}`;
        document.body.appendChild(alertDiv);
        
        setTimeout(() => {
            alertDiv.style.opacity = '0';
            setTimeout(() => alertDiv.remove(), 500);
        }, 3000);
    }
    
 logout() {
        this.call('/logout', 'POST').then(() => {
            // [NEW] Remove the flag when logging out
            localStorage.removeItem('metro_logged_in');
            window.location.href = 'login.html';
        });
    }
}

// 1. Initialize Global API
const API = new MetroAPI();

// 2. BACKWARD COMPATIBILITY (Vital for your Login Page)
// This connects the old "apiCall" function to our new class
window.apiCall = (url, method, body) => API.call(url, method, body);
window.checkAuth = () => API.checkAuth();
window.showAlert = (msg, type) => API.showAlert(msg, type);

// 3. Auto-run Auth Check (Updated to skip Login/Register pages)
document.addEventListener('DOMContentLoaded', () => {
    const path = window.location.pathname;
    
    // Only check if we are NOT on the auth pages
    // This prevents the 401 error from appearing in the console
    if (!path.includes('login.html') && !path.includes('register.html')) {
        API.checkAuth();
    }
});