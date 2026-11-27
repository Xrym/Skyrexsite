// Skyrex Computers - Authentication & User Session Manager
// Passwordless One-Time Password (OTP) Authentication via Email & SQLite users.db

const SkyrexAuth = {
    // LocalStorage Keys
    TOKEN_KEY: "skyrex_auth_token",
    SESSION_KEY: "skyrex_current_user",

    // In-memory State
    token: null,
    currentUser: null,
    pendingEmail: "",
    pendingResetEmail: "",
    pendingPassword: "",
    pendingNickname: "",
    countdownTimer: null,
    countdownSeconds: 60,

    // Init function
    init() {
        const storedToken = localStorage.getItem(this.TOKEN_KEY);
        const storedSession = localStorage.getItem(this.SESSION_KEY);
        if (storedToken) {
            this.token = storedToken;
            if (storedSession) {
                try {
                    this.currentUser = JSON.parse(storedSession);
                } catch (_) {}
            }
        }
        this.setupDOM();
        this.bindEvents();
        this.updateUI();
        this.checkSession();

        // Handle return from YooKassa payment
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.get("payment") === "success") {
            window.history.replaceState({}, document.title, window.location.pathname);
            setTimeout(() => {
                this.checkSession();
                const toastFn = (typeof showToast === "function") ? showToast : (window.showChatToast || null);
                if (toastFn) {
                    toastFn("🎉 Оплата прошла успешно! Премиум подписка активирована на 30 дней.", "success", 8000);
                } else {
                    alert("🎉 Оплата прошла успешно! Премиум подписка активирована на 30 дней.");
                }
            }, 800);
        }
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

    isAuthenticated() {
        return !!(this.getToken() && this.currentUser);
    },

    // Password Login for all users & admin
    async loginWithPassword(username, password) {
        username = (username || "").trim();
        password = password || "";
        if (!username || !password) {
            return { success: false, message: "Введите логин или email и пароль." };
        }
        try {
            const res = await fetch("/api/auth/login", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username, password })
            });
            const data = await res.json();
            if (res.ok && data.success && data.token) {
                this.token = data.token;
                this.currentUser = data.user;
                localStorage.setItem(this.TOKEN_KEY, this.token);
                this.saveSession();
                this.updateUI();
                return { success: true };
            }
            return { success: false, message: data.error || "Неверный логин или пароль." };
        } catch (err) {
            console.error("loginWithPassword error:", err);
            return { success: false, message: `Ошибка связи с сервером: ${err.message}` };
        }
    },

    // Registration Step 1: Send confirmation OTP code to email
    async registerRequest(email, password, nickname) {
        email = (email || "").trim().toLowerCase();
        password = password || "";
        nickname = (nickname || "").trim();

        if (!email) return { success: false, message: "Введите адрес электронной почты." };
        if (!password || password.length < 6) return { success: false, message: "Пароль должен содержать минимум 6 символов." };

        try {
            const res = await fetch("/api/auth/register-request", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email, password, nickname })
            });
            const data = await res.json();
            if (res.ok && data.success) {
                this.pendingEmail = email;
                this.pendingPassword = password;
                this.pendingNickname = nickname;
                return { success: true, message: data.message };
            }
            return { success: false, message: data.error || "Не удалось отправить код подтверждения." };
        } catch (err) {
            console.error("registerRequest error:", err);
            return { success: false, message: `Ошибка связи с сервером: ${err.message}` };
        }
    },

    // Registration Step 2: Confirm OTP code & login
    async registerConfirm(code) {
        code = (code || "").trim();
        if (!this.pendingEmail) return { success: false, message: "Email не указан. Вернитесь назад." };
        if (!code || code.length !== 6) return { success: false, message: "Введите 6-значный код из письма." };

        try {
            const res = await fetch("/api/auth/register-confirm", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email: this.pendingEmail, code })
            });
            const data = await res.json();
            if (res.ok && data.success && data.token) {
                this.token = data.token;
                this.currentUser = data.user;
                localStorage.setItem(this.TOKEN_KEY, this.token);
                this.saveSession();
                this.updateUI();
                return { success: true };
            }
            return { success: false, message: data.error || "Неверный код подтверждения." };
        } catch (err) {
            console.error("registerConfirm error:", err);
            return { success: false, message: `Ошибка связи с сервером: ${err.message}` };
        }
    },

    // Password Reset Step 1: Request code
    async resetPasswordRequest(email) {
        email = (email || "").trim().toLowerCase();
        if (!email) return { success: false, message: "Введите адрес электронной почты." };

        try {
            const res = await fetch("/api/auth/reset-request", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email })
            });
            const data = await res.json();
            if (res.ok && data.success) {
                this.pendingResetEmail = email;
                return { success: true, message: data.message };
            }
            return { success: false, message: data.error || "Не удалось запросить сброс пароля." };
        } catch (err) {
            console.error("resetPasswordRequest error:", err);
            return { success: false, message: `Ошибка связи с сервером: ${err.message}` };
        }
    },

    // Password Reset Step 2: Confirm code & set new password
    async resetPasswordConfirm(code, password) {
        code = (code || "").trim();
        password = password || "";
        if (!this.pendingResetEmail) return { success: false, message: "Email не указан." };
        if (!code || code.length !== 6) return { success: false, message: "Введите 6-значный код из письма." };
        if (!password || password.length < 6) return { success: false, message: "Новый пароль должен содержать минимум 6 символов." };

        try {
            const res = await fetch("/api/auth/reset-confirm", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email: this.pendingResetEmail, code, password })
            });
            const data = await res.json();
            if (res.ok && data.success && data.token) {
                this.token = data.token;
                this.currentUser = data.user;
                localStorage.setItem(this.TOKEN_KEY, this.token);
                this.saveSession();
                this.updateUI();
                return { success: true, message: data.message };
            }
            return { success: false, message: data.error || "Не удалось обновить пароль." };
        } catch (err) {
            console.error("resetPasswordConfirm error:", err);
            return { success: false, message: `Ошибка связи с сервером: ${err.message}` };
        }
    },

    // Legacy OTP support
    async sendCode(email) {
        return this.registerRequest(email, "default123", "");
    },
    async verifyCode(code) {
        return this.registerConfirm(code);
    },

    // Update user display nickname
    async updateNickname(nickname) {
        nickname = (nickname || "").trim();
        if (!this.token) {
            return { success: false, message: "Необходима авторизация." };
        }
        try {
            const res = await fetch("/api/auth/nickname", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${this.token}`
                },
                body: JSON.stringify({ nickname })
            });
            const data = await res.json();
            if (res.ok && data.success) {
                if (data.user) {
                    this.currentUser = data.user;
                } else if (this.currentUser) {
                    this.currentUser.nickname = data.nickname;
                }
                this.saveSession();
                this.updateProfileUI();
                return { success: true };
            }
            return { success: false, message: data.error || "Не удалось обновить никнейм." };
        } catch (err) {
            console.error("updateNickname error:", err);
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

            // Auth Modal & Steps
            authModal: document.getElementById("auth-modal"),
            authCloseBtn: document.getElementById("auth-modal-close-btn"),

            // Step: Login
            stepLogin: document.getElementById("auth-step-login"),
            loginForm: document.getElementById("auth-login-form"),
            loginUsernameInput: document.getElementById("auth-login-username"),
            loginPasswordInput: document.getElementById("auth-login-password"),
            loginError: document.getElementById("auth-login-error"),
            loginSubmitBtn: document.getElementById("auth-login-submit-btn"),

            // Step: Register
            stepRegister: document.getElementById("auth-step-register"),
            regForm: document.getElementById("auth-reg-form"),
            regEmailInput: document.getElementById("auth-reg-email"),
            regNicknameInput: document.getElementById("auth-reg-nickname"),
            regPasswordInput: document.getElementById("auth-reg-password"),
            regError: document.getElementById("auth-reg-error"),
            regSubmitBtn: document.getElementById("auth-reg-submit-btn"),

            // Step: Confirm OTP
            stepConfirm: document.getElementById("auth-step-confirm"),
            confirmForm: document.getElementById("auth-confirm-form"),
            confirmCodeInput: document.getElementById("auth-confirm-code-input"),
            confirmError: document.getElementById("auth-confirm-error"),
            confirmSubmitBtn: document.getElementById("auth-confirm-submit-btn"),
            confirmEmailDisplay: document.getElementById("auth-confirm-email-display"),
            confirmResendBtn: document.getElementById("auth-confirm-resend-btn"),
            confirmCountdownSpan: document.getElementById("auth-confirm-countdown"),

            // Step: Reset Request
            stepResetRequest: document.getElementById("auth-step-reset-request"),
            resetReqForm: document.getElementById("auth-reset-req-form"),
            resetReqEmailInput: document.getElementById("auth-reset-req-email"),
            resetReqError: document.getElementById("auth-reset-req-error"),
            resetReqSubmitBtn: document.getElementById("auth-reset-req-submit-btn"),

            // Step: Reset Confirm
            stepResetConfirm: document.getElementById("auth-step-reset-confirm"),
            resetConfirmForm: document.getElementById("auth-reset-confirm-form"),
            resetCodeInput: document.getElementById("auth-reset-code-input"),
            resetNewPasswordInput: document.getElementById("auth-reset-new-password"),
            resetConfirmError: document.getElementById("auth-reset-confirm-error"),
            resetConfirmSubmitBtn: document.getElementById("auth-reset-confirm-submit-btn"),
            resetEmailDisplay: document.getElementById("auth-reset-email-display"),

            // Profile Modal
            profileModal: document.getElementById("profile-modal"),
            profileCloseBtn: document.getElementById("profile-modal-close-btn"),
            profileAvatarDisplay: document.getElementById("profile-avatar-display"),
            profileNicknameDisplay: document.getElementById("profile-nickname-display"),
            profileEmailDisplay: document.getElementById("profile-email-display"),
            profileRoleDisplay: document.getElementById("profile-role-display"),
            profileEditNickBtn: document.getElementById("profile-edit-nick-btn"),
            profileNickForm: document.getElementById("profile-nick-form"),
            profileNickInput: document.getElementById("profile-nick-input"),
            profileNickError: document.getElementById("profile-nick-error"),
            profileSaveNickBtn: document.getElementById("profile-save-nick-btn"),
            profileCancelNickBtn: document.getElementById("profile-cancel-nick-btn"),
            profileSubStatus: document.getElementById("profile-sub-status"),
            profileSubExpiry: document.getElementById("profile-sub-expiry"),
            profilePayBtn: document.getElementById("profile-pay-btn"),
            profileLogoutBtn: document.getElementById("profile-logout-btn"),

            // Paywall & Offer Modals
            paywallModal: document.getElementById("paywall-modal"),
            paywallCloseBtn: document.getElementById("paywall-modal-close-btn"),
            paywallCheckoutBtn: document.getElementById("paywall-checkout-btn"),
            offerModal: document.getElementById("offer-modal"),
            offerCloseBtn: document.getElementById("offer-modal-close-btn"),

            // Support Helpdesk Modal
            supportModal: document.getElementById("support-modal"),
            supportCloseBtn: document.getElementById("support-modal-close-btn"),
            supportSendForm: document.getElementById("support-send-form"),
            supportInput: document.getElementById("support-input"),
            supportAdminSendForm: document.getElementById("support-admin-send-form"),
            supportAdminInput: document.getElementById("support-admin-input"),

            // On-site Web Admin Panel Modal
            adminPanelModal: document.getElementById("admin-panel-modal"),
            adminPanelCloseBtn: document.getElementById("admin-panel-close-btn"),
            navAdminLink: document.getElementById("nav-admin-link"),
            profileAdminBtn: document.getElementById("profile-admin-btn"),
            adminAddRuleForm: document.getElementById("admin-add-rule-form"),
            adminAddCompForm: document.getElementById("admin-add-comp-form"),
            adminManualSubForm: document.getElementById("admin-manual-sub-form"),
            adminPanelReplyForm: document.getElementById("admin-panel-reply-form"),
            adminPanelReplyInput: document.getElementById("admin-panel-reply-input"),
            adminPanelReplyBtn: document.getElementById("admin-panel-reply-btn"),
            adminPanelDeleteDialogBtn: document.getElementById("admin-panel-delete-dialog-btn"),
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
        if (this.dom.paywallCloseBtn) {
            this.dom.paywallCloseBtn.addEventListener("click", () => this.closePaywallModal());
        }
        if (this.dom.offerCloseBtn) {
            this.dom.offerCloseBtn.addEventListener("click", () => this.closeOfferModal());
        }
        if (this.dom.supportCloseBtn) {
            this.dom.supportCloseBtn.addEventListener("click", () => this.closeSupportModal());
        }
        if (this.dom.adminPanelCloseBtn) {
            this.dom.adminPanelCloseBtn.addEventListener("click", () => this.closeAdminPanel());
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
        if (this.dom.paywallModal) {
            this.dom.paywallModal.addEventListener("click", (e) => {
                if (e.target === this.dom.paywallModal) this.closePaywallModal();
            });
        }
        if (this.dom.offerModal) {
            this.dom.offerModal.addEventListener("click", (e) => {
                if (e.target === this.dom.offerModal) this.closeOfferModal();
            });
        }
        if (this.dom.supportModal) {
            this.dom.supportModal.addEventListener("click", (e) => {
                if (e.target === this.dom.supportModal) this.closeSupportModal();
            });
        }
        if (this.dom.adminPanelModal) {
            this.dom.adminPanelModal.addEventListener("click", (e) => {
                if (e.target === this.dom.adminPanelModal) this.closeAdminPanel();
            });
        }

        // Pay buttons
        if (this.dom.paywallCheckoutBtn) {
            this.dom.paywallCheckoutBtn.addEventListener("click", () => this.startPayment());
        }
        if (this.dom.profilePayBtn) {
            this.dom.profilePayBtn.addEventListener("click", () => this.startPayment());
        }

        // Close on Escape key
        document.addEventListener("keydown", (e) => {
            if (e.key === "Escape") {
                this.closeAuthModal();
                this.closeProfileModal();
                this.closePaywallModal();
                this.closeOfferModal();
                this.closeSupportModal();
                this.closeAdminPanel();
            }
        });

        // 1. Password Login Form (for all users & admin)
        if (this.dom.loginForm) {
            this.dom.loginForm.addEventListener("submit", async (e) => {
                e.preventDefault();
                if (this.dom.loginError) this.dom.loginError.textContent = "";

                const username = this.dom.loginUsernameInput ? this.dom.loginUsernameInput.value.trim() : "";
                const password = this.dom.loginPasswordInput ? this.dom.loginPasswordInput.value : "";

                if (!username || !password) {
                    if (this.dom.loginError) this.dom.loginError.textContent = "Введите логин или email и пароль.";
                    return;
                }

                if (this.dom.loginSubmitBtn) {
                    this.dom.loginSubmitBtn.disabled = true;
                    this.dom.loginSubmitBtn.innerHTML = `<span>Вход...</span>`;
                }

                const res = await this.loginWithPassword(username, password);

                if (this.dom.loginSubmitBtn) {
                    this.dom.loginSubmitBtn.disabled = false;
                    this.dom.loginSubmitBtn.innerHTML = `<span>Войти</span>`;
                }

                if (res.success) {
                    this.closeAuthModal();
                    if (this.dom.loginPasswordInput) this.dom.loginPasswordInput.value = "";
                    const toastFn = (typeof showToast === "function") ? showToast : (window.showChatToast || null);
                    const name = (this.currentUser && (this.currentUser.nickname || this.currentUser.username)) || "";
                    if (toastFn) toastFn(`Добро пожаловать, ${name}!`, "success");
                } else if (this.dom.loginError) {
                    this.dom.loginError.textContent = res.message;
                }
            });
        }

        // Support Client Send Form
        if (this.dom.supportSendForm) {
            this.dom.supportSendForm.addEventListener("submit", (e) => {
                e.preventDefault();
                const text = this.dom.supportInput ? this.dom.supportInput.value : "";
                this.sendClientSupportMessage(text);
            });
        }

        // Support Admin Send Form (Support Modal)
        if (this.dom.supportAdminSendForm) {
            this.dom.supportAdminSendForm.addEventListener("submit", (e) => {
                e.preventDefault();
                const text = this.dom.supportAdminInput ? this.dom.supportAdminInput.value : "";
                this.sendAdminSupportReply(text);
            });
        }

        // Support Admin Reply Form (Admin Panel Modal)
        if (this.dom.adminPanelReplyForm) {
            this.dom.adminPanelReplyForm.addEventListener("submit", (e) => {
                e.preventDefault();
                const text = this.dom.adminPanelReplyInput ? this.dom.adminPanelReplyInput.value : "";
                this.sendAdminSupportReply(text);
            });
        }

        // Admin Panel: Add AI Rule Form
        if (this.dom.adminAddRuleForm) {
            this.dom.adminAddRuleForm.addEventListener("submit", (e) => {
                e.preventDefault();
                const titleEl = document.getElementById("admin-rule-title");
                const textEl = document.getElementById("admin-rule-text");
                const title = titleEl ? titleEl.value.trim() : "";
                const text = textEl ? textEl.value.trim() : "";
                if (title && text) {
                    this.addAdminRule(title, text);
                }
            });
        }

        // Admin Panel: Add Expert Component Form
        if (this.dom.adminAddCompForm) {
            this.dom.adminAddCompForm.addEventListener("submit", (e) => {
                e.preventDefault();
                const name = (document.getElementById("admin-comp-name")?.value || "").trim();
                const category = document.getElementById("admin-comp-cat")?.value || "cpu";
                const price = parseFloat(document.getElementById("admin-comp-price")?.value || "0");
                const shop = document.getElementById("admin-comp-shop")?.value || "Авито";
                const url = (document.getElementById("admin-comp-url")?.value || "").trim();
                const comment = (document.getElementById("admin-comp-comment")?.value || "").trim();
                if (name && price && url) {
                    this.addAdminComponent({ name, category, price, shop, url, comment });
                }
            });
        }

        // Admin Panel: Manual Subscription Form
        if (this.dom.adminManualSubForm) {
            this.dom.adminManualSubForm.addEventListener("submit", (e) => {
                e.preventDefault();
                const userId = parseInt(document.getElementById("admin-sub-userid")?.value || "0", 10);
                const days = parseInt(document.getElementById("admin-sub-days")?.value || "30", 10);
                if (userId && days) {
                    this.activateAdminUserSub(userId, days);
                }
            });
        }

        // 2. Registration Form
        if (this.dom.regForm) {
            this.dom.regForm.addEventListener("submit", async (e) => {
                e.preventDefault();
                if (this.dom.regError) this.dom.regError.textContent = "";

                const email = this.dom.regEmailInput ? this.dom.regEmailInput.value.trim() : "";
                const nickname = this.dom.regNicknameInput ? this.dom.regNicknameInput.value.trim() : "";
                const password = this.dom.regPasswordInput ? this.dom.regPasswordInput.value : "";

                if (!email || !password) {
                    if (this.dom.regError) this.dom.regError.textContent = "Заполните все обязательные поля.";
                    return;
                }
                if (password.length < 6) {
                    if (this.dom.regError) this.dom.regError.textContent = "Пароль должен быть не менее 6 символов.";
                    return;
                }

                if (this.dom.regSubmitBtn) {
                    this.dom.regSubmitBtn.disabled = true;
                    this.dom.regSubmitBtn.innerHTML = `<span>Отправка кода...</span>`;
                }

                const res = await this.registerRequest(email, password, nickname);

                if (this.dom.regSubmitBtn) {
                    this.dom.regSubmitBtn.disabled = false;
                    this.dom.regSubmitBtn.innerHTML = `<span>Получить код подтверждения</span>`;
                }

                if (res.success) {
                    this.goToStep("confirm");
                    this.startCountdown(60);
                } else if (this.dom.regError) {
                    this.dom.regError.textContent = res.message;
                }
            });
        }

        // 3. Confirm Registration OTP Code
        if (this.dom.confirmCodeInput) {
            this.dom.confirmCodeInput.addEventListener("input", (e) => {
                e.target.value = e.target.value.replace(/\D/g, "").slice(0, 6);
                if (this.dom.confirmError) this.dom.confirmError.textContent = "";
                if (e.target.value.length === 6) {
                    this.handleConfirmSubmit();
                }
            });
        }
        if (this.dom.confirmForm) {
            this.dom.confirmForm.addEventListener("submit", (e) => {
                e.preventDefault();
                this.handleConfirmSubmit();
            });
        }
        if (this.dom.confirmResendBtn) {
            this.dom.confirmResendBtn.addEventListener("click", async () => {
                if (this.dom.confirmResendBtn.disabled || !this.pendingEmail) return;
                this.dom.confirmResendBtn.disabled = true;
                this.dom.confirmResendBtn.textContent = "Отправка...";
                if (this.dom.confirmError) this.dom.confirmError.textContent = "";

                const res = await this.registerRequest(this.pendingEmail, this.pendingPassword, this.pendingNickname);
                if (res.success) {
                    this.startCountdown(60);
                } else {
                    if (this.dom.confirmError) this.dom.confirmError.textContent = res.message;
                    this.dom.confirmResendBtn.disabled = false;
                    this.dom.confirmResendBtn.textContent = "Отправить повторно";
                }
            });
        }

        // 4. Password Reset Request Form
        if (this.dom.resetReqForm) {
            this.dom.resetReqForm.addEventListener("submit", async (e) => {
                e.preventDefault();
                if (this.dom.resetReqError) this.dom.resetReqError.textContent = "";

                const email = this.dom.resetReqEmailInput ? this.dom.resetReqEmailInput.value.trim() : "";
                if (!email) {
                    if (this.dom.resetReqError) this.dom.resetReqError.textContent = "Введите email.";
                    return;
                }

                if (this.dom.resetReqSubmitBtn) {
                    this.dom.resetReqSubmitBtn.disabled = true;
                    this.dom.resetReqSubmitBtn.innerHTML = `<span>Отправка кода...</span>`;
                }

                const res = await this.resetPasswordRequest(email);

                if (this.dom.resetReqSubmitBtn) {
                    this.dom.resetReqSubmitBtn.disabled = false;
                    this.dom.resetReqSubmitBtn.innerHTML = `<span>Получить код сброса</span>`;
                }

                if (res.success) {
                    this.goToStep("reset-confirm");
                } else if (this.dom.resetReqError) {
                    this.dom.resetReqError.textContent = res.message;
                }
            });
        }

        // 5. Password Reset Confirm Form
        if (this.dom.resetConfirmForm) {
            this.dom.resetConfirmForm.addEventListener("submit", async (e) => {
                e.preventDefault();
                if (this.dom.resetConfirmError) this.dom.resetConfirmError.textContent = "";

                const code = this.dom.resetCodeInput ? this.dom.resetCodeInput.value.trim() : "";
                const pwd = this.dom.resetNewPasswordInput ? this.dom.resetNewPasswordInput.value : "";

                if (!code || code.length !== 6) {
                    if (this.dom.resetConfirmError) this.dom.resetConfirmError.textContent = "Введите 6-значный код из письма.";
                    return;
                }
                if (!pwd || pwd.length < 6) {
                    if (this.dom.resetConfirmError) this.dom.resetConfirmError.textContent = "Пароль должен быть не менее 6 символов.";
                    return;
                }

                if (this.dom.resetConfirmSubmitBtn) {
                    this.dom.resetConfirmSubmitBtn.disabled = true;
                    this.dom.resetConfirmSubmitBtn.innerHTML = `<span>Сохранение...</span>`;
                }

                const res = await this.resetPasswordConfirm(code, pwd);

                if (this.dom.resetConfirmSubmitBtn) {
                    this.dom.resetConfirmSubmitBtn.disabled = false;
                    this.dom.resetConfirmSubmitBtn.innerHTML = `<span>Сохранить пароль и войти</span>`;
                }

                if (res.success) {
                    this.closeAuthModal();
                    const toastFn = (typeof showToast === "function") ? showToast : (window.showChatToast || null);
                    if (toastFn) toastFn("Пароль успешно обновлен! Вход выполнен.", "success");
                } else if (this.dom.resetConfirmError) {
                    this.dom.resetConfirmError.textContent = res.message;
                }
            });
        }

        // Profile Modal: Edit Nickname toggle
        if (this.dom.profileEditNickBtn) {
            this.dom.profileEditNickBtn.addEventListener("click", () => {
                if (!this.dom.profileNickForm) return;
                const isHidden = this.dom.profileNickForm.style.display === "none";
                if (isHidden) {
                    this.dom.profileNickForm.style.display = "block";
                    if (this.dom.profileNickInput) {
                        const currentNick = (this.currentUser && this.currentUser.nickname) || "";
                        this.dom.profileNickInput.value = currentNick;
                        setTimeout(() => this.dom.profileNickInput.focus(), 50);
                    }
                    if (this.dom.profileNickError) this.dom.profileNickError.textContent = "";
                } else {
                    this.dom.profileNickForm.style.display = "none";
                }
            });
        }

        // Profile Modal: Cancel Nickname edit
        if (this.dom.profileCancelNickBtn) {
            this.dom.profileCancelNickBtn.addEventListener("click", () => {
                if (this.dom.profileNickForm) this.dom.profileNickForm.style.display = "none";
                if (this.dom.profileNickError) this.dom.profileNickError.textContent = "";
            });
        }

        // Profile Modal: Save Nickname
        if (this.dom.profileNickForm) {
            this.dom.profileNickForm.addEventListener("submit", async (e) => {
                e.preventDefault();
                if (this.dom.profileNickError) this.dom.profileNickError.textContent = "";

                const newNick = this.dom.profileNickInput ? this.dom.profileNickInput.value.trim() : "";
                if (!newNick) {
                    if (this.dom.profileNickError) this.dom.profileNickError.textContent = "Введите никнейм.";
                    return;
                }

                if (this.dom.profileSaveNickBtn) {
                    this.dom.profileSaveNickBtn.disabled = true;
                    this.dom.profileSaveNickBtn.innerHTML = `<span>Сохранение...</span>`;
                }

                const res = await this.updateNickname(newNick);

                if (this.dom.profileSaveNickBtn) {
                    this.dom.profileSaveNickBtn.disabled = false;
                    this.dom.profileSaveNickBtn.innerHTML = `<span>Сохранить</span>`;
                }

                if (res.success) {
                    if (this.dom.profileNickForm) this.dom.profileNickForm.style.display = "none";
                    if (typeof showToast === "function") {
                        showToast("Никнейм успешно изменен!", "success");
                    }
                } else if (this.dom.profileNickError) {
                    this.dom.profileNickError.textContent = res.message;
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

    async handleConfirmSubmit() {
        if (!this.dom.confirmCodeInput) return;
        const code = this.dom.confirmCodeInput.value.trim();
        if (code.length !== 6) {
            if (this.dom.confirmError) this.dom.confirmError.textContent = "Введите полный 6-значный код.";
            return;
        }

        if (this.dom.confirmSubmitBtn) {
            this.dom.confirmSubmitBtn.disabled = true;
            this.dom.confirmSubmitBtn.innerHTML = `<span>Проверка...</span>`;
        }

        const res = await this.registerConfirm(code);

        if (this.dom.confirmSubmitBtn) {
            this.dom.confirmSubmitBtn.disabled = false;
            this.dom.confirmSubmitBtn.innerHTML = `<span>Подтвердить и войти</span>`;
        }

        if (res.success) {
            this.closeAuthModal();
            if (this.dom.confirmCodeInput) this.dom.confirmCodeInput.value = "";
            this.pendingEmail = "";
            this.pendingPassword = "";
            this.pendingNickname = "";
            this.stopCountdown();
            const toastFn = (typeof showToast === "function") ? showToast : (window.showChatToast || null);
            const name = (this.currentUser && (this.currentUser.nickname || this.currentUser.username)) || "";
            if (toastFn) toastFn(`🎉 Регистрация завершена! Добро пожаловать, ${name}!`, "success");
        } else if (this.dom.confirmError) {
            this.dom.confirmError.textContent = res.message;
        }
    },

    goToStep(step) {
        if (!this.dom || !this.dom.stepLogin) {
            this.setupDOM();
        }

        if (this.dom.loginError) this.dom.loginError.textContent = "";
        if (this.dom.regError) this.dom.regError.textContent = "";
        if (this.dom.confirmError) this.dom.confirmError.textContent = "";
        if (this.dom.resetReqError) this.dom.resetReqError.textContent = "";
        if (this.dom.resetConfirmError) this.dom.resetConfirmError.textContent = "";

        const allSteps = [
            this.dom.stepLogin,
            this.dom.stepRegister,
            this.dom.stepConfirm,
            this.dom.stepResetRequest,
            this.dom.stepResetConfirm
        ];

        allSteps.forEach(s => {
            if (s) {
                s.classList.remove("active");
                s.style.display = "none";
            }
        });

        if (step === "register") {
            if (this.dom.stepRegister) {
                this.dom.stepRegister.classList.add("active");
                this.dom.stepRegister.style.display = "block";
            }
            if (this.dom.regEmailInput) setTimeout(() => this.dom.regEmailInput.focus(), 100);
            this.stopCountdown();
        } else if (step === "confirm") {
            if (this.dom.stepConfirm) {
                this.dom.stepConfirm.classList.add("active");
                this.dom.stepConfirm.style.display = "block";
            }
            if (this.dom.confirmEmailDisplay) this.dom.confirmEmailDisplay.textContent = this.pendingEmail;
            if (this.dom.confirmCodeInput) {
                this.dom.confirmCodeInput.value = "";
                setTimeout(() => this.dom.confirmCodeInput.focus(), 100);
            }
        } else if (step === "reset-request") {
            if (this.dom.stepResetRequest) {
                this.dom.stepResetRequest.classList.add("active");
                this.dom.stepResetRequest.style.display = "block";
            }
            if (this.dom.resetReqEmailInput) setTimeout(() => this.dom.resetReqEmailInput.focus(), 100);
            this.stopCountdown();
        } else if (step === "reset-confirm") {
            if (this.dom.stepResetConfirm) {
                this.dom.stepResetConfirm.classList.add("active");
                this.dom.stepResetConfirm.style.display = "block";
            }
            if (this.dom.resetEmailDisplay) this.dom.resetEmailDisplay.textContent = this.pendingResetEmail;
            if (this.dom.resetCodeInput) {
                this.dom.resetCodeInput.value = "";
                setTimeout(() => this.dom.resetCodeInput.focus(), 100);
            }
            this.stopCountdown();
        } else {
            // "login" (default for all users and admin)
            if (this.dom.stepLogin) {
                this.dom.stepLogin.classList.add("active");
                this.dom.stepLogin.style.display = "block";
            }
            if (this.dom.loginUsernameInput) setTimeout(() => this.dom.loginUsernameInput.focus(), 100);
            this.stopCountdown();
        }
    },

    startCountdown(seconds) {
        this.stopCountdown();
        this.countdownSeconds = seconds || 60;
        const btn = document.getElementById("auth-confirm-resend-btn");
        if (!btn) return;

        btn.disabled = true;
        btn.innerHTML = `Отправить повторно через <span id="auth-confirm-countdown">${this.countdownSeconds}</span>с`;

        this.countdownTimer = setInterval(() => {
            this.countdownSeconds--;
            const span = document.getElementById("auth-confirm-countdown");
            if (span) span.textContent = this.countdownSeconds;

            if (this.countdownSeconds <= 0) {
                this.stopCountdown();
                if (btn) {
                    btn.disabled = false;
                    btn.textContent = "Отправить код повторно";
                }
            }
        }, 1000);
    },

    stopCountdown() {
        if (this.countdownTimer) {
            clearInterval(this.countdownTimer);
            this.countdownTimer = null;
        }
    },

    openAuthModal(initialStep = "login") {
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
        this.goToStep(initialStep || "login");
    },

    closeAuthModal() {
        const modal = (this.dom && this.dom.authModal) || document.getElementById("auth-modal");
        if (modal) {
            modal.classList.remove("active");
            modal.style.visibility = "hidden";
            modal.style.opacity = "0";
            modal.style.pointerEvents = "none";
        }
        this.stopCountdown();
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
        const nick = this.currentUser.nickname || (this.currentUser.username ? this.currentUser.username.split("@")[0] : "Пользователь");
        const email = this.currentUser.username || "";

        if (this.dom.profileNicknameDisplay) {
            this.dom.profileNicknameDisplay.textContent = nick;
        }
        if (this.dom.profileEmailDisplay) {
            this.dom.profileEmailDisplay.textContent = email;
        }
        if (this.dom.profileAvatarDisplay) {
            const firstLetter = nick.charAt(0).toUpperCase();
            this.dom.profileAvatarDisplay.textContent = firstLetter || "👤";
        }
        if (this.dom.profileRoleDisplay) {
            this.dom.profileRoleDisplay.textContent = this.currentUser.role === "admin" ? "Администратор" : "Пользователь";
        }

        // Hide inline edit form on fresh modal open
        if (this.dom.profileNickForm) {
            this.dom.profileNickForm.style.display = "none";
        }

        // Subscription status display
        if (this.dom.profileSubStatus) {
            if (this.currentUser.subscribed) {
                this.dom.profileSubStatus.textContent = "Премиум активен ⭐";
                this.dom.profileSubStatus.style.color = "#00ffcc";
            } else {
                this.dom.profileSubStatus.textContent = "Базовый доступ";
                this.dom.profileSubStatus.style.color = "var(--text-secondary)";
            }
        }
        if (this.dom.profileSubExpiry) {
            if (this.currentUser.subscribed && this.currentUser.subscriptionExpires) {
                try {
                    const dt = new Date(this.currentUser.subscriptionExpires);
                    this.dom.profileSubExpiry.textContent = `Действует до: ${dt.toLocaleDateString("ru-RU")}`;
                    this.dom.profileSubExpiry.style.display = "block";
                } catch (_) {
                    this.dom.profileSubExpiry.style.display = "none";
                }
            } else {
                this.dom.profileSubExpiry.style.display = "none";
            }
        }
        if (this.dom.profilePayBtn) {
            if (this.currentUser.subscribed) {
                this.dom.profilePayBtn.innerHTML = `<span>⚡ Продлить подписку (+30 дней за 490 ₽)</span>`;
            } else {
                this.dom.profilePayBtn.innerHTML = `<span>⚡ Оформить подписку (490 ₽ / 30 дней)</span>`;
            }
        }
    },

    openPaywallModal() {
        if (!this.dom || !this.dom.paywallModal) {
            this.setupDOM();
        }
        const modal = this.dom.paywallModal || document.getElementById("paywall-modal");
        if (modal) {
            modal.classList.add("active");
            modal.style.visibility = "visible";
            modal.style.opacity = "1";
            modal.style.pointerEvents = "auto";
        }
    },

    closePaywallModal() {
        const modal = (this.dom && this.dom.paywallModal) || document.getElementById("paywall-modal");
        if (modal) {
            modal.classList.remove("active");
            modal.style.visibility = "hidden";
            modal.style.opacity = "0";
            modal.style.pointerEvents = "none";
        }
    },

    openOfferModal() {
        if (!this.dom || !this.dom.offerModal) {
            this.setupDOM();
        }
        const modal = this.dom.offerModal || document.getElementById("offer-modal");
        if (modal) {
            modal.classList.add("active");
            modal.style.visibility = "visible";
            modal.style.opacity = "1";
            modal.style.pointerEvents = "auto";
        }
    },

    closeOfferModal() {
        const modal = (this.dom && this.dom.offerModal) || document.getElementById("offer-modal");
        if (modal) {
            modal.classList.remove("active");
            modal.style.visibility = "hidden";
            modal.style.opacity = "0";
            modal.style.pointerEvents = "none";
        }
    },

    async startPayment() {
        if (!this.currentUser || !this.getToken()) {
            this.closePaywallModal();
            this.openAuthModal();
            const toastFn = (typeof showToast === "function") ? showToast : (window.showChatToast || null);
            if (toastFn) {
                toastFn("Сначала войдите по почте, чтобы привязать подписку к вашему аккаунту.", "info", 5000);
            }
            return;
        }

        const payBtn = this.dom.paywallCheckoutBtn || document.getElementById("paywall-checkout-btn");
        const origText = payBtn ? payBtn.innerHTML : "";
        if (payBtn) {
            payBtn.disabled = true;
            payBtn.innerHTML = `<span>⏳ Создаем платеж ЮKassa...</span>`;
        }

        try {
            const res = await fetch("/api/payments/create", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${this.getToken()}`
                }
            });
            const data = await res.json();
            if (res.ok && data.success && data.payment_url) {
                // Redirect directly to YooKassa payment checkout
                window.location.href = data.payment_url;
            } else {
                const errText = data.error || "Не удалось создать счет на оплату.";
                const toastFn = (typeof showToast === "function") ? showToast : (window.showChatToast || null);
                if (toastFn) {
                    toastFn(`⚠️ ${errText}`, "error", 6000);
                } else {
                    alert(errText);
                }
                if (payBtn) {
                    payBtn.disabled = false;
                    payBtn.innerHTML = origText;
                }
            }
        } catch (err) {
            console.error("Payment initiation error:", err);
            const toastFn = (typeof showToast === "function") ? showToast : (window.showChatToast || null);
            if (toastFn) {
                toastFn("⚠️ Ошибка связи с платежным сервисом.", "error", 5000);
            }
            if (payBtn) {
                payBtn.disabled = false;
                payBtn.innerHTML = origText;
            }
        }
    },

    async loginWithPassword(username, password) {
        username = (username || "").trim();
        password = password || "";
        if (!username || !password) {
            return { success: false, message: "Введите логин и пароль." };
        }
        try {
            const res = await fetch("/api/auth/login", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username, password })
            });
            const data = await res.json();
            if (res.ok && data.success && data.token) {
                this.token = data.token;
                this.currentUser = data.user;
                localStorage.setItem(this.TOKEN_KEY, this.token);
                this.saveSession();
                this.updateUI();
                return { success: true };
            }
            return { success: false, message: data.error || "Неверный логин или пароль." };
        } catch (err) {
            console.error("loginWithPassword error:", err);
            return { success: false, message: `Ошибка сети: ${err.message}` };
        }
    },

    // ==========================================
    // Customer Support & Helpdesk
    // ==========================================
    supportPollTimer: null,
    activeAdminCustomerEmail: "",

    openSupportModal() {
        const modal = document.getElementById("support-modal");
        if (modal) {
            modal.classList.add("active");
            modal.style.visibility = "visible";
            modal.style.opacity = "1";
            modal.style.pointerEvents = "auto";
        }
        this.initSupportUI();
        this.startSupportPolling();
    },

    closeSupportModal() {
        const modal = document.getElementById("support-modal");
        if (modal) {
            modal.classList.remove("active");
            modal.style.visibility = "hidden";
            modal.style.opacity = "0";
            modal.style.pointerEvents = "none";
        }
        this.stopSupportPolling();
    },

    initSupportUI() {
        const isAdmin = this.currentUser && this.currentUser.role === "admin";
        const clientView = document.getElementById("support-client-view");
        const adminView = document.getElementById("support-admin-view");
        const headerSub = document.getElementById("support-header-sub");
        const guestEmailBox = document.getElementById("support-guest-email-box");

        if (isAdmin) {
            if (clientView) clientView.style.display = "none";
            if (adminView) adminView.style.display = "flex";
            if (headerSub) headerSub.textContent = "Панель администратора: диалоги и ответы клиентам.";
            this.loadSupportDialogs();
        } else {
            if (adminView) adminView.style.display = "none";
            if (clientView) clientView.style.display = "flex";
            if (headerSub) headerSub.textContent = "Задайте вопрос по сборке, оплате или гарантии — администратор ответит вам здесь.";
            if (guestEmailBox) {
                guestEmailBox.style.display = this.currentUser ? "none" : "block";
            }
            this.loadClientSupportMessages();
        }
    },

    async loadClientSupportMessages() {
        const container = document.getElementById("support-messages-container");
        if (!container) return;

        let email = this.currentUser ? this.currentUser.username : "";
        if (!email) {
            const guestInput = document.getElementById("support-guest-email");
            email = guestInput ? guestInput.value.trim() : (localStorage.getItem("skyrex_guest_support_email") || "");
            if (guestInput && !guestInput.value) guestInput.value = email;
        }

        if (!email) {
            container.innerHTML = `<div style="text-align:center; color: var(--text-muted); font-size:13px; margin:auto; padding:20px;">Напишите ваш вопрос и укажите email для связи. Администратор ответит вам здесь и пришлет копию на почту.</div>`;
            return;
        }

        try {
            const res = await fetch(`/api/support/messages?email=${encodeURIComponent(email)}`, {
                headers: this.getToken() ? { "Authorization": `Bearer ${this.getToken()}` } : {}
            });
            const data = await res.json();
            this.renderSupportMessagesList(container, data.messages || []);
        } catch (e) {
            console.warn("Could not load support messages:", e);
        }
    },

    renderSupportMessagesList(container, messages) {
        if (!messages || messages.length === 0) {
            container.innerHTML = `<div style="text-align:center; color: var(--text-muted); font-size:13px; margin:auto; padding:20px;">Диалог пуст. Задайте любой вопрос администратору!</div>`;
            return;
        }

        const isScrolledToBottom = container.scrollHeight - container.clientHeight <= container.scrollTop + 40;

        container.innerHTML = messages.map(m => {
            const isAdminMsg = m.sender === "admin";
            const timeStr = m.created_at ? m.created_at.replace("T", " ").slice(11, 16) : "";
            const bubbleClass = isAdminMsg ? "support-msg support-msg-admin" : "support-msg support-msg-user";
            const senderTitle = isAdminMsg ? "🛡️ Поддержка Skyrex" : "Вы";
            const escaped = this.escapeHtml(m.message);

            return `
                <div class="${bubbleClass}">
                    <div class="support-msg-sender">${senderTitle}</div>
                    <div class="support-msg-text">${escaped}</div>
                    <div class="support-msg-time">${timeStr}</div>
                </div>
            `;
        }).join("");

        if (isScrolledToBottom || !container.dataset.scrolled) {
            container.scrollTop = container.scrollHeight;
            container.dataset.scrolled = "true";
        }
    },

    async sendClientSupportMessage(text) {
        text = (text || "").trim();
        if (!text) return;

        let email = this.currentUser ? this.currentUser.username : "";
        if (!email) {
            const guestInput = document.getElementById("support-guest-email");
            email = guestInput ? guestInput.value.trim() : "";
            if (!email || !email.includes("@")) {
                const toastFn = (typeof showToast === "function") ? showToast : (window.showChatToast || null);
                if (toastFn) toastFn("Укажите ваш email, чтобы администратор мог ответить вам.", "warning");
                else alert("Укажите ваш email, чтобы администратор мог ответить вам.");
                return;
            }
            localStorage.setItem("skyrex_guest_support_email", email);
        }

        const sendBtn = document.getElementById("support-send-btn");
        if (sendBtn) sendBtn.disabled = true;

        try {
            const res = await fetch("/api/support/send", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    ...(this.getToken() ? { "Authorization": `Bearer ${this.getToken()}` } : {})
                },
                body: JSON.stringify({ email, message: text })
            });
            const data = await res.json();
            if (res.ok && data.success) {
                const input = document.getElementById("support-input");
                if (input) input.value = "";
                await this.loadClientSupportMessages();
            } else {
                const toastFn = (typeof showToast === "function") ? showToast : (window.showChatToast || null);
                if (toastFn) toastFn(data.error || "Ошибка отправки", "error");
            }
        } catch (e) {
            console.error("Support send error:", e);
        } finally {
            if (sendBtn) sendBtn.disabled = false;
        }
    },

    // Admin Helpdesk Methods
    async loadSupportDialogs() {
        if (!this.currentUser || this.currentUser.role !== "admin") return;
        try {
            const res = await fetch("/api/support/dialogs", {
                headers: { "Authorization": `Bearer ${this.getToken()}` }
            });
            const data = await res.json();
            const listEl = document.getElementById("support-admin-dialogs-list");
            const panelListEl = document.getElementById("admin-panel-dialogs-list");
            if (!listEl && !panelListEl) return;

            const dialogs = data.dialogs || [];
            if (dialogs.length === 0) {
                const emptyHtml = `<div style="color:var(--text-muted); font-size:12px; padding:10px;">Обращений пока нет.</div>`;
                if (listEl) listEl.innerHTML = emptyHtml;
                if (panelListEl) panelListEl.innerHTML = emptyHtml;
                return;
            }

            const html = dialogs.map(d => {
                const activeCls = (d.email === this.activeAdminCustomerEmail) ? "active" : "";
                const unreadBadge = d.unread_count > 0 ? `<span class="support-badge" style="float:right;">+${d.unread_count}</span>` : "";
                const lastSnippet = this.escapeHtml((d.last_message || "").slice(0, 30));
                return `
                    <div class="support-dialog-item ${activeCls}" onclick="SkyrexAuth.selectSupportDialog('${this.escapeHtml(d.email)}')">
                        <div style="font-weight:700; color:#fff; display:flex; justify-content:space-between; align-items:center;">
                            <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:130px;">${this.escapeHtml(d.email)}</span>
                            ${unreadBadge}
                        </div>
                        <div style="color:var(--text-muted); font-size:11px; margin-top:2px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
                            ${lastSnippet}
                        </div>
                    </div>
                `;
            }).join("");

            if (listEl) listEl.innerHTML = html;
            if (panelListEl) panelListEl.innerHTML = html;

            if (!this.activeAdminCustomerEmail && dialogs.length > 0) {
                this.selectSupportDialog(dialogs[0].email);
            }
        } catch (e) {
            console.warn("Could not load support dialogs:", e);
        }
    },

    async selectSupportDialog(email) {
        this.activeAdminCustomerEmail = email;
        const targetEmailEl = document.getElementById("support-admin-target-email");
        if (targetEmailEl) targetEmailEl.textContent = email;
        const panelTargetEmailEl = document.getElementById("admin-panel-target-email");
        if (panelTargetEmailEl) panelTargetEmailEl.textContent = email;

        const input = document.getElementById("support-admin-input");
        const btn = document.getElementById("support-admin-send-btn");
        if (input) input.disabled = false;
        if (btn) btn.disabled = false;

        const panelInput = document.getElementById("admin-panel-reply-input");
        const panelBtn = document.getElementById("admin-panel-reply-btn");
        const panelDelBtn = document.getElementById("admin-panel-delete-dialog-btn");
        if (panelInput) panelInput.disabled = false;
        if (panelBtn) panelBtn.disabled = false;
        if (panelDelBtn) panelDelBtn.style.display = "inline-block";

        // Highlight active item in sidebars
        const items = document.querySelectorAll(".support-dialog-item");
        items.forEach(el => {
            if (el.textContent.includes(email)) el.classList.add("active");
            else el.classList.remove("active");
        });

        await this.loadAdminActiveChat();
    },

    async loadAdminActiveChat() {
        if (!this.activeAdminCustomerEmail) return;
        const container = document.getElementById("support-admin-messages-container");
        const panelContainer = document.getElementById("admin-panel-messages-container");
        if (!container && !panelContainer) return;

        try {
            const res = await fetch(`/api/support/messages?email=${encodeURIComponent(this.activeAdminCustomerEmail)}`, {
                headers: { "Authorization": `Bearer ${this.getToken()}` }
            });
            const data = await res.json();
            const msgs = data.messages || [];
            if (container) this.renderSupportMessagesList(container, msgs);
            if (panelContainer) this.renderSupportMessagesList(panelContainer, msgs);
        } catch (e) {
            console.warn("Could not load admin chat messages:", e);
        }
    },

    async sendAdminSupportReply(text) {
        text = (text || "").trim();
        if (!text || !this.activeAdminCustomerEmail) return;

        const btn = document.getElementById("support-admin-send-btn");
        const panelBtn = document.getElementById("admin-panel-reply-btn");
        if (btn) btn.disabled = true;
        if (panelBtn) panelBtn.disabled = true;

        try {
            const res = await fetch("/api/support/send", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${this.getToken()}`
                },
                body: JSON.stringify({ email: this.activeAdminCustomerEmail, message: text })
            });
            const data = await res.json();
            if (res.ok && data.success) {
                const input = document.getElementById("support-admin-input");
                if (input) input.value = "";
                const panelInput = document.getElementById("admin-panel-reply-input");
                if (panelInput) panelInput.value = "";
                await this.loadAdminActiveChat();
                this.loadSupportDialogs();
                const toastFn = (typeof showToast === "function") ? showToast : (window.showChatToast || null);
                if (toastFn) toastFn("Ответ отправлен клиенту (и продублирован на email)!", "success");
            } else {
                const toastFn = (typeof showToast === "function") ? showToast : (window.showChatToast || null);
                if (toastFn) toastFn(data.error || "Ошибка отправки", "error");
            }
        } catch (e) {
            console.error("Admin support send error:", e);
        } finally {
            if (btn) btn.disabled = false;
            if (panelBtn) panelBtn.disabled = false;
        }
    },

    async deleteSelectedDialog() {
        if (!this.activeAdminCustomerEmail) return;
        if (!confirm(`Удалить диалог с ${this.activeAdminCustomerEmail}? История сообщений будет очищена.`)) return;

        try {
            const res = await fetch("/api/admin/support/delete", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${this.getToken()}`
                },
                body: JSON.stringify({ email: this.activeAdminCustomerEmail })
            });
            const data = await res.json();
            if (res.ok && data.success) {
                this.activeAdminCustomerEmail = "";
                const targetEmailEl = document.getElementById("support-admin-target-email");
                if (targetEmailEl) targetEmailEl.textContent = "Выберите клиента";
                const panelTargetEmailEl = document.getElementById("admin-panel-target-email");
                if (panelTargetEmailEl) panelTargetEmailEl.textContent = "Выберите обращение слева";

                const container = document.getElementById("support-admin-messages-container");
                if (container) container.innerHTML = `<div style="text-align: center; color: var(--text-muted); font-size: 12px; margin: auto;">Диалог удален</div>`;
                const panelContainer = document.getElementById("admin-panel-messages-container");
                if (panelContainer) panelContainer.innerHTML = `<div style="text-align: center; color: var(--text-muted); font-size: 12px; margin: auto;">Диалог удален</div>`;

                const delBtn = document.getElementById("admin-panel-delete-dialog-btn");
                if (delBtn) delBtn.style.display = "none";

                this.loadSupportDialogs();
                const toastFn = (typeof showToast === "function") ? showToast : (window.showChatToast || null);
                if (toastFn) toastFn("Диалог успешно удален", "success");
            } else {
                alert(data.error || "Ошибка удаления");
            }
        } catch (e) {
            console.error("deleteSelectedDialog error:", e);
        }
    },

    startSupportPolling() {
        this.stopSupportPolling();
        this.supportPollTimer = setInterval(() => {
            const isAdmin = this.currentUser && this.currentUser.role === "admin";
            if (isAdmin) {
                this.loadAdminActiveChat();
                this.loadSupportDialogs();
            } else {
                this.loadClientSupportMessages();
            }
        }, 4000);
    },

    stopSupportPolling() {
        if (this.supportPollTimer) {
            clearInterval(this.supportPollTimer);
            this.supportPollTimer = null;
        }
    },

    // ==========================================
    // On-site Web Admin Panel
    // ==========================================
    openAdminPanel(tab = "support") {
        if (!this.currentUser || this.currentUser.role !== "admin") {
            const toastFn = (typeof showToast === "function") ? showToast : (window.showChatToast || null);
            if (toastFn) toastFn("Доступ разрешен только администраторам.", "error");
            else alert("Доступ разрешен только администраторам.");
            return;
        }
        const modal = document.getElementById("admin-panel-modal");
        if (modal) {
            modal.classList.add("active");
            modal.style.visibility = "visible";
            modal.style.opacity = "1";
            modal.style.pointerEvents = "auto";
        }
        this.switchAdminTab(tab);
    },

    closeAdminPanel() {
        const modal = document.getElementById("admin-panel-modal");
        if (modal) {
            modal.classList.remove("active");
            modal.style.visibility = "hidden";
            modal.style.opacity = "0";
            modal.style.pointerEvents = "none";
        }
        this.stopSupportPolling();
    },

    switchAdminTab(tab) {
        // Toggle tab buttons
        document.querySelectorAll(".admin-tab-btn").forEach(btn => {
            if (btn.getAttribute("data-tab") === tab) {
                btn.classList.add("active");
            } else {
                btn.classList.remove("active");
            }
        });

        // Toggle tab panes
        document.querySelectorAll(".admin-tab-pane").forEach(pane => {
            if (pane.id === `admin-tab-${tab}`) {
                pane.classList.add("active");
                pane.style.display = "flex";
            } else {
                pane.classList.remove("active");
                pane.style.display = "none";
            }
        });

        // Trigger loader for specific tab
        if (tab === "support") {
            this.loadSupportDialogs();
            this.startSupportPolling();
        } else {
            this.stopSupportPolling();
            if (tab === "rules") {
                this.loadAdminRules();
                this.loadAdminPrompt();
            } else if (tab === "components") {
                this.loadAdminComponents();
            } else if (tab === "payments") {
                this.loadAdminPayments();
                this.loadAdminUsers();
            } else if (tab === "stats") {
                this.loadAdminStats();
            }
        }
    },

    // --- TAB: Rules & System Prompt ---
    async loadAdminRules() {
        const container = document.getElementById("admin-rules-list");
        if (!container) return;
        try {
            const res = await fetch("/api/admin/rules", {
                headers: { "Authorization": `Bearer ${this.getToken()}` }
            });
            const data = await res.json();
            const rules = data.rules || [];
            if (rules.length === 0) {
                container.innerHTML = `<div style="color:var(--text-muted); font-size:12px; padding:10px; background:rgba(255,255,255,0.02); border-radius:8px;">Оперативных правил пока нет. Все правила регулируются эталонным системным промптом.</div>`;
                return;
            }
            container.innerHTML = rules.map(r => `
                <div class="admin-rule-card" style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); border-radius:8px; padding:12px; display:flex; justify-content:space-between; align-items:flex-start; gap:12px;">
                    <div style="flex:1;">
                        <div style="font-weight:700; color:#00ffcc; font-size:13px; margin-bottom:4px;">${this.escapeHtml(r.title || 'Правило #' + r.id)}</div>
                        <div style="color:#ddd; font-size:12px; line-height:1.4;">${this.escapeHtml(r.rule_text)}</div>
                        <div style="color:var(--text-muted); font-size:10px; margin-top:6px;">Автор: ${this.escapeHtml(r.author || 'admin')} • ${this.escapeHtml(r.created_at || '')}</div>
                    </div>
                    <button type="button" class="btn btn-secondary" style="padding:4px 10px; font-size:11px; color:#ff3366;" onclick="SkyrexAuth.deleteAdminRule(${r.id})">Удалить</button>
                </div>
            `).join("");
        } catch (e) {
            console.error("loadAdminRules error:", e);
        }
    },

    async addAdminRule(title, rule_text) {
        try {
            const res = await fetch("/api/admin/rules/add", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${this.getToken()}`
                },
                body: JSON.stringify({ title, rule_text })
            });
            const data = await res.json();
            if (res.ok && data.success) {
                const titleInp = document.getElementById("admin-rule-title");
                const textInp = document.getElementById("admin-rule-text");
                if (titleInp) titleInp.value = "";
                if (textInp) textInp.value = "";
                this.loadAdminRules();
                const toastFn = (typeof showToast === "function") ? showToast : (window.showChatToast || null);
                if (toastFn) toastFn("Правило успешно добавлено!", "success");
            } else {
                alert(data.error || "Ошибка добавления правила");
            }
        } catch (e) {
            console.error("addAdminRule error:", e);
        }
    },

    async deleteAdminRule(ruleId) {
        if (!confirm("Удалить это оперативное правило?")) return;
        try {
            const res = await fetch("/api/admin/rules/delete", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${this.getToken()}`
                },
                body: JSON.stringify({ rule_id: ruleId })
            });
            const data = await res.json();
            if (res.ok && data.success) {
                this.loadAdminRules();
                const toastFn = (typeof showToast === "function") ? showToast : (window.showChatToast || null);
                if (toastFn) toastFn("Правило удалено", "success");
            }
        } catch (e) {
            console.error("deleteAdminRule error:", e);
        }
    },

    async resetAdminRules() {
        if (!confirm("Сбросить ВСЕ оперативные правила ИИ? Базовый системный промпт останется неизменным.")) return;
        try {
            const res = await fetch("/api/admin/rules/reset", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${this.getToken()}`
                }
            });
            const data = await res.json();
            if (res.ok && data.success) {
                this.loadAdminRules();
                const toastFn = (typeof showToast === "function") ? showToast : (window.showChatToast || null);
                if (toastFn) toastFn(`Все правила сброшены (${data.deleted_count || 0})`, "success");
            }
        } catch (e) {
            console.error("resetAdminRules error:", e);
        }
    },

    async loadAdminPrompt() {
        const textarea = document.getElementById("admin-prompt-editor");
        if (!textarea) return;
        try {
            const res = await fetch("/api/admin/prompt", {
                headers: { "Authorization": `Bearer ${this.getToken()}` }
            });
            const data = await res.json();
            if (data.prompt) {
                textarea.value = data.prompt;
            }
        } catch (e) {
            console.error("loadAdminPrompt error:", e);
        }
    },

    async saveAdminPrompt() {
        const textarea = document.getElementById("admin-prompt-editor");
        if (!textarea) return;
        const text = textarea.value.trim();
        if (!text) {
            alert("Промпт не может быть пустым");
            return;
        }
        try {
            const res = await fetch("/api/admin/prompt/update", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${this.getToken()}`
                },
                body: JSON.stringify({ prompt: text })
            });
            const data = await res.json();
            if (res.ok && data.success) {
                const toastFn = (typeof showToast === "function") ? showToast : (window.showChatToast || null);
                if (toastFn) toastFn("Системный промпт ИИ успешно обновлен!", "success");
            } else {
                alert(data.error || "Ошибка сохранения промпта");
            }
        } catch (e) {
            console.error("saveAdminPrompt error:", e);
        }
    },

    async resetAdminPrompt() {
        if (!confirm("Восстановить системный промпт к исходному эталонному коду?")) return;
        try {
            const res = await fetch("/api/admin/prompt/reset", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${this.getToken()}`
                }
            });
            const data = await res.json();
            if (res.ok && data.success) {
                const textarea = document.getElementById("admin-prompt-editor");
                if (textarea && data.prompt) textarea.value = data.prompt;
                const toastFn = (typeof showToast === "function") ? showToast : (window.showChatToast || null);
                if (toastFn) toastFn("Системный промпт восстановлен к эталону!", "success");
            }
        } catch (e) {
            console.error("resetAdminPrompt error:", e);
        }
    },

    // --- TAB: Expert Components ---
    async loadAdminComponents() {
        const container = document.getElementById("admin-components-list");
        if (!container) return;
        try {
            const res = await fetch("/api/admin/components", {
                headers: { "Authorization": `Bearer ${this.getToken()}` }
            });
            const data = await res.json();
            const comps = data.components || [];
            if (comps.length === 0) {
                container.innerHTML = `<div style="color:var(--text-muted); font-size:12px; padding:10px; background:rgba(255,255,255,0.02); border-radius:8px;">Экспертные комплектующие еще не добавлены. Добавьте первую деталь через форму выше.</div>`;
                return;
            }
            container.innerHTML = comps.map(c => `
                <div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); border-radius:8px; padding:10px 14px; display:flex; justify-content:space-between; align-items:center; gap:12px;">
                    <div style="flex:1;">
                        <div style="display:flex; align-items:center; gap:8px; margin-bottom:4px;">
                            <span style="font-size:10px; text-transform:uppercase; background:rgba(0,255,204,0.15); color:#00ffcc; padding:2px 6px; border-radius:4px; font-weight:700;">${this.escapeHtml(c.category)}</span>
                            <span style="font-weight:700; color:#fff; font-size:13px;">${this.escapeHtml(c.name)}</span>
                            <span style="color:#00ffcc; font-weight:700; font-size:13px;">${Number(c.price).toLocaleString('ru-RU')} ₽</span>
                            <span style="font-size:11px; color:var(--text-muted);">(${this.escapeHtml(c.shop)})</span>
                        </div>
                        <div style="font-size:11px; color:#aaa; display:flex; gap:12px; align-items:center;">
                            <a href="${this.escapeHtml(c.url)}" target="_blank" rel="noopener noreferrer" style="color:#3399ff; text-decoration:underline;">Открыть ссылку ↗</a>
                            ${c.comment ? `<span>${this.escapeHtml(c.comment)}</span>` : ''}
                        </div>
                    </div>
                    <button type="button" class="btn btn-secondary" style="padding:4px 10px; font-size:11px; color:#ff3366;" onclick="SkyrexAuth.deleteAdminComponent(${c.id})">Удалить</button>
                </div>
            `).join("");
        } catch (e) {
            console.error("loadAdminComponents error:", e);
        }
    },

    async addAdminComponent(data) {
        try {
            const res = await fetch("/api/admin/components/add", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${this.getToken()}`
                },
                body: JSON.stringify(data)
            });
            const resData = await res.json();
            if (res.ok && resData.success) {
                const nameInp = document.getElementById("admin-comp-name");
                const priceInp = document.getElementById("admin-comp-price");
                const urlInp = document.getElementById("admin-comp-url");
                const commentInp = document.getElementById("admin-comp-comment");
                if (nameInp) nameInp.value = "";
                if (priceInp) priceInp.value = "";
                if (urlInp) urlInp.value = "";
                if (commentInp) commentInp.value = "";
                this.loadAdminComponents();
                const toastFn = (typeof showToast === "function") ? showToast : (window.showChatToast || null);
                if (toastFn) toastFn("Комплектующая добавлена в каталог!", "success");
            } else {
                alert(resData.error || "Ошибка добавления детали");
            }
        } catch (e) {
            console.error("addAdminComponent error:", e);
        }
    },

    async deleteAdminComponent(compId) {
        if (!confirm("Удалить деталь из каталога?")) return;
        try {
            const res = await fetch("/api/admin/components/delete", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${this.getToken()}`
                },
                body: JSON.stringify({ component_id: compId })
            });
            const data = await res.json();
            if (res.ok && data.success) {
                this.loadAdminComponents();
                const toastFn = (typeof showToast === "function") ? showToast : (window.showChatToast || null);
                if (toastFn) toastFn("Деталь удалена", "success");
            }
        } catch (e) {
            console.error("deleteAdminComponent error:", e);
        }
    },

    // --- TAB: Payments & Users ---
    async loadAdminPayments() {
        const tbody = document.getElementById("admin-payments-tbody");
        if (!tbody) return;
        try {
            const res = await fetch("/api/admin/payments", {
                headers: { "Authorization": `Bearer ${this.getToken()}` }
            });
            const data = await res.json();
            const list = data.payments || [];
            if (list.length === 0) {
                tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:var(--text-muted); padding:16px;">Транзакций пока нет.</td></tr>`;
                return;
            }
            tbody.innerHTML = list.map(p => {
                const statusColor = p.status === 'succeeded' ? '#00ffcc' : (p.status === 'pending' ? '#ffaa00' : '#ff3366');
                const statusLabel = p.status === 'succeeded' ? 'Оплачено' : (p.status === 'pending' ? 'Ожидает' : p.status);
                return `
                    <tr>
                        <td style="font-family:monospace; font-size:11px;">${this.escapeHtml((p.payment_id || '').slice(0, 16))}...</td>
                        <td>${this.escapeHtml(p.email || '—')}</td>
                        <td style="font-weight:700; color:#fff;">${Number(p.amount || 0).toLocaleString('ru-RU')} ₽</td>
                        <td><span style="color:${statusColor}; font-weight:700; font-size:11px;">${statusLabel}</span></td>
                        <td style="color:var(--text-muted); font-size:11px;">${this.escapeHtml(p.created_at || '—')}</td>
                    </tr>
                `;
            }).join("");
        } catch (e) {
            console.error("loadAdminPayments error:", e);
        }
    },

    async loadAdminUsers() {
        const tbody = document.getElementById("admin-users-tbody");
        if (!tbody) return;
        try {
            const res = await fetch("/api/admin/users", {
                headers: { "Authorization": `Bearer ${this.getToken()}` }
            });
            const data = await res.json();
            const list = data.users || [];
            if (list.length === 0) {
                tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:var(--text-muted); padding:16px;">Пользователей пока нет.</td></tr>`;
                return;
            }
            tbody.innerHTML = list.map(u => {
                const isSub = !!u.subscribed;
                const subBadge = isSub ? `<span style="color:#00ffcc; font-weight:700;">Активна</span>` : `<span style="color:var(--text-muted);">Базовый</span>`;
                const roleBadge = u.role === 'admin' ? `<span style="color:#ffcc00; font-weight:700;">Админ</span>` : `Пользователь`;
                let expires = u.subscription_expires || '—';
                if (expires && expires.startsWith('2099')) expires = 'Бессрочно';
                return `
                    <tr>
                        <td style="color:var(--text-muted); font-size:11px;">#${u.id}</td>
                        <td style="font-weight:700; color:#fff;">${this.escapeHtml(u.email || '')}</td>
                        <td>${this.escapeHtml(u.nickname || '—')}</td>
                        <td>${roleBadge}</td>
                        <td>${subBadge}</td>
                        <td style="color:var(--text-muted); font-size:11px;">${this.escapeHtml(expires)}</td>
                    </tr>
                `;
            }).join("");
        } catch (e) {
            console.error("loadAdminUsers error:", e);
        }
    },

    async activateAdminUserSub(userId, days) {
        try {
            const res = await fetch("/api/admin/subscriptions/activate", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${this.getToken()}`
                },
                body: JSON.stringify({ user_id: userId, days: days })
            });
            const data = await res.json();
            if (res.ok && data.success) {
                this.loadAdminUsers();
                const toastFn = (typeof showToast === "function") ? showToast : (window.showChatToast || null);
                if (toastFn) toastFn(`Подписка активирована для пользователя #${userId} на ${days} дней!`, "success");
            } else {
                alert(data.error || "Ошибка активации подписки");
            }
        } catch (e) {
            console.error("activateAdminUserSub error:", e);
        }
    },

    // --- TAB: System Stats ---
    async loadAdminStats() {
        const container = document.getElementById("admin-stats-cards");
        if (!container) return;
        try {
            const res = await fetch("/api/admin/stats", {
                headers: { "Authorization": `Bearer ${this.getToken()}` }
            });
            const data = await res.json();
            if (data.success) {
                const cs = data.catalog_stats || {};
                container.innerHTML = `
                    <div class="admin-stat-card" style="background:rgba(255,255,255,0.03); border:1px solid rgba(0,255,204,0.2); border-radius:12px; padding:16px;">
                        <div style="font-size:11px; text-transform:uppercase; color:var(--text-muted); margin-bottom:6px;">Всего пользователей</div>
                        <div style="font-size:24px; font-weight:800; color:#fff;">${data.users_count || 0}</div>
                    </div>
                    <div class="admin-stat-card" style="background:rgba(255,255,255,0.03); border:1px solid rgba(0,255,204,0.2); border-radius:12px; padding:16px;">
                        <div style="font-size:11px; text-transform:uppercase; color:var(--text-muted); margin-bottom:6px;">Активных премиум-подписок</div>
                        <div style="font-size:24px; font-weight:800; color:#00ffcc;">${data.active_subscribers || 0}</div>
                    </div>
                    <div class="admin-stat-card" style="background:rgba(255,255,255,0.03); border:1px solid rgba(0,255,204,0.2); border-radius:12px; padding:16px;">
                        <div style="font-size:11px; text-transform:uppercase; color:var(--text-muted); margin-bottom:6px;">Общая выручка</div>
                        <div style="font-size:24px; font-weight:800; color:#ffcc00;">${Number(data.total_revenue || 0).toLocaleString('ru-RU')} ₽</div>
                    </div>
                    <div class="admin-stat-card" style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); border-radius:12px; padding:16px;">
                        <div style="font-size:11px; text-transform:uppercase; color:var(--text-muted); margin-bottom:6px;">Успешных оплат</div>
                        <div style="font-size:24px; font-weight:800; color:#fff;">${data.payments_count || 0}</div>
                    </div>
                    <div class="admin-stat-card" style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); border-radius:12px; padding:16px;">
                        <div style="font-size:11px; text-transform:uppercase; color:var(--text-muted); margin-bottom:6px;">Диалогов в техподдержке</div>
                        <div style="font-size:24px; font-weight:800; color:#00ffcc;">${data.dialogs_count || 0}</div>
                    </div>
                    <div class="admin-stat-card" style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); border-radius:12px; padding:16px;">
                        <div style="font-size:11px; text-transform:uppercase; color:var(--text-muted); margin-bottom:6px;">Комплектующих в базе</div>
                        <div style="font-size:24px; font-weight:800; color:#fff;">${cs.total_components || 0}</div>
                    </div>
                `;
            }
        } catch (e) {
            console.error("loadAdminStats error:", e);
        }
    },

    escapeHtml(str) {
        if (!str) return "";
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    },

    // Overall layout UI Synchronization
    updateUI() {
        if (!this.dom || !this.dom.authStatusDot) {
            this.setupDOM();
        }
        if (this.dom.authStatusDot) {
            if (this.currentUser) {
                if (this.currentUser.subscribed) {
                    this.dom.authStatusDot.className = "auth-status-dot active-premium";
                } else {
                    this.dom.authStatusDot.className = "auth-status-dot active-base";
                }
            } else {
                this.dom.authStatusDot.className = "auth-status-dot";
            }
        }

        const isAdmin = this.currentUser && this.currentUser.role === "admin";
        const navAdminLink = document.getElementById("nav-admin-link");
        if (navAdminLink) {
            navAdminLink.style.display = isAdmin ? "inline-block" : "none";
        }
        const profileAdminBtn = document.getElementById("profile-admin-btn");
        if (profileAdminBtn) {
            profileAdminBtn.style.display = isAdmin ? "block" : "none";
        }
    },

    switchAuthTab(step) {
        this.goToStep(step);
    }
};

// Global backward-compatible switchAuthTab helper
function switchAuthTab(tab) {
    if (window.SkyrexAuth) {
        SkyrexAuth.goToStep(tab || "login");
    }
}

// Auto init on load
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => SkyrexAuth.init());
} else {
    SkyrexAuth.init();
}
