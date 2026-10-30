// ISO string -> date and time in the browser's locale.
export const when = (iso) => new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
