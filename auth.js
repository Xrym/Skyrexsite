// Skyrex Computers - Authentication and User Database Manager
// Real Server-Side Authentication via SQLite users.db & Session Tokens

const SkyrexAuth = {
    // LocalStorage Keys
    TOKEN_KEY: "skyrex_auth_token",
    SESSION_KEY: "skyrex_current_user",

    // In-memory State
    token: null,
    currentUser: null,
    tempVerification: {}, // Simulates verification code registry: { email: { code, password, expires } }
    countdownInterval: null,

    // Init function
    init() {
        this.setupDOM();
        this.bindEvents();
        this.checkSession();

        // Start subscription checker
        setInterval(() => this.validateActiveSubscription(), 60000); // Check every minute
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
        // Dispatch custom event for decoupling (e.g. for chat_bot.js)
        document.dispatchEvent(new CustomEvent("skyrex-auth-changed", { detail: this.currentUser }));
    },

    validateActiveSubscription() {
        if (!this.currentUser) return;

        if (this.currentUser.subscribed && this.currentUser.subscriptionExpires) {
            const expires = new Date(this.currentUser.subscriptionExpires);
            const now = new Date();
            if (expires <= now) {
                this.currentUser.subscribed = false;
                this.currentUser.subscriptionExpires = null;
                this.saveSession();
                this.updateUI();
            }
        }
    },

    // Check if the current user has premium access
    isSubscribed() {
        this.validateActiveSubscription();
        return Boolean(this.currentUser && this.currentUser.subscribed);
    },

    getToken() {
        return this.token || localStorage.getItem(this.TOKEN_KEY) || "";
    },

    // Login logic via server
    async login(email, password) {
        email = email.trim().toLowerCase();
        try {
            const res = await fetch("/api/auth/login", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email, password })
            });
            const data = await res.json();
            if (data.success && data.token) {
                this.token = data.token;
                this.currentUser = data.user;
                localStorage.setItem(this.TOKEN_KEY, data.token);
                this.saveSession();
                this.updateUI();
                localStorage.setItem("skyrex_subscribed", data.user.subscribed ? "true" : "false");
                return { success: true, user: data.user };
            }
            return { success: false, message: data.error || "Неверный email или пароль." };
        } catch (err) {
            console.error("Login fetch error:", err);
            return { success: false, message: "Ошибка связи с сервером авторизации." };
        }
    },

    // Registration step 1: Send verification code
    sendVerificationCode(email, password) {
        email = email.trim().toLowerCase();

        // Validate email format
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(email)) {
            return { success: false, message: "Введите корректный email адрес." };
        }

        // Validate password length
        if (password.length < 6) {
            return { success: false, message: "Пароль должен быть не менее 6 символов." };
        }

        // Generate 4-digit code
        const code = Math.floor(1000 + Math.random() * 9000).toString();

        // Save verification entry (expires in 5 minutes)
        this.tempVerification[email] = {
            code,
            password,
            expires: Date.now() + 5 * 60000
        };

        console.log(`[Skyrex Verification] Code for ${email} is: ${code}`);
        return { success: true, code };
    },

    // Registration step 2: Verify code and register on server
    async verifyAndRegister(email, code) {
        email = email.trim().toLowerCase();
        const record = this.tempVerification[email];

        if (!record) {
            return { success: false, message: "Сессия регистрации не найдена. Попробуйте снова." };
        }

        if (Date.now() > record.expires) {
            delete this.tempVerification[email];
            return { success: false, message: "Время действия кода истекло. Запросите новый." };
        }

        if (record.code !== code) {
            return { success: false, message: "Неверный код подтверждения." };
        }

        try {
            const res = await fetch("/api/auth/register", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email, password: record.password })
            });
            const data = await res.json();
            if (data.success && data.token) {
                delete this.tempVerification[email];
                this.token = data.token;
                this.currentUser = data.user;
                localStorage.setItem(this.TOKEN_KEY, data.token);
                this.saveSession();
                this.updateUI();
                localStorage.setItem("skyrex_subscribed", "false");
                return { success: true, user: data.user };
            }
            return { success: false, message: data.error || "Ошибка регистрации." };
        } catch (err) {
            console.error("Register fetch error:", err);
            return { success: false, message: "Ошибка связи с сервером авторизации." };
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
        localStorage.setItem("skyrex_subscribed", "false");
        this.updateUI();
    },

    // Activate/Extend subscription via server
    async activateSubscription(days = 30) {
        if (!this.token) return false;
        try {
            const res = await fetch("/api/auth/subscribe", {
                method: "POST",
                headers: { "Authorization": `Bearer ${this.token}` }
            });
            const data = await res.json();
            if (data.success && data.user) {
                this.currentUser = data.user;
                this.saveSession();
                this.updateUI();
                localStorage.setItem("skyrex_subscribed", "true");
                return true;
            }
        } catch (e) {
            console.error("Subscription activation error:", e);
        }
        return false;
    },

    // Reset subscription (for testing)
    resetSubscription() {
        if (this.currentUser) {
            this.currentUser.subscribed = false;
            this.currentUser.subscriptionExpires = null;
            this.saveSession();
            this.updateUI();
            localStorage.setItem("skyrex_subscribed", "false");
        }
    },


        this.updateUI();
        return true;
    },

    // Helper formatting subscription time remaining
    getSubscriptionTimeRemaining() {
        if (!this.currentUser || !this.currentUser.subscriptionExpires) return null;

        const expires = new Date(this.currentUser.subscriptionExpires);
        const diff = expires - new Date();

        if (diff <= 0) return null;

        const days = Math.floor(diff / (24 * 60 * 60 * 1000));
        const hours = Math.floor((diff % (24 * 60 * 60 * 1000)) / (60 * 60 * 1000));
        const minutes = Math.floor((diff % (60 * 60 * 1000)) / (60 * 1000));

        return { days, hours, minutes };
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

            loginEmail: document.getElementById("login-email"),
            loginPass: document.getElementById("login-password"),
            loginError: document.getElementById("login-error"),

            registerEmail: document.getElementById("register-email"),
            registerPass: document.getElementById("register-password"),
            registerPassConfirm: document.getElementById("register-password-confirm"),
            registerError: document.getElementById("register-error"),

            registerInputStep: document.getElementById("register-input-step"),
            registerVerifyStep: document.getElementById("register-verify-step"),
            verifyCodeInput: document.getElementById("verify-code"),
            verifyError: document.getElementById("verify-error"),
            btnVerifyCode: document.getElementById("btn-verify-code"),
            btnBackToRegister: document.getElementById("btn-back-to-register"),
            demoCodeHelper: document.getElementById("auth-demo-code-helper"),

            // Profile Modal
            profileModal: document.getElementById("profile-modal"),
            profileCloseBtn: document.getElementById("profile-modal-close-btn"),
            profileEmailDisplay: document.getElementById("profile-email-display"),
            profileRoleDisplay: document.getElementById("profile-role-display"),
            profileSubBadge: document.getElementById("profile-sub-badge"),
            profileSubExpires: document.getElementById("profile-sub-expires"),
            profileSubTimeRemaining: document.getElementById("profile-sub-time-remaining"),
            profileSubActionBtn: document.getElementById("profile-sub-action-btn"),
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
        this.dom.authCloseBtn.addEventListener("click", () => this.closeAuthModal());
        this.dom.profileCloseBtn.addEventListener("click", () => this.closeProfileModal());

        // Close on overlay click
        this.dom.authModal.addEventListener("click", (e) => {
            if (e.target === this.dom.authModal) this.closeAuthModal();
        });
        this.dom.profileModal.addEventListener("click", (e) => {
            if (e.target === this.dom.profileModal) this.closeProfileModal();
        });

        // Form Submit: Login
        this.dom.loginForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            this.dom.loginError.textContent = "";

            const email = this.dom.loginEmail.value;
            const pass = this.dom.loginPass.value;

            const result = await this.login(email, pass);
            if (result.success) {
                this.closeAuthModal();
            } else {
                this.dom.loginError.textContent = result.message;
            }
        });

        // Form Submit: Register Step 1 (Request Verification)
        this.dom.registerForm.addEventListener("submit", (e) => {
            e.preventDefault();
            this.dom.registerError.textContent = "";

            const email = this.dom.registerEmail.value;
            const pass = this.dom.registerPass.value;
            const passConfirm = this.dom.registerPassConfirm.value;

            if (pass !== passConfirm) {
                this.dom.registerError.textContent = "Пароли не совпадают.";
                return;
            }

            const result = this.sendVerificationCode(email, pass);
            if (result.success) {
                // Switch steps
                this.dom.registerInputStep.style.display = "none";
                this.dom.registerVerifyStep.style.display = "block";

                // Show demo helper code to help users test registration immediately
                this.dom.demoCodeHelper.innerHTML = `🔑 <b>Демо-код подтверждения:</b> <span style="font-size: 16px; font-weight: 700; color: #fff; text-shadow: 0 0 5px var(--accent-cyan);">${result.code}</span><br>(код также выведен в консоль)`;
                this.dom.verifyCodeInput.value = "";
                this.dom.verifyCodeInput.focus();
            } else {
                this.dom.registerError.textContent = result.message;
            }
        });

        // Verify Verification Code and Register
        this.dom.btnVerifyCode.addEventListener("click", async () => {
            this.dom.verifyError.textContent = "";
            const email = this.dom.registerEmail.value;
            const code = this.dom.verifyCodeInput.value.trim();

            const result = await this.verifyAndRegister(email, code);
            if (result.success) {
                this.closeAuthModal();
                // Reset register step
                this.dom.registerVerifyStep.style.display = "none";
                this.dom.registerInputStep.style.display = "block";
            } else {
                this.dom.verifyError.textContent = result.message;
            }
        });


        // Back to register fields
        this.dom.btnBackToRegister.addEventListener("click", () => {
            this.dom.registerVerifyStep.style.display = "none";
            this.dom.registerInputStep.style.display = "block";
            this.dom.verifyError.textContent = "";
        });

        // Logout
        this.dom.profileLogoutBtn.addEventListener("click", () => {
            this.logout();
            this.closeProfileModal();
        });

        // Subscription Activation from Profile
        this.dom.profileSubActionBtn.addEventListener("click", () => {
            this.closeProfileModal();
            // Open old payment modal
            const paymentModal = document.getElementById("payment-modal");
            if (paymentModal) {
                // Trigger event to open modal (reuse payment simulation logic)
                const subActionBtn = document.getElementById("sub-action-btn");
                if (subActionBtn) {
                    subActionBtn.click();
                }
            }
        });
    },

    openAuthModal() {
        this.dom.authModal.classList.add("active");
        this.dom.loginForm.reset();
        this.dom.registerForm.reset();
        this.dom.loginError.textContent = "";
        this.dom.registerError.textContent = "";
        this.dom.verifyError.textContent = "";
        this.dom.registerVerifyStep.style.display = "none";
        this.dom.registerInputStep.style.display = "block";
        switchAuthTab('login');
    },

    closeAuthModal() {
        this.dom.authModal.classList.remove("active");
    },

    openProfileModal() {
        if (!this.currentUser) return;
        this.dom.profileModal.classList.add("active");
        this.updateProfileUI();

        // Start countdown timer
        this.startCountdown();
    },

    closeProfileModal() {
        this.dom.profileModal.classList.remove("active");
        this.stopCountdown();
    },

    updateProfileUI() {
        if (!this.currentUser) return;
        this.dom.profileEmailDisplay.textContent = this.currentUser.email;
        this.dom.profileRoleDisplay.textContent = this.currentUser.role === "admin" ? "Администратор" : "Пользователь";

        const subscribed = this.isSubscribed();
        if (subscribed) {
            this.dom.profileSubBadge.textContent = "Premium";
            this.dom.profileSubBadge.className = "sub-badge premium";

            const expiresDate = new Date(this.currentUser.subscriptionExpires);
            const formattedDate = expiresDate.toLocaleString('ru-RU', {
                day: '2-digit', month: '2-digit', year: 'numeric',
                hour: '2-digit', minute: '2-digit'
            });
            this.dom.profileSubExpires.textContent = `Активна до: ${formattedDate}`;
            this.dom.profileSubTimeRemaining.style.display = "block";
            this.dom.profileSubActionBtn.textContent = "Продлить подписку";
        } else {
            this.dom.profileSubBadge.textContent = "Базовый";
            this.dom.profileSubBadge.className = "sub-badge";
            this.dom.profileSubExpires.textContent = "Подписка не активна";
            this.dom.profileSubTimeRemaining.style.display = "none";
            this.dom.profileSubActionBtn.textContent = "Активировать Premium (390 ₽)";
        }
    },

    startCountdown() {
        this.stopCountdown();

        const update = () => {
            const time = this.getSubscriptionTimeRemaining();
            if (time) {
                let text = "Осталось: ";
                if (time.days > 0) text += `${time.days} дн. `;
                text += `${time.hours} ч. ${time.minutes} мин.`;
                this.dom.profileSubTimeRemaining.textContent = text;
            } else {
                this.dom.profileSubTimeRemaining.textContent = "";
                this.updateProfileUI();
                this.updateUI();
            }
        };

        update();
        this.countdownInterval = setInterval(update, 30000); // Update every 30 seconds
    },

    stopCountdown() {
        if (this.countdownInterval) {
            clearInterval(this.countdownInterval);
            this.countdownInterval = null;
        }
    },

    // Overall layout UI Synchronization
    updateUI() {
        if (this.currentUser) {
            // Update auth dot indicator
            this.dom.authStatusDot.className = "auth-status-dot " +
                (this.isSubscribed() ? "active-premium" : "active-base");

            // If they are logged in, make sure sidebar bot box matches their subscription
            const subBadge = document.getElementById("sub-badge");
            const subStatusDesc = document.getElementById("sub-status-desc");
            const subActionBtn = document.getElementById("sub-action-btn");
            const subResetBtn = document.getElementById("sub-reset-btn");

            const isPremium = this.isSubscribed();
            if (subBadge && subStatusDesc && subActionBtn && subResetBtn) {
                if (isPremium) {
                    subBadge.textContent = "Premium";
                    subBadge.className = "sub-badge premium";

                    const expiresDate = new Date(this.currentUser.subscriptionExpires);
                    const formattedDate = expiresDate.toLocaleDateString('ru-RU');
                    subStatusDesc.textContent = `Премиальные функции разблокированы. Активны до: ${formattedDate}.`;
                    subActionBtn.style.display = "none";
                    subResetBtn.style.display = "block";
                } else {
                    subBadge.textContent = "Базовый";
                    subBadge.className = "sub-badge";
                    subStatusDesc.textContent = "Премиальные функции (оценка, подбор и б/у сборки) заблокированы.";
                    subActionBtn.style.display = "block";
                    subResetBtn.style.display = "none";
                }
            }

            const subChatLink = document.getElementById("sub-chat-link");
            if (subChatLink) {
                subChatLink.style.display = isPremium ? "flex" : "none";
            }

            // Sync global compatibility subscription variable for simple scripts
            localStorage.setItem("skyrex_subscribed", isPremium ? "true" : "false");
        } else {
            // Logged out
            this.dom.authStatusDot.className = "auth-status-dot";

            // Sidebar premium details reset
            const subBadge = document.getElementById("sub-badge");
            const subStatusDesc = document.getElementById("sub-status-desc");
            const subActionBtn = document.getElementById("sub-action-btn");
            const subResetBtn = document.getElementById("sub-reset-btn");

            if (subBadge && subStatusDesc && subActionBtn && subResetBtn) {
                subBadge.textContent = "Войти";
                subBadge.className = "sub-badge";
                subStatusDesc.textContent = "Пожалуйста, авторизуйтесь для использования бота и отслеживания подписки.";
                subActionBtn.textContent = "Войти в аккаунт";
                subActionBtn.style.display = "block";
                subResetBtn.style.display = "none";
            }

            const subChatLink = document.getElementById("sub-chat-link");
            if (subChatLink) {
                subChatLink.style.display = "none";
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

        // Reset steps
        document.getElementById("register-input-step").style.display = "block";
        document.getElementById("register-verify-step").style.display = "none";
    }
}

// Auto init on load
document.addEventListener("DOMContentLoaded", () => {
    SkyrexAuth.init();
});
