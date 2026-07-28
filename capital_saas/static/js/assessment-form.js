(() => {
  const nullableNumber = (value) => {
    if (value === null || value === undefined) return null;
    const normalized = String(value).trim();
    if (normalized === "") return null;
    const number = Number(normalized);
    return Number.isFinite(number) ? number : null;
  };

  const form = document.querySelector("[data-assessment-form]");
  if (!form) return;
  const submitAlert = form.querySelector("[data-submit-alert]");
  const submitButton = form.querySelector("[data-submit-button]");

  const showSubmitAlert = (message) => {
    if (!submitAlert) return;
    submitAlert.textContent = message;
    submitAlert.hidden = false;
  };

  const hideSubmitAlert = () => {
    if (!submitAlert) return;
    submitAlert.hidden = true;
    submitAlert.textContent = "";
  };

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

  const setGroupError = (group, message) => {
    if (!group) return;
    group.classList.add("has-error");
    const error = group.querySelector(".form-error");
    if (error) error.textContent = message;
    group.querySelector("input, textarea, select")?.setAttribute("aria-invalid", "true");
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

  const applyServerError = (name, message) => {
    if (name === "funding_purposes") {
      setGroupError(purposeGroup, message);
      return;
    }
    if (name === "collateral_types") {
      setGroupError(collateralGroup, message);
      return;
    }
    const control = form.querySelector(`[name="${CSS.escape(name)}"]`);
    if (!control) return;
    control.closest("details")?.setAttribute("open", "");
    setFieldError(control, message);
  };

  const scrollToFirstError = () => {
    const firstInvalid = form.querySelector(
      ".has-error .form-control, .checkbox-group.has-error input"
    );
    firstInvalid?.focus();
    firstInvalid?.closest(".assessment-section")?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  };

  const restoreServerState = () => {
    const stateNode = form.querySelector("[data-assessment-server-state]");
    if (!stateNode) return;
    let state = {};
    try {
      state = JSON.parse(stateNode.textContent || "{}");
    } catch {
      return;
    }
    Object.entries(state.values || {}).forEach(([name, rawValue]) => {
      const values = Array.isArray(rawValue) ? rawValue.map(String) : [String(rawValue ?? "")];
      form.querySelectorAll(`[name="${CSS.escape(name)}"]`).forEach((control) => {
        if (control.type === "checkbox" || control.type === "radio") {
          control.checked = values.includes(control.value);
          setSelectedState(control);
        } else {
          control.value = values[0];
        }
      });
    });
    Object.entries(state.errors || {}).forEach(([name, message]) => {
      applyServerError(name, message);
    });
  };

  restoreServerState();

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

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    hideSubmitAlert();
    const controlsValid = [...form.querySelectorAll(".form-control")]
      .map((control) => validateControl(control))
      .every(Boolean);
    const purposeValid = validatePurposeGroup();
    const collateralValid = validateCollateralGroup();

    if (!controlsValid || !purposeValid || !collateralValid) {
      showSubmitAlert("部分内容尚未正确填写，请检查标红字段。");
      scrollToFirstError();
      return;
    }

    const formData = new FormData(form);
    form.querySelectorAll('input[type="number"]:not([required])').forEach((input) => {
      if (nullableNumber(input.value) === null && !String(input.value).trim()) {
        formData.delete(input.name);
      }
    });

    if (submitButton) {
      submitButton.disabled = true;
      submitButton.textContent = "正在提交……";
    }

    try {
      const response = await fetch(form.action, {
        method: "POST",
        body: formData,
        headers: {
          "Accept": "application/json",
          "X-Assessment-Ajax": "1",
        },
      });
      const result = await response.json().catch(() => null);

      if (response.ok && result?.redirect_url) {
        window.location.assign(result.redirect_url);
        return;
      }

      if (response.status === 422 && result?.errors) {
        Object.entries(result.errors).forEach(([name, message]) => {
          applyServerError(name, message);
        });
        showSubmitAlert(
          result.message || "部分数值填写格式不正确，请检查标红字段。"
        );
        scrollToFirstError();
        return;
      }

      showSubmitAlert("提交暂未成功，请稍后重试。您填写的内容已保留。");
    } catch {
      showSubmitAlert("网络连接异常，请检查网络后重试。您填写的内容已保留。");
    } finally {
      if (submitButton) {
        submitButton.disabled = false;
        submitButton.textContent = "生成免费测评结果";
      }
    }
  });
})();
