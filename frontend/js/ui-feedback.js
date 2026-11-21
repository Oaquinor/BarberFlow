"use strict";

(() => {
  if (!document.body || document.getElementById("appFeedbackRoot")) return;

  const root = document.createElement("div");
  root.id = "appFeedbackRoot";
  root.className = "app-feedback-root";

  const toast = document.createElement("div");
  toast.className = "app-toast";
  toast.hidden = true;
  toast.setAttribute("role", "status");
  toast.setAttribute("aria-live", "polite");
  toast.setAttribute("aria-atomic", "true");
  const toastText = document.createElement("span");
  const dismissToast = document.createElement("button");
  dismissToast.type = "button";
  dismissToast.className = "app-feedback-dismiss";
  dismissToast.setAttribute("aria-label", "Cerrar aviso");
  dismissToast.textContent = "Cerrar";
  toast.append(toastText, dismissToast);

  const dialog = document.createElement("dialog");
  dialog.className = "app-confirm-dialog";
  dialog.setAttribute("aria-labelledby", "appConfirmTitle");
  dialog.setAttribute("aria-describedby", "appConfirmMessage");
  const title = document.createElement("h2");
  title.id = "appConfirmTitle";
  title.textContent = "Confirmar acción";
  const message = document.createElement("p");
  message.id = "appConfirmMessage";
  const actions = document.createElement("div");
  actions.className = "app-confirm-actions";
  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.className = "btn-secondary";
  cancel.textContent = "Cancelar";
  const accept = document.createElement("button");
  accept.type = "button";
  accept.className = "btn-primary";
  accept.textContent = "Confirmar";
  actions.append(cancel, accept);
  dialog.append(title, message, actions);
  root.append(toast, dialog);
  document.body.append(root);

  let toastTimer = null;
  dismissToast.addEventListener("click", () => {
    clearTimeout(toastTimer);
    toast.hidden = true;
  });

  let resolveConfirmation = null;
  cancel.addEventListener("click", () => dialog.close("cancel"));
  accept.addEventListener("click", () => dialog.close("confirm"));
  dialog.addEventListener("close", () => {
    const resolve = resolveConfirmation;
    resolveConfirmation = null;
    resolve?.(dialog.returnValue === "confirm");
  });
  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    dialog.close("cancel");
  });

  window.showToast = (text, kind = "error") => {
    clearTimeout(toastTimer);
    toastText.textContent = String(text ?? "");
    const isError = kind === "error";
    toast.dataset.kind = isError ? "error" : "info";
    toast.setAttribute("role", isError ? "alert" : "status");
    toast.setAttribute("aria-live", isError ? "assertive" : "polite");
    toast.hidden = !toastText.textContent;
    if (!toast.hidden) {
      toastTimer = setTimeout(() => { toast.hidden = true; }, isError ? 10000 : 6500);
    }
  };

  let confirmationQueue = Promise.resolve();
  const askConfirmation = (text, options = {}) => new Promise((resolve) => {
    title.textContent = options.title || "Confirmar acción";
    message.textContent = String(text ?? "");
    accept.textContent = options.confirmLabel || "Confirmar";
    accept.classList.toggle("app-confirm-danger", options.danger === true);
    resolveConfirmation = resolve;
    dialog.returnValue = "";
    dialog.showModal();
    cancel.focus();
  });

  window.showConfirmation = (text, options = {}) => {
    const request = confirmationQueue.then(() => askConfirmation(text, options));
    confirmationQueue = request.catch(() => false);
    return request;
  };
})();
