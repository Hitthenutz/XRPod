/**
 * entity.subscribe() that never throws and always returns an unsubscribe
 * function, so a live-update failure degrades to "no live updates" instead
 * of crashing the HUD. Errors inside `handler` are caught per event.
 */
export function safeSubscribe(entity, handler, label) {
  try {
    const unsubscribe = entity.subscribe((event) => {
      try {
        handler(event);
      } catch (err) {
        console.error(`Bad live update for ${label}:`, err, event);
      }
    });
    return typeof unsubscribe === "function" ? unsubscribe : () => {};
  } catch (err) {
    console.error(`Couldn't subscribe to ${label} updates:`, err);
    return () => {};
  }
}
