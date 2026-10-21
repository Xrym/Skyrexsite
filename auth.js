// Skyrex Computers - Authentication and User Session Manager
// Real Server-Side Authentication via SQLite users.db & Session Tokens

const SkyrexAuth = {
    // LocalStorage Keys
    TOKEN_KEY: "skyrex_auth_token",
    SESSION_KEY: "skyrex_current_user",

    // In-memory State
    token: null,
    currentUser: null,

    // Init function
    init() {
        this.setupDOM();
        this.bindEvents();
        this.checkSession();
    },

    async checkSession() {
        const storedToken = localStorage.getItem(this.TOKEN_KEY);
        if (storedToken) {
            this.token = storedToken;
            try {
                const res = await fetch("/api/auth/me", {
                    headers: {
                        "Authorization": `Bearer ${this.token}`
                    }
                });
                if (res.ok) {
                    const data = await res.json();
                    if (data.authenticated && data.user) {
                        this.currentUser = data.user;
                        this.saveSession();
                        this.updateUI();
                        return;
                    }
                }
            } catch (e) {
                console.warn("Could not check session with server:", e);
            }
        }

        // If token missing or invalid
        const storedSession = localStorage.getItem(this.SESSION_KEY);
        if (storedSession && !this.token) {
            localStorage.removeItem(this.SESSION_KEY);
        }
        this.currentUser = null;
        this.updateUI();
    },

    saveSession() {
        if (this.currentUser) {
            localStorage.setItem(this.SESSION_KEY, JSON.stringify(this.currentUser));
        } else {
            localStorage.removeItem(this.SESSION_KEY);
        }
        // Dispatch custom event for decoupling
        document.dispatchEvent(new CustomEvent("skyrex-auth-changed", { detail: this.currentUser }));
    },

    getToken() {
        return this.token || localStorage.getItem(this.TOKEN_KEY) || "";
    },

    // Login logic via server (login & password)
    async login(username, password) {
        username = (username || "").trim();
        try {
            const res = await fetch("/api/auth/login", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username, password })
            });
            const data = await res.json();
            if (data.success && data.token) {
                this.token = data.token;
                this.currentUser = data.user;
                localStorage.setItem(this.TOKEN_KEY, this.token);
                this.saveSession();
                this.updateUI();
                return { success: true };
            }
            return { success: false, message: data.error || "Неверный логин или пароль." };
        } catch (err) {
            console.error("Login fetch error:", err);
            return { success: false, message: `Ошибка связи с сервером: ${err.message}` };
        }
    },

    // Direct registration logic via server (login & password)
    async register(username, password) {
        username = (username || "").trim();
        try {
            const res = await fetch("/api/auth/register", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username, password })
            });
            const data = await res.json();
            if (data.success && data.token) {
                this.token = data.token;
                this.currentUser = data.user;
                localStorage.setItem(this.TOKEN_KEY, this.token);
                this.saveSession();
                this.updateUI();
                return { success: true };
            }
            return { success: false, message: data.error || "Ошибка регистрации." };
        } catch (err) {
            console.error("Register fetch error:", err);
            return { success: false, message: `Ошибка связи с сервером: ${err.message}` };
        }
    },

    // Logout logic
    async logout() {
        if (this.token) {
            try {
                await fetch("/api/auth/logout", {
                    method: "POST",
                    headers: { "Authorization": `Bearer ${this.token}` }
                });
            } catch (e) {}
        }

        this.token = null;
        this.currentUser = null;
        localStorage.removeItem(this.TOKEN_KEY);
        localStorage.removeItem(this.SESSION_KEY);
        this.updateUI();
    },

    // UI elements references setup
    setupDOM() {
        this.dom = {
            authToggleBtn: document.getElementById("auth-toggle-btn"),
            authStatusDot: document.getElementById("auth-status-dot"),

            // Auth Modal
            authModal: document.getElementById("auth-modal"),
            authCloseBtn: document.getElementById("auth-modal-close-btn"),
            loginForm: document.getElementById("login-form"),
            registerForm: document.getElementById("register-form"),

            loginUsername: document.getElementById("login-username"),
            loginPass: document.getElementById("login-password"),
            loginError: document.getElementById("login-error"),

            registerUsername: document.getElementById("register-username"),
            registerPass: document.getElementById("register-password"),
            registerPassConfirm: document.getElementById("register-password-confirm"),
            registerError: document.getElementById("register-error"),

            // Profile Modal
            profileModal: document.getElementById("profile-modal"),
            profileCloseBtn: document.getElementById("profile-modal-close-btn"),
            profileUsernameDisplay: document.getElementById("profile-username-display"),
            profileRoleDisplay: document.getElementById("profile-role-display"),
            profileLogoutBtn: document.getElementById("profile-logout-btn"),
        };
    },

    bindEvents() {
        if (!this.dom.authToggleBtn) return;

        // Toggle Auth/Profile modal on header btn click
        this.dom.authToggleBtn.addEventListener("click", () => {
            if (this.currentUser) {
                this.openProfileModal();
            } else {
                this.openAuthModal();
            }
        });

        // Close buttons
        if (this.dom.authCloseBtn) {
            this.dom.authCloseBtn.addEventListener("click", () => this.closeAuthModal());
        }
        if (this.dom.profileCloseBtn) {
            this.dom.profileCloseBtn.addEventListener("click", () => this.closeProfileModal());
        }

        // Close on overlay click
        if (this.dom.authModal) {
            this.dom.authModal.addEventListener("click", (e) => {
                if (e.target === this.dom.authModal) this.closeAuthModal();
            });
        }
        if (this.dom.profileModal) {
            this.dom.profileModal.addEventListener("click", (e) => {
                if (e.target === this.dom.profileModal) this.closeProfileModal();
            });
        }

        // Close on Escape key
        document.addEventListener("keydown", (e) => {
            if (e.key === "Escape") {
                this.closeAuthModal();
                this.closeProfileModal();
            }
        });

        // Form Submit: Login
        if (this.dom.loginForm) {
            this.dom.loginForm.addEventListener("submit", async (e) => {
                e.preventDefault();
                if (this.dom.loginError) this.dom.loginError.textContent = "";

                const username = this.dom.loginUsername ? this.dom.loginUsername.value.trim() : "";
                const pass = this.dom.loginPass ? this.dom.loginPass.value : "";

                if (!username) {
                    if (this.dom.loginError) this.dom.loginError.textContent = "Введите логин.";
                    return;
                }
                if (!pass) {
                    if (this.dom.loginError) this.dom.loginError.textContent = "Введите пароль.";
                    return;
                }

                const submitBtn = this.dom.loginForm.querySelector("button[type='submit']");
                if (submitBtn) {
                    submitBtn.disabled = true;
                    submitBtn.textContent = "Вход...";
                }

                const result = await this.login(username, pass);

                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = "Войти";
                }

                if (result.success) {
                    this.closeAuthModal();
                    if (this.dom.loginUsername) this.dom.loginUsername.value = "";
                    if (this.dom.loginPass) this.dom.loginPass.value = "";
                } else if (this.dom.loginError) {
                    this.dom.loginError.textContent = result.message;
                }
            });
        }

        // Form Submit: Direct Registration
        if (this.dom.registerForm) {
            this.dom.registerForm.addEventListener("submit", async (e) => {
                e.preventDefault();
                if (this.dom.registerError) this.dom.registerError.textContent = "";

                const username = this.dom.registerUsername ? this.dom.registerUsername.value.trim() : "";
                const pass = this.dom.registerPass ? this.dom.registerPass.value : "";
                const passConfirm = this.dom.registerPassConfirm ? this.dom.registerPassConfirm.value : "";

                if (!username || username.length < 3) {
                    if (this.dom.registerError) this.dom.registerError.textContent = "Логин должен содержать минимум 3 символа.";
                    return;
                }

                if (!pass || pass.length < 6) {
                    if (this.dom.registerError) this.dom.registerError.textContent = "Пароль должен содержать минимум 6 символов.";
                    return;
                }

                if (pass !== passConfirm) {
                    if (this.dom.registerError) this.dom.registerError.textContent = "Пароли не совпадают.";
                    return;
                }

                const submitBtn = this.dom.registerForm.querySelector("button[type='submit']");
                if (submitBtn) {
                    submitBtn.disabled = true;
                    submitBtn.textContent = "Регистрация...";
                }

                const result = await this.register(username, pass);

                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = "Зарегистрироваться";
                }

                if (result.success) {
                    this.closeAuthModal();
                    if (this.dom.registerUsername) this.dom.registerUsername.value = "";
                    if (this.dom.registerPass) this.dom.registerPass.value = "";
                    if (this.dom.registerPassConfirm) this.dom.registerPassConfirm.value = "";
                } else if (this.dom.registerError) {
                    this.dom.registerError.textContent = result.message;
                }
            });
        }

        // Profile Modal Logout
        if (this.dom.profileLogoutBtn) {
            this.dom.profileLogoutBtn.addEventListener("click", () => {
                this.logout();
                this.closeProfileModal();
            });
        }
    },

    openAuthModal() {
        if (!this.dom || !this.dom.authModal) {
            this.setupDOM();
        }
        const modal = this.dom.authModal || document.getElementById("auth-modal");
        if (modal) {
            modal.classList.add("active");
            modal.style.visibility = "visible";
            modal.style.opacity = "1";
            modal.style.pointerEvents = "auto";
        }
        switchAuthTab('login');
    },

    closeAuthModal() {
        const modal = (this.dom && this.dom.authModal) || document.getElementById("auth-modal");
        if (modal) {
            modal.classList.remove("active");
            modal.style.visibility = "hidden";
            modal.style.opacity = "0";
            modal.style.pointerEvents = "none";
        }
    },

    openProfileModal() {
        if (!this.currentUser) return;
        if (!this.dom || !this.dom.profileModal) {
            this.setupDOM();
        }
        const modal = this.dom.profileModal || document.getElementById("profile-modal");
        if (modal) {
            modal.classList.add("active");
            modal.style.visibility = "visible";
            modal.style.opacity = "1";
            modal.style.pointerEvents = "auto";
        }
        this.updateProfileUI();
    },

    closeProfileModal() {
        const modal = (this.dom && this.dom.profileModal) || document.getElementById("profile-modal");
        if (modal) {
            modal.classList.remove("active");
            modal.style.visibility = "hidden";
            modal.style.opacity = "0";
            modal.style.pointerEvents = "none";
        }
    },

    updateProfileUI() {
        if (!this.currentUser) return;
        const displayName = this.currentUser.username || this.currentUser.login || "Пользователь";
        if (this.dom.profileUsernameDisplay) {
            this.dom.profileUsernameDisplay.textContent = displayName;
        }
        if (this.dom.profileRoleDisplay) {
            this.dom.profileRoleDisplay.textContent = this.currentUser.role === "admin" ? "Администратор" : "Пользователь";
        }
    },

    // Overall layout UI Synchronization
    updateUI() {
        if (!this.dom || !this.dom.authStatusDot) {
            this.setupDOM();
        }
        if (this.dom.authStatusDot) {
            if (this.currentUser) {
                this.dom.authStatusDot.className = "auth-status-dot active-base";
            } else {
                this.dom.authStatusDot.className = "auth-status-dot";
            }
        }
    }
};

// Global helper for Auth tab switching
function switchAuthTab(tab) {
    const tabLogin = document.getElementById("tab-login");
    const tabRegister = document.getElementById("tab-register");
    const loginForm = document.getElementById("login-form");
    const registerForm = document.getElementById("register-form");

    if (!tabLogin || !tabRegister || !loginForm || !registerForm) return;

    if (tab === 'login') {
        tabLogin.classList.add("active");
        tabRegister.classList.remove("active");
        loginForm.classList.add("active");
        registerForm.classList.remove("active");
    } else {
        tabLogin.classList.remove("active");
        tabRegister.classList.add("active");
        loginForm.classList.remove("active");
        registerForm.classList.add("active");
    }
}

// Auto init on load
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => SkyrexAuth.init());
} else {
    SkyrexAuth.init();
}
