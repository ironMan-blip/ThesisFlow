// The SRS says all times are shown in Dhaka time, whatever the browser's zone.
export const TIME_ZONE = "Asia/Dhaka";

// ISO string -> date and time in Dhaka time.
export const when = (iso) =>
  new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short", timeZone: TIME_ZONE });

// "Full Name (INI)"; faculty have initials, students don't.
export const personName = (p) => `${p.full_name}${p.initials ? ` (${p.initials})` : ""}`;
