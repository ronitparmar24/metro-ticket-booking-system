// API Configuration
const API_BASE_URL = 'http://localhost:5000/api';

// Utility Functions
function showAlert(message, type = 'success') {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    const container = document.querySelector('.container') || document.body;
    container.insertBefore(alertDiv, container.firstChild);
    
    setTimeout(() => {
        alertDiv.remove();
    }, 5000);
}

function formatDate(dateString) {
    const options = { year: 'numeric', month: 'short', day: 'numeric' };
    return new Date(dateString).toLocaleDateString('en-US', options);
}

function formatDateTime(dateString) {
    const options = { 
        year: 'numeric', 
        month: 'short', 
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    };
    return new Date(dateString).toLocaleDateString('en-US', options);
}

// API Call Wrapper
async function apiCall(endpoint, method = 'GET', data = null) {
    const options = {
        method: method,
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'include', // Important for session cookies
    };
    
    if (data) {
        options.body = JSON.stringify(data);
    }
    
    try {
        const response = await fetch(`${API_BASE_URL}${endpoint}`, options);
        const result = await response.json();
        
        if (!response.ok) {
            throw new Error(result.error || 'Something went wrong');
        }
        
        return result;
    } catch (error) {
        console.error('API Error:', error);
        throw error;
    }
}

// Check if user is logged in
async function checkAuth() {
    try {
        const result = await apiCall('/me');
        if (result.success) {
            return result.user;
        }
    } catch (error) {
        return null;
    }
}

// Redirect if not logged in
async function requireAuth() {
    const user = await checkAuth();
    if (!user) {
        window.location.href = 'login.html';
    }
    return user;
}

// Logout function
async function logout() {
    try {
        await apiCall('/logout', 'POST');
        window.location.href = 'login.html';
    } catch (error) {
        showAlert(error.message, 'danger');
    }
}

// Export for use in other pages
window.API = {
    call: apiCall,
    checkAuth: checkAuth,
    requireAuth: requireAuth,
    logout: logout,
    showAlert: showAlert,
    formatDate: formatDate,
    formatDateTime: formatDateTime
};
