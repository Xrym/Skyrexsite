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

    // Check if the current user has premium access (all free for now)
    isSubscribed() {
        return true;
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
            return { success: false, message: `Ошибка связи с сервером (${err.message || 'сеть недоступна'})` };
        }
    },

    // Registration step 1: Request verification code from server (sent via email)
    async sendVerificationCode(email, password) {
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

        try {
            const res = await fetch("/api/auth/send_code", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email, password })
            });
            const data = await res.json();
            if (data.success) {
                return { success: true, message: data.message };
            } else {
                // If SMTP is not yet configured or returned an error, check if fallback code was provided
                if (data.fallback_code) {
                    return { success: true, fallback_code: data.fallback_code, warning: data.error };
                }
                return { success: false, message: data.error || "Не удалось отправить код подтверждения." };
            }
        } catch (err) {
            console.error("sendVerificationCode error:", err);
            return { success: false, message: `Ошибка связи с сервером: ${err.message}` };
        }
    },

    // Registration step 2: Verify code and register on server
    async verifyAndRegister(email, code) {
        email = email.trim().toLowerCase();
        code = code.trim();

        if (!code) {
            return { success: false, message: "Пожалуйста, введите код из письма." };
        }

        try {
            const res = await fetch("/api/auth/register", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email, code })
            });
            const data = await res.json();
            if (data.success && data.token) {
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

        // Form Submit: Register Step 1 (Request Verification via Email)
        this.dom.registerForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            this.dom.registerError.textContent = "";

            const email = this.dom.registerEmail.value;
            const pass = this.dom.registerPass.value;
            const passConfirm = this.dom.registerPassConfirm.value;

            if (pass !== passConfirm) {
                this.dom.registerError.textContent = "Пароли не совпадают.";
                return;
            }

            const submitBtn = this.dom.registerForm.querySelector('button[type="submit"]');
            const originalBtnText = submitBtn ? submitBtn.textContent : "";
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = "Отправка кода на почту...";
            }

            const result = await this.sendVerificationCode(email, pass);

            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = originalBtnText;
            }

            if (result.success) {
                // Switch steps
                this.dom.registerInputStep.style.display = "none";
                this.dom.registerVerifyStep.style.display = "block";

                if (result.fallback_code) {
                    this.dom.demoCodeHelper.innerHTML = `⚠️ <i>${result.warning || 'Почта не настроена'}</i><br>🔑 <b>Код подтверждения:</b> <span style="font-size: 16px; font-weight: 700; color: #fff; text-shadow: 0 0 5px var(--accent-cyan);">${result.fallback_code}</span>`;
                } else {
                    this.dom.demoCodeHelper.innerHTML = `✉️ <b>Код отправлен на:</b> <span style="color: var(--accent-cyan); font-weight: 600;">${email}</span><br>Пожалуйста, проверьте папку «Входящие» (и папку «Спам»).`;
                }

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
        if (this.dom.loginForm) this.dom.loginForm.reset();
        if (this.dom.registerForm) this.dom.registerForm.reset();
        if (this.dom.loginError) this.dom.loginError.textContent = "";
        if (this.dom.registerError) this.dom.registerError.textContent = "";
        if (this.dom.verifyError) this.dom.verifyError.textContent = "";
        if (this.dom.registerVerifyStep) this.dom.registerVerifyStep.style.display = "none";
        if (this.dom.registerInputStep) this.dom.registerInputStep.style.display = "block";
        if (typeof switchAuthTab === "function") switchAuthTab('login');
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
        this.startCountdown();
    },

    closeProfileModal() {
        const modal = (this.dom && this.dom.profileModal) || document.getElementById("profile-modal");
        if (modal) {
            modal.classList.remove("active");
            modal.style.visibility = "hidden";
            modal.style.opacity = "0";
            modal.style.pointerEvents = "none";
        }
        this.stopCountdown();
    },


    updateProfileUI() {
        if (!this.currentUser) return;
        if (this.dom.profileEmailDisplay) this.dom.profileEmailDisplay.textContent = this.currentUser.email;
        if (this.dom.profileRoleDisplay) this.dom.profileRoleDisplay.textContent = this.currentUser.role === "admin" ? "Администратор" : "Пользователь";

        if (this.dom.profileSubBadge) {
            this.dom.profileSubBadge.textContent = "Бесплатный доступ";
            this.dom.profileSubBadge.className = "sub-badge premium";
        }
        if (this.dom.profileSubExpires) {
            this.dom.profileSubExpires.textContent = "Все функции активны";
        }
        if (this.dom.profileSubTimeRemaining) {
            this.dom.profileSubTimeRemaining.style.display = "none";
        }
        if (this.dom.profileSubActionBtn) {
            this.dom.profileSubActionBtn.style.display = "none";
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
            if (subBadge && subStatusDesc) {
                subBadge.textContent = "Полный доступ";
                subBadge.className = "sub-badge premium";
                subStatusDesc.textContent = "Все функции ИИ-консультанта и подбора ПК активны.";
                if (subActionBtn) subActionBtn.style.display = "none";
                if (subResetBtn) subResetBtn.style.display = "none";
            }

            const subChatLink = document.getElementById("sub-chat-link");
            if (subChatLink) {
                subChatLink.style.display = "inline-block";
            }

            localStorage.setItem("skyrex_subscribed", "true");
        } else {
            // Logged out
            this.dom.authStatusDot.className = "auth-status-dot";

            const subBadge = document.getElementById("sub-badge");
            const subStatusDesc = document.getElementById("sub-status-desc");
            const subActionBtn = document.getElementById("sub-action-btn");
            const subResetBtn = document.getElementById("sub-reset-btn");

            if (subBadge && subStatusDesc) {
                subBadge.textContent = "Полный доступ";
                subBadge.className = "sub-badge premium";
                subStatusDesc.textContent = "Все функции ИИ-консультанта и подбора ПК активны.";
                if (subActionBtn) subActionBtn.style.display = "none";
                if (subResetBtn) subResetBtn.style.display = "none";
            }

            const subChatLink = document.getElementById("sub-chat-link");
            if (subChatLink) {
                subChatLink.style.display = "inline-block";
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
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => SkyrexAuth.init());
} else {
    SkyrexAuth.init();
}

