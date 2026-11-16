// ISO string -> date and time in Dhaka time: the SRS shows every time in Dhaka time, whatever the browser's zone.
export const when = (iso) =>
  new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Dhaka" });

// "Full Name (INI)"; faculty have initials, students don't.
export const personName = (p) => `${p.full_name}${p.initials ? ` (${p.initials})` : ""}`;
