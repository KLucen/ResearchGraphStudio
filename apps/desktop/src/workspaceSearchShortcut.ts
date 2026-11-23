export function handleWorkspaceFind(
  event: KeyboardEvent,
  activate: () => void,
) {
  if (
    event.defaultPrevented ||
    event.isComposing ||
    event.altKey ||
    event.shiftKey ||
    (!event.ctrlKey && !event.metaKey) ||
    event.key.toLowerCase() !== "f"
  ) {
    return;
  }
  const modal = document.querySelector("dialog[open]:modal");
  if (modal) {
    const search = modal.querySelector<HTMLInputElement>(
      'input[type="search"]',
    );
    if (search) {
      event.preventDefault();
      search.focus();
      search.select();
    }
    return;
  }
  event.preventDefault();
  activate();
}
