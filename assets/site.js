(function () {
  "use strict";

  var body = document.body;
  var gate = document.getElementById("access-gate");
  var digest = body.dataset.accessDigest || "";

  function hex(buffer) {
    return Array.from(new Uint8Array(buffer), function (byte) {
      return byte.toString(16).padStart(2, "0");
    }).join("");
  }

  async function sha256(value) {
    var bytes = new TextEncoder().encode(value);
    return hex(await crypto.subtle.digest("SHA-256", bytes));
  }

  function unlock() {
    body.classList.remove("is-locked");
    if (gate) gate.hidden = true;
  }

  if (!digest) {
    unlock();
  } else if (sessionStorage.getItem("xhs-site-access") === digest) {
    unlock();
  } else if (gate) {
    var form = gate.querySelector("form");
    var input = gate.querySelector("input");
    var error = gate.querySelector(".gate-error");
    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      error.textContent = "";
      try {
        if (await sha256(input.value) === digest) {
          sessionStorage.setItem("xhs-site-access", digest);
          input.value = "";
          unlock();
        } else {
          error.textContent = "访问码不正确";
          input.select();
        }
      } catch (_error) {
        error.textContent = "当前浏览器无法校验访问码";
      }
    });
  }

  document.querySelectorAll("[data-download-group]").forEach(function (button) {
    button.addEventListener("click", async function () {
      var note = button.closest(".note");
      var links = Array.from(note.querySelectorAll("a.original-link"));
      var status = note.querySelector(".download-status");
      if (!links.length) return;

      button.disabled = true;
      button.textContent = "正在准备原图…";
      if (status) status.textContent = "";
      try {
        for (var index = 0; index < links.length; index += 1) {
          var response = await fetch(links[index].href);
          if (!response.ok) throw new Error("HTTP " + response.status);
          var blob = await response.blob();
          var anchor = document.createElement("a");
          anchor.href = URL.createObjectURL(blob);
          anchor.download = links[index].getAttribute("download") || ("image-" + (index + 1) + ".png");
          document.body.appendChild(anchor);
          anchor.click();
          window.setTimeout(function (url, element) {
            URL.revokeObjectURL(url);
            element.remove();
          }, 1500, anchor.href, anchor);
          await new Promise(function (resolve) { window.setTimeout(resolve, 260); });
        }
        if (status) status.textContent = "已触发 " + links.length + " 张原图下载";
      } catch (error) {
        if (status) status.textContent = "批量下载失败，可使用每张图片下方的“下载原图”。";
      } finally {
        button.disabled = false;
        button.textContent = "下载本篇全部原图";
      }
    });
  });
})();
