/* FitBuddy — client-side validation for the intake form. */

(function () {
  "use strict";

  var GOALS = ["weight loss", "muscle gain", "general wellness"];
  var INTENSITIES = ["low", "medium", "high"];

  function setError(name, message) {
    var el = document.querySelector('[data-error-for="' + name + '"]');
    if (!el) return;
    if (message) {
      el.textContent = message;
      el.hidden = false;
    } else {
      el.textContent = "";
      el.hidden = true;
    }
    var input = document.querySelector('[name="' + name + '"]');
    if (input && input.type !== "radio") {
      if (message) input.setAttribute("aria-invalid", "true");
      else input.removeAttribute("aria-invalid");
    }
  }

  function number(value) {
    if (value === null || value.trim() === "") return NaN;
    return Number(value);
  }

  function validate(data) {
    var errors = {};
    var name = (data.name || "").trim();
    if (name.length < 2 || name.length > 80) {
      errors.name = "Enter a name between 2 and 80 characters.";
    }

    var age = number(data.age);
    if (!Number.isInteger(age) || age < 13 || age > 100) {
      errors.age = "Age must be a whole number from 13 to 100.";
    }

    var weight = number(data.weight);
    if (!Number.isFinite(weight) || weight < 30 || weight > 300) {
      errors.weight = "Weight must be between 30 and 300 kg.";
    }

    if (GOALS.indexOf(String(data.goal).toLowerCase()) === -1) {
      errors.goal = "Choose one of the three goals.";
    }

    if (INTENSITIES.indexOf(String(data.intensity).toLowerCase()) === -1) {
      errors.intensity = "Choose low, medium or high.";
    }

    return errors;
  }

  var form = document.getElementById("intake-form");
  if (!form) return;

  function collect() {
    var fields = new FormData(form);
    return {
      name: fields.get("name"),
      age: fields.get("age"),
      weight: fields.get("weight"),
      goal: fields.get("goal"),
      intensity: fields.get("intensity"),
    };
  }

  function clearErrors() {
    ["name", "age", "weight", "goal", "intensity"].forEach(function (key) {
      setError(key, "");
    });
  }

  form.addEventListener("input", function (event) {
    var key = event.target.name;
    if (key) setError(key, "");
  });

  form.addEventListener("submit", function (event) {
    var errors = validate(collect());
    clearErrors();

    var firstInvalid = null;
    Object.keys(errors).forEach(function (key) {
      setError(key, errors[key]);
      if (!firstInvalid) {
        firstInvalid = document.querySelector('[name="' + key + '"]');
      }
    });

    if (Object.keys(errors).length > 0) {
      event.preventDefault();
      if (firstInvalid) firstInvalid.focus();
    }
  });
})();
