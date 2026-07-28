(() => {
  const form = document.querySelector("[data-assessment-form]");
  if (!form) return;

  const setSelectedState = (input) => {
    input.closest(".checkbox-item")?.classList.toggle("is-selected", input.checked);
  };

  const clearFieldError = (control) => {
    const field = control.closest(".form-field");
    if (!field) return;
    field.classList.remove("has-error");
    control.removeAttribute("aria-invalid");
    const error = field.querySelector(".form-error");
    if (error) error.textContent = "";
  };

  const setFieldError = (control, message) => {
    const field = control.closest(".form-field");
    if (!field) return;
    field.classList.add("has-error");
    control.setAttribute("aria-invalid", "true");
    const error = field.querySelector(".form-error");
    if (error) error.textContent = message;
  };

  const controlErrorMessage = (control) => {
    if (control.validity.valueMissing) return control.dataset.errorRequired || "请填写此项";
    if (control.validity.badInput) return control.dataset.errorNumber || "请输入有效数字";
    if (control.validity.rangeUnderflow || control.validity.rangeOverflow) {
      return control.dataset.errorRange || "输入值超出允许范围";
    }
    if (control.validity.patternMismatch) return control.dataset.errorPattern || "输入格式不正确";
    return "请检查填写内容";
  };

  const validateControl = (control) => {
    clearFieldError(control);
    if (control.checkValidity()) return true;
    setFieldError(control, controlErrorMessage(control));
    return false;
  };

  const formatMoneyHint = (input) => {
    const hint = input.closest(".form-field")?.querySelector("[data-money-hint]");
    if (!hint) return;
    const amount = Number(input.value);
    if (!input.value || !Number.isFinite(amount) || amount < 0) {
      hint.textContent = "";
      return;
    }
    hint.textContent = amount >= 10000
      ? `约${(amount / 10000).toLocaleString("zh-CN", {maximumFractionDigits: 2})}万元`
      : `约${amount.toLocaleString("zh-CN", {maximumFractionDigits: 2})}元`;
  };

  const purposeGroup = form.querySelector('[data-checkbox-group="funding-purpose"]');
  const purposeOptions = [...form.querySelectorAll("[data-purpose-option]")];
  const otherPurposeBox = form.querySelector("[data-other-purpose]");
  const otherPurposeInput = form.querySelector('textarea[name="funding_purpose_other"]');

  const syncOtherPurpose = () => {
    const otherSelected = purposeOptions.some((item) => item.value === "其他" && item.checked);
    if (otherPurposeBox) otherPurposeBox.hidden = !otherSelected;
    if (!otherSelected && otherPurposeInput) otherPurposeInput.value = "";
  };

  const validatePurposeGroup = () => {
    if (!purposeGroup) return true;
    purposeGroup.classList.remove("has-error");
    const selected = purposeOptions.filter((item) => item.checked);
    const otherSelected = selected.some((item) => item.value === "其他");
    const valid = selected.length > 0 && (!otherSelected || Boolean(otherPurposeInput?.value.trim()));
    if (!valid) {
      purposeGroup.classList.add("has-error");
      const error = purposeGroup.querySelector(".form-error");
      if (error) {
        error.textContent = selected.length
          ? "选择“其他”后，请补充具体融资用途"
          : "请至少选择一个融资用途";
      }
    }
    return valid;
  };

  const collateralGroup = form.querySelector('[data-checkbox-group="collateral"]');
  const collateralOptions = [...form.querySelectorAll("[data-collateral-option]")];

  const validateCollateralGroup = () => {
    if (!collateralGroup) return true;
    const valid = collateralOptions.some((item) => item.checked);
    collateralGroup.classList.toggle("has-error", !valid);
    return valid;
  };

  purposeOptions.forEach((input) => {
    setSelectedState(input);
    input.addEventListener("change", () => {
      setSelectedState(input);
      purposeGroup?.classList.remove("has-error");
      syncOtherPurpose();
    });
  });

  otherPurposeInput?.addEventListener("input", () => purposeGroup?.classList.remove("has-error"));
  syncOtherPurpose();

  collateralOptions.forEach((input) => {
    setSelectedState(input);
    input.addEventListener("change", () => {
      if (input.value === "暂无抵押物" && input.checked) {
        collateralOptions.filter((item) => item !== input).forEach((item) => {
          item.checked = false;
          setSelectedState(item);
        });
      } else if (input.checked) {
        const noneOption = collateralOptions.find((item) => item.value === "暂无抵押物");
        if (noneOption) {
          noneOption.checked = false;
          setSelectedState(noneOption);
        }
      }
      setSelectedState(input);
      collateralGroup?.classList.remove("has-error");
    });
  });

  form.querySelectorAll('input[name="intellectual_property_types"]').forEach((input) => {
    setSelectedState(input);
    input.addEventListener("change", () => setSelectedState(input));
  });

  form.querySelectorAll("[data-money-input]").forEach((input) => {
    input.addEventListener("input", () => formatMoneyHint(input));
    formatMoneyHint(input);
  });

  form.querySelectorAll(".form-control").forEach((control) => {
    control.addEventListener("input", () => clearFieldError(control));
    control.addEventListener("change", () => clearFieldError(control));
    control.addEventListener("blur", () => {
      if (control.value || control.required) validateControl(control);
    });
  });

  form.addEventListener("submit", (event) => {
    const controlsValid = [...form.querySelectorAll(".form-control")]
      .map((control) => validateControl(control))
      .every(Boolean);
    const purposeValid = validatePurposeGroup();
    const collateralValid = validateCollateralGroup();

    if (!controlsValid || !purposeValid || !collateralValid) {
      event.preventDefault();
      const firstInvalid = form.querySelector(".has-error .form-control, .checkbox-group.has-error input");
      firstInvalid?.focus();
      firstInvalid?.closest(".assessment-section")?.scrollIntoView({behavior: "smooth", block: "start"});
      return;
    }

    const button = form.querySelector("[data-submit-button]");
    if (button) {
      button.disabled = true;
      button.textContent = "正在提交……";
    }
  });
})();
