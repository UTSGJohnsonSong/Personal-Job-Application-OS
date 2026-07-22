document.getElementById("scan").addEventListener("click", async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const out = document.getElementById("out");
  try {
    const res = await chrome.tabs.sendMessage(tab.id, { type: "JOBOS_SCAN" });
    out.textContent = `Fields: ${res.fields}. Empty required flagged: ${res.flaggedEmptyRequired}.`;
  } catch {
    out.textContent = "No application page detected on this tab.";
  }
});
