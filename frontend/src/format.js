// ISO string -> date and time in Dhaka time: the SRS shows every time in Dhaka time, whatever the browser's zone.
export const when = (iso) =>
  new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Dhaka" });

// "Full Name (INI)"; faculty have initials, students don't.
export const personName = (p) => `${p.full_name}${p.initials ? ` (${p.initials})` : ""}`;

// A thesis's group members as "A, B, C"; archived theses may have none left.
export const memberNames = (t) => t.members.map((m) => m.full_name).join(", ") || "No current members";

// <input type="date|time"> values <-> ISO strings, always in Dhaka time (UTC+6, no daylight saving).
const DHAKA_OFFSET_MS = 6 * 3600 * 1000;
export const toDhakaInput = (iso) => new Date(new Date(iso).getTime() + DHAKA_OFFSET_MS).toISOString().slice(0, 16);
export const fromDhakaInput = (date, time) => new Date(`${date}T${time}:00+06:00`).toISOString();
