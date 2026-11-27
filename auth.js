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

    // Step 1: Request OTP code to email
    async sendCode(email) {
        email = (email || "").trim().toLowerCase();
        if (!email) {
            return { success: false, message: "Введите адрес электронной почты." };
        }
        try {
            const res = await fetch("/api/auth/send-code", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email })
            });
            const data = await res.json();
            if (res.ok && data.success) {
                this.pendingEmail = email;
                return { success: true, message: data.message };
            }
            return { success: false, message: data.error || "Не удалось отправить код." };
        } catch (err) {
            console.error("sendCode error:", err);
            return { success: false, message: `Ошибка связи с сервером: ${err.message}` };
        }
    },

    // Step 2: Verify OTP code
    async verifyCode(code) {
        code = (code || "").trim();
        if (!this.pendingEmail) {
            return { success: false, message: "Адрес почты не указан. Вернитесь назад." };
        }
        if (!code || code.length !== 6) {
            return { success: false, message: "Введите полный 6-значный код." };
        }

        try {
            const res = await fetch("/api/auth/verify-code", {
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
            console.error("verifyCode error:", err);
            return { success: false, message: `Ошибка связи с сервером: ${err.message}` };
        }
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
            stepEmail: document.getElementById("auth-step-email"),
            stepCode: document.getElementById("auth-step-code"),
            stepPassword: document.getElementById("auth-step-password"),
            switchPwdBtn: document.getElementById("auth-switch-pwd-btn"),
            backToEmailBtn: document.getElementById("auth-back-to-email-btn"),
            pwdForm: document.getElementById("auth-password-form"),
            pwdEmailInput: document.getElementById("auth-pwd-email-input"),
            pwdPasswordInput: document.getElementById("auth-pwd-password-input"),
            pwdError: document.getElementById("auth-pwd-error"),
            pwdSubmitBtn: document.getElementById("auth-pwd-submit-btn"),

            // Email step
            emailForm: document.getElementById("auth-email-form"),
            emailInput: document.getElementById("auth-email-input"),
            emailError: document.getElementById("auth-email-error"),
            sendBtn: document.getElementById("auth-send-btn"),

            // Code step
            codeForm: document.getElementById("auth-code-form"),
            codeInput: document.getElementById("auth-code-input"),
            codeError: document.getElementById("auth-code-error"),
            verifyBtn: document.getElementById("auth-verify-btn"),
            targetEmailDisplay: document.getElementById("auth-target-email-display"),
            backBtn: document.getElementById("auth-back-btn"),
            resendBtn: document.getElementById("auth-resend-btn"),
            countdownSpan: document.getElementById("auth-countdown"),

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
            }
        });

        // Switch to Password Login (Admin)
        if (this.dom.switchPwdBtn) {
            this.dom.switchPwdBtn.addEventListener("click", () => this.goToStep("password"));
        }
        if (this.dom.backToEmailBtn) {
            this.dom.backToEmailBtn.addEventListener("click", () => this.goToStep("email"));
        }

        // Submit Password Form
        if (this.dom.pwdForm) {
            this.dom.pwdForm.addEventListener("submit", async (e) => {
                e.preventDefault();
                if (this.dom.pwdError) this.dom.pwdError.textContent = "";

                const username = this.dom.pwdEmailInput ? this.dom.pwdEmailInput.value.trim() : "";
                const password = this.dom.pwdPasswordInput ? this.dom.pwdPasswordInput.value : "";

                if (!username || !password) {
                    if (this.dom.pwdError) this.dom.pwdError.textContent = "Введите логин и пароль.";
                    return;
                }

                if (this.dom.pwdSubmitBtn) {
                    this.dom.pwdSubmitBtn.disabled = true;
                    this.dom.pwdSubmitBtn.innerHTML = `<span>Вход...</span>`;
                }

                const res = await this.loginWithPassword(username, password);

                if (this.dom.pwdSubmitBtn) {
                    this.dom.pwdSubmitBtn.disabled = false;
                    this.dom.pwdSubmitBtn.innerHTML = `<span>Войти</span>`;
                }

                if (res.success) {
                    this.closeAuthModal();
                    if (this.dom.pwdPasswordInput) this.dom.pwdPasswordInput.value = "";
                    const toastFn = (typeof showToast === "function") ? showToast : (window.showChatToast || null);
                    if (toastFn) {
                        toastFn("Успешный вход в аккаунт администратора!", "success");
                    }
                } else if (this.dom.pwdError) {
                    this.dom.pwdError.textContent = res.message;
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

        // Support Admin Send Form
        if (this.dom.supportAdminSendForm) {
            this.dom.supportAdminSendForm.addEventListener("submit", (e) => {
                e.preventDefault();
                const text = this.dom.supportAdminInput ? this.dom.supportAdminInput.value : "";
                this.sendAdminSupportReply(text);
            });
        }

        // Step 1: Submit Email
        if (this.dom.emailForm) {
            this.dom.emailForm.addEventListener("submit", async (e) => {
                e.preventDefault();
                if (this.dom.emailError) this.dom.emailError.textContent = "";

                const email = this.dom.emailInput ? this.dom.emailInput.value.trim() : "";
                if (!email) {
                    if (this.dom.emailError) this.dom.emailError.textContent = "Введите адрес электронной почты.";
                    return;
                }

                if (this.dom.sendBtn) {
                    this.dom.sendBtn.disabled = true;
                    this.dom.sendBtn.innerHTML = `<span>Отправка кода...</span>`;
                }

                const res = await this.sendCode(email);

                if (this.dom.sendBtn) {
                    this.dom.sendBtn.disabled = false;
                    this.dom.sendBtn.innerHTML = `<span>Получить код</span>`;
                }

                if (res.success) {
                    this.goToStep("code");
                    this.startCountdown(60);
                } else if (this.dom.emailError) {
                    this.dom.emailError.textContent = res.message;
                }
            });
        }

        // Step 2: Format & Auto-submit Code
        if (this.dom.codeInput) {
            this.dom.codeInput.addEventListener("input", (e) => {
                // Keep only digits, max 6
                e.target.value = e.target.value.replace(/\D/g, "").slice(0, 6);
                if (this.dom.codeError) this.dom.codeError.textContent = "";

                // If user entered 6 digits, auto-submit
                if (e.target.value.length === 6) {
                    this.handleCodeSubmit();
                }
            });
        }

        // Step 2: Submit Code Form
        if (this.dom.codeForm) {
            this.dom.codeForm.addEventListener("submit", (e) => {
                e.preventDefault();
                this.handleCodeSubmit();
            });
        }

        // Step 2: Back to Email button
        if (this.dom.backBtn) {
            this.dom.backBtn.addEventListener("click", () => {
                this.goToStep("email");
            });
        }

        // Step 2: Resend code button
        if (this.dom.resendBtn) {
            this.dom.resendBtn.addEventListener("click", async () => {
                if (this.dom.resendBtn.disabled || !this.pendingEmail) return;
                this.dom.resendBtn.disabled = true;
                this.dom.resendBtn.textContent = "Отправка...";
                if (this.dom.codeError) this.dom.codeError.textContent = "";

                const res = await this.sendCode(this.pendingEmail);
                if (res.success) {
                    this.startCountdown(60);
                } else {
                    if (this.dom.codeError) this.dom.codeError.textContent = res.message;
                    this.dom.resendBtn.disabled = false;
                    this.dom.resendBtn.textContent = "Отправить повторно";
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

    async handleCodeSubmit() {
        const code = this.dom.codeInput ? this.dom.codeInput.value.trim() : "";
        if (!code || code.length !== 6) {
            if (this.dom.codeError) this.dom.codeError.textContent = "Введите 6 цифр кода.";
            return;
        }

        if (this.dom.verifyBtn) {
            this.dom.verifyBtn.disabled = true;
            this.dom.verifyBtn.innerHTML = `<span>Проверка...</span>`;
        }

        const res = await this.verifyCode(code);

        if (this.dom.verifyBtn) {
            this.dom.verifyBtn.disabled = false;
            this.dom.verifyBtn.innerHTML = `<span>Подтвердить и войти</span>`;
        }

        if (res.success) {
            this.closeAuthModal();
            if (this.dom.codeInput) this.dom.codeInput.value = "";
            if (this.dom.emailInput) this.dom.emailInput.value = "";
            this.pendingEmail = "";
            this.stopCountdown();
            if (typeof showToast === "function") {
                showToast("Успешный вход в аккаунт!", "success");
            }
        } else if (this.dom.codeError) {
            this.dom.codeError.textContent = res.message;
        }
    },

    goToStep(step) {
        if (!this.dom.stepEmail || !this.dom.stepCode) {
            this.setupDOM();
        }
        if (this.dom.emailError) this.dom.emailError.textContent = "";
        if (this.dom.codeError) this.dom.codeError.textContent = "";
        if (this.dom.pwdError) this.dom.pwdError.textContent = "";

        if (step === "code") {
            if (this.dom.stepEmail) this.dom.stepEmail.classList.remove("active");
            if (this.dom.stepPassword) this.dom.stepPassword.classList.remove("active");
            if (this.dom.stepCode) this.dom.stepCode.classList.add("active");
            if (this.dom.targetEmailDisplay) this.dom.targetEmailDisplay.textContent = this.pendingEmail;
            if (this.dom.codeInput) {
                this.dom.codeInput.value = "";
                setTimeout(() => this.dom.codeInput.focus(), 100);
            }
        } else if (step === "password") {
            if (this.dom.stepEmail) this.dom.stepEmail.classList.remove("active");
            if (this.dom.stepCode) this.dom.stepCode.classList.remove("active");
            if (this.dom.stepPassword) this.dom.stepPassword.classList.add("active");
            if (this.dom.pwdEmailInput) {
                setTimeout(() => this.dom.pwdEmailInput.focus(), 100);
            }
            this.stopCountdown();
        } else {
            if (this.dom.stepCode) this.dom.stepCode.classList.remove("active");
            if (this.dom.stepPassword) this.dom.stepPassword.classList.remove("active");
            if (this.dom.stepEmail) this.dom.stepEmail.classList.add("active");
            if (this.dom.emailInput) {
                setTimeout(() => this.dom.emailInput.focus(), 100);
            }
            this.stopCountdown();
        }
    },

    startCountdown(seconds) {
        this.stopCountdown();
        this.countdownSeconds = seconds || 60;
        if (!this.dom.resendBtn) return;

        this.dom.resendBtn.disabled = true;
        this.dom.resendBtn.innerHTML = `Отправить повторно через <span id="auth-countdown">${this.countdownSeconds}</span>с`;

        this.countdownTimer = setInterval(() => {
            this.countdownSeconds--;
            const span = document.getElementById("auth-countdown");
            if (span) span.textContent = this.countdownSeconds;

            if (this.countdownSeconds <= 0) {
                this.stopCountdown();
                if (this.dom.resendBtn) {
                    this.dom.resendBtn.disabled = false;
                    this.dom.resendBtn.textContent = "Отправить код повторно";
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
        this.goToStep("email");
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
            if (!listEl) return;

            const dialogs = data.dialogs || [];
            if (dialogs.length === 0) {
                listEl.innerHTML = `<div style="color:var(--text-muted); font-size:12px; padding:10px;">Обращений пока нет.</div>`;
                return;
            }

            listEl.innerHTML = dialogs.map(d => {
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

        const input = document.getElementById("support-admin-input");
        const btn = document.getElementById("support-admin-send-btn");
        if (input) input.disabled = false;
        if (btn) btn.disabled = false;

        // Highlight active item in sidebar
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
        if (!container) return;

        try {
            const res = await fetch(`/api/support/messages?email=${encodeURIComponent(this.activeAdminCustomerEmail)}`, {
                headers: { "Authorization": `Bearer ${this.getToken()}` }
            });
            const data = await res.json();
            this.renderSupportMessagesList(container, data.messages || []);
        } catch (e) {
            console.warn("Could not load admin chat messages:", e);
        }
    },

    async sendAdminSupportReply(text) {
        text = (text || "").trim();
        if (!text || !this.activeAdminCustomerEmail) return;

        const btn = document.getElementById("support-admin-send-btn");
        if (btn) btn.disabled = true;

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
    }
};

// Global backward-compatible switchAuthTab helper
function switchAuthTab(tab) {
    if (window.SkyrexAuth) {
        SkyrexAuth.goToStep("email");
    }
}

// Auto init on load
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => SkyrexAuth.init());
} else {
    SkyrexAuth.init();
}
