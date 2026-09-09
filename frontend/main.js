document.addEventListener("DOMContentLoaded", () => {
  // Respect user preference for reduced motion
  const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // --- 1. Stat Counter Animation ---
  const easeOutCubic = (t) => 1 - Math.pow(1 - t, 3);

  const animateCounter = (el, index) => {
    const target = parseFloat(el.getAttribute("data-target"));
    const decimals = parseInt(el.getAttribute("data-decimals") || "0", 10);
    const suffix = el.getAttribute("data-suffix") || "";

    if (prefersReducedMotion) {
      el.textContent = target.toFixed(decimals) + suffix;
      return;
    }

    const duration = 1500 + index * 80; // ms
    const delay = 480 + index * 90;    // ms
    let startTime = null;

    setTimeout(() => {
      const step = (now) => {
        if (!startTime) startTime = now;
        const progress = Math.min((now - startTime) / duration, 1);
        const easedProgress = easeOutCubic(progress);
        const currentValue = easedProgress * target;

        el.textContent = currentValue.toFixed(decimals) + suffix;

        if (progress < 1) {
          requestAnimationFrame(step);
        } else {
          el.textContent = target.toFixed(decimals) + suffix;
        }
      };
      requestAnimationFrame(step);
    }, delay);
  };

  const observerOptions = {
    threshold: 0.25,
  };

  const statsObserver = new IntersectionObserver((entries, observer) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        const statValues = entry.target.querySelectorAll(".stat-value");
        statValues.forEach((el, index) => {
          animateCounter(el, index);
        });
        observer.unobserve(entry.target);
      }
    });
  }, observerOptions);

  const statsFooter = document.querySelector(".stats-footer");
  if (statsFooter) {
    statsObserver.observe(statsFooter);
  }

  // --- 2. Mobile Menu Controller ---
  const burgerBtn = document.getElementById("burgerBtn");
  const mobileOverlay = document.getElementById("mobileOverlay");
  const mobileMenu = document.getElementById("mobileMenu");
  const mobileLinks = document.querySelectorAll(".mobile-nav-link, .mobile-sign-in");

  if (burgerBtn && mobileOverlay && mobileMenu) {
    const openMenu = () => {
      burgerBtn.setAttribute("aria-expanded", "true");
      mobileOverlay.hidden = false;
      mobileMenu.hidden = false;
      document.body.classList.add("menu-open");
    };

    const closeMenu = () => {
      burgerBtn.setAttribute("aria-expanded", "false");
      mobileOverlay.hidden = true;
      mobileMenu.hidden = true;
      document.body.classList.remove("menu-open");
    };

    const toggleMenu = () => {
      const isOpen = burgerBtn.getAttribute("aria-expanded") === "true";
      if (isOpen) {
        closeMenu();
      } else {
        openMenu();
      }
    };

    burgerBtn.addEventListener("click", toggleMenu);
    mobileOverlay.addEventListener("click", closeMenu);

    mobileLinks.forEach((link) => {
      link.addEventListener("click", closeMenu);
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && burgerBtn.getAttribute("aria-expanded") === "true") {
        closeMenu();
      }
    });

    window.addEventListener("resize", () => {
      if (window.innerWidth > 720 && burgerBtn.getAttribute("aria-expanded") === "true") {
        closeMenu();
      }
    });
  }

  // --- 3. Rule Book Modal Controller ---
  const rulesNavBtn = document.getElementById("rulesNavBtn");
  const mobileRulesBtn = document.getElementById("mobileRulesBtn");
  const rulesModal = document.getElementById("rulesModal");
  const closeRulesBtn = document.getElementById("closeRulesBtn");

  const openRulesModal = (e) => {
    if (e) e.preventDefault();
    if (rulesModal) {
      rulesModal.hidden = false;
      rulesModal.style.display = "flex";
    }
  };

  const closeRulesModal = () => {
    if (rulesModal) {
      rulesModal.hidden = true;
      rulesModal.style.display = "none";
    }
  };


  if (rulesNavBtn) rulesNavBtn.addEventListener("click", openRulesModal);
  if (mobileRulesBtn) mobileRulesBtn.addEventListener("click", openRulesModal);
  if (closeRulesBtn) closeRulesBtn.addEventListener("click", closeRulesModal);

  if (rulesModal) {
    rulesModal.addEventListener("click", (e) => {
      if (e.target === rulesModal) closeRulesModal();
    });
  }

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && rulesModal && !rulesModal.hidden) {
      closeRulesModal();
    }
  });
});

