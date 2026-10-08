// Skyrex - General Layout Behavior
// Handles header background activation on scroll

document.addEventListener("DOMContentLoaded", () => {
    const mainHeader = document.getElementById("main-header");
    if (mainHeader) {
        window.addEventListener("scroll", () => {
            if (window.scrollY > 50) {
                mainHeader.classList.add("scrolled");
            } else {
                mainHeader.classList.remove("scrolled");
            }
        });
    }
});
