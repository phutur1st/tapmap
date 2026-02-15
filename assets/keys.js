(function () {
  function isTypingTarget(el) {
    if (!el) return false;

    // Ikke blokker snarveier når target er det tekniske feltet
    if ((el.id || "") === "key_capture") return false;

    const tag = (el.tagName || "").toLowerCase();
    return tag === "input" || tag === "textarea" || el.isContentEditable;
  }

  function setNativeValue(el, value) {
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      "value"
    ).set;
    setter.call(el, value);
  }

  function sendToken(token) {
    const inp = document.getElementById("key_capture");
    if (!inp) return;

    const v = token + "|" + Date.now();
    setNativeValue(inp, v);

    // Må være input-event for at Dash skal trigge callbacken
    inp.dispatchEvent(new Event("input", { bubbles: true }));
  }

  window.addEventListener(
    "keydown",
    function (e) {
      if (isTypingTarget(e.target)) return;

      const k = (e.key || "").toLowerCase();

      if (e.key === "Escape") {
        e.preventDefault();
        sendToken("__esc__");
        return;
      }

      if (k === "o" || k === "u" || k === "t" || k === "c" || k === "h" || k === "a") {
        sendToken("__" + k + "__");
      }
    },
    true
  );
})();
