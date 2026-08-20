(function () {
  "use strict";

  function syncOtherField(container) {
    var select = container.querySelector("[data-other-select]");
    var input = container.querySelector("[data-other-input]");
    if (!select || !input) return;
    var show = select.value === "其他";
    input.classList.toggle("is-hidden", !show);
    input.disabled = !show;
    input.setAttribute("aria-hidden", show ? "false" : "true");
    if (show) input.removeAttribute("tabindex");
    else input.setAttribute("tabindex", "-1");
  }

  document.querySelectorAll("[data-select-other-field]").forEach(function (container) {
    var select = container.querySelector("[data-other-select]");
    syncOtherField(container);
    if (select) select.addEventListener("change", function () { syncOtherField(container); });
  });
}());
