// EcoTrack — small client-side enhancements

document.addEventListener("DOMContentLoaded", function () {
    // Auto-dismiss flash messages after a few seconds
    const flashes = document.querySelectorAll(".flash");
    flashes.forEach(function (el) {
        setTimeout(function () {
            el.style.transition = "opacity 0.4s ease";
            el.style.opacity = "0";
            setTimeout(function () { el.remove(); }, 400);
        }, 4500);
    });

    document.querySelectorAll(".password-toggle").forEach(function (button) {
        button.addEventListener("click", function () {
            const input = document.getElementById(button.dataset.target);
            const visible = input.type === "text";
            input.type = visible ? "password" : "text";
            button.textContent = visible ? "Show" : "Hide";
            button.setAttribute("aria-label", visible ? "Show password" : "Hide password");
        });
    });

    const password = document.getElementById("password");
    const strengthBar = document.getElementById("strength-bar");
    const strengthLabel = document.getElementById("strength-label");
    if (password && strengthBar && strengthLabel) {
        password.addEventListener("input", function () {
            const value = password.value;
            const checks = {
                length: value.length >= 8,
                upper: /[A-Z]/.test(value),
                lower: /[a-z]/.test(value),
                number: /\d/.test(value),
                special: /[^A-Za-z0-9]/.test(value)
            };
            let score = Object.values(checks).filter(Boolean).length;
            if (value.length >= 12) score = Math.min(5, score + 1);
            strengthBar.dataset.score = score;
            strengthLabel.textContent = ["Very weak", "Weak", "Medium", "Strong", "Very strong", "Very strong"][score];
            document.querySelectorAll(".password-rules li").forEach(function (rule) {
                rule.classList.toggle("valid", checks[rule.dataset.rule]);
            });
        });
    }

    const revealObserver = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
            if (entry.isIntersecting) {
                entry.target.classList.add("is-visible");
                revealObserver.unobserve(entry.target);
            }
        });
    }, { threshold: 0.12 });
    document.querySelectorAll(".content-section, .split-section, .lifestyle-section, .education-section, .about-section, .cta-band").forEach(function (element) {
        element.classList.add("reveal-on-scroll");
        revealObserver.observe(element);
    });
});
