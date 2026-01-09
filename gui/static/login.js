//gui/static/login.js
// SHA-256 helper
async function sha256(message) {
  const msgBuffer = new TextEncoder().encode(message);
  const hashBuffer = await crypto.subtle.digest("SHA-256", msgBuffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, "0")).join("");
}

// Store only the HASH of your password here (generated once beforehand)
const correctHash = "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3" // example

document.getElementById("loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const password = document.getElementById("password").value;
  const hash = await sha256(password);

  if (hash === correctHash) {
    sessionStorage.setItem("loggedIn", "true");
    window.location.href = "/static/index.html";
  } else {
    const err = document.getElementById("error-message");
    err.textContent = "Invalid password.";
    err.style.display = "block";
  }
});

// Redirect protection (index.html & others should include this check)
if (window.location.pathname.endsWith("index.html")) {
  if (sessionStorage.getItem("loggedIn") !== "true") {
    window.location.href = "/static/login.html";
  }
}

// Protect index.html
if (window.location.pathname.endsWith("index.html")) {
  if (sessionStorage.getItem("loggedIn") !== "true") {
    window.location.replace("/static/login.html");
  }
}
