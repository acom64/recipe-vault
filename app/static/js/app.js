document.addEventListener("submit", (event) => {
  const form = event.target;
  const confirmMessage = form.dataset.confirm;

  if (confirmMessage && !window.confirm(confirmMessage)) {
    event.preventDefault();
    return;
  }

  if (form.matches("[data-favorite-form]")) {
    event.preventDefault();
    toggleFavorite(form);
    return;
  }

  const submitButton = form.querySelector("[data-loading-text]");

  if (submitButton) {
    submitButton.dataset.originalText = submitButton.innerHTML;
    submitButton.innerHTML = submitButton.dataset.loadingText;
    submitButton.disabled = true;
  }
});

const setFavoriteState = (form, isFavorite, data = {}) => {
  const button = form.querySelector("[data-favorite-button]");
  const icon = form.querySelector("[data-favorite-icon]");
  const label = form.querySelector("[data-favorite-label]");
  const card = form.closest(".recipe-card");
  const chip = card ? card.querySelector(".favorite-chip") : null;
  const ariaLabel = data.aria_label || (isFavorite ? "Remove favorite" : "Favorite");

  if (button) {
    button.setAttribute("aria-label", ariaLabel);
    button.setAttribute("title", ariaLabel);
    button.disabled = false;
  }

  if (icon) {
    icon.classList.toggle("bi-heart-fill", isFavorite);
    icon.classList.toggle("bi-heart", !isFavorite);
  }

  if (label) {
    label.textContent = data.button_label || (isFavorite ? "Favorited" : "Favorite");
  }

  if (chip) {
    chip.hidden = !isFavorite;
  }
};

const toggleFavorite = async (form) => {
  const button = form.querySelector("[data-favorite-button]");

  if (button) {
    button.disabled = true;
  }

  try {
    const response = await fetch(form.action, {
      method: "POST",
      body: new FormData(form),
      headers: {
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest"
      },
      credentials: "same-origin"
    });

    if (!response.ok) {
      form.submit();
      return;
    }

    const data = await response.json();
    setFavoriteState(form, Boolean(data.is_favorite), data);
  } catch (_error) {
    form.submit();
  }
};
