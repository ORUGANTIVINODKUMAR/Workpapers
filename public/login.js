document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const username = document.getElementById("username").value.trim();
  const password = document.getElementById("password").value.trim();
  const msg = document.getElementById("login-msg");

  const response = await fetch("/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
    credentials: "include" // ✅ keep session cookie
  });

  if (response.ok) {
  
    const data = await response.json();
    window.location.href = data.redirect || "/details";

  } else {
    const { error } = await response.json();
    msg.innerText = error || "Invalid credentials";
  }
});
