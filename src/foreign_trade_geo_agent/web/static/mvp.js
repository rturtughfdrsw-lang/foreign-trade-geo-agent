"use strict";
const sampleButton = document.getElementById("fill-sample");
const textarea = document.getElementById("evidence-text");
if (sampleButton) sampleButton.addEventListener("click", () => {
  textarea.value = document.getElementById("sample-text").content.textContent;
  textarea.focus();
});
const fileInput = document.getElementById("text-file");
if (fileInput) fileInput.addEventListener("change", async () => {
  const error = document.getElementById("file-error");
  error.hidden = true;
  const file = fileInput.files[0];
  if (!file) return;
  try {
    if (file.size > 64000) throw new Error();
    const text = new TextDecoder("utf-8", {fatal: true}).decode(await file.arrayBuffer());
    if ([...text].length > 16000) throw new Error();
    textarea.value = text;
  } catch (_) {
    error.textContent = "无法读取：请选择有效的 UTF-8 文本文件，最多 16,000 字符。原有文本未改变。";
    error.hidden = false;
  }
});
document.querySelectorAll("form").forEach(form => form.addEventListener("submit", () => {
  const button = form.querySelector('button[type="submit"]');
  if (button) { button.disabled = true; button.textContent = "处理中…"; }
}));

// Read-only status polling; never POST or replay generation.
if (document.querySelector('[data-generation-state="RUNNING"]')) {
  window.setTimeout(() => window.location.replace("/mvp/generate"), 1500);
}
