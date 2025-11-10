// logout.js — handles logout for all pages
const logoutBtn = document.getElementById("logout-btn");
if (logoutBtn) {
  logoutBtn.addEventListener("click", async () => {
    try {
      const res = await fetch("/logout", { method: "POST" });
      if (res.ok) {
        // Clear any local state (if needed)
        sessionStorage.clear();
        localStorage.clear();
        window.location.href = "/login.html";
      } else {
        alert("Logout failed, please try again.");
      }
    } catch (err) {
      console.error("Logout error:", err);
      alert("Unable to log out. Please try again.");
    }
  });
}
