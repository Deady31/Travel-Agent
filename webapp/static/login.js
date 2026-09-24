import { login } from "./js/api.js";

const form = document.getElementById("login-form");
const btn = document.getElementById("login-btn");
const msg = document.getElementById("login-msg");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  btn.disabled = true;
  msg.textContent = "Vérification…";
  try {
    await login(document.getElementById("password").value);
    window.location.href = "/";
  } catch (err) {
    msg.textContent = err.message;
    btn.disabled = false;
    document.getElementById("password").select();
  }
});
