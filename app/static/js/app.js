document.addEventListener("submit", (event) => {
  const form = event.target;
  const confirmMessage = form.dataset.confirm;

  if (confirmMessage && !window.confirm(confirmMessage)) {
    event.preventDefault();
    return;
  }

  const submitButton = form.querySelector("[data-loading-text]");

  if (submitButton) {
    submitButton.dataset.originalText = submitButton.innerHTML;
    submitButton.innerHTML = submitButton.dataset.loadingText;
    submitButton.disabled = true;
  }
});
