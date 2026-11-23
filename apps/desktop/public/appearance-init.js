(() => {
  let preference;
  try {
    preference = localStorage.getItem("rgs.appearance");
  } catch {
    preference = null;
  }
  const root = document.documentElement;
  root.dataset.appearance =
    preference === "light" || preference === "dark" ? preference : "system";
  root.dataset.theme =
    root.dataset.appearance === "system"
      ? matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light"
      : root.dataset.appearance;
})();
