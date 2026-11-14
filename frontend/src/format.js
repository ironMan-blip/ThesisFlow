// The SRS says all times are shown in Dhaka time, whatever the browser's zone.
export const TIME_ZONE = "Asia/Dhaka";
// Bangladesh has no daylight saving, so the offset is fixed.
export const DHAKA_OFFSET = "+06:00";

// ISO string -> date and time in Dhaka time.
export const when = (iso) =>
  new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short", timeZone: TIME_ZONE });

// "Full Name (INI)"; faculty have initials, students don't.
export const personName = (p) => `${p.full_name}${p.initials ? ` (${p.initials})` : ""}`;

// ISO string -> "YYYY-MM-DDTHH:mm" in Dhaka time, for date and time inputs.
export const toDhakaInput = (iso) => new Date(new Date(iso).getTime() + 6 * 3600000).toISOString().slice(0, 16);

// Date and time inputs, read as Dhaka time -> ISO string.
export const fromDhakaInput = (date, time) => new Date(`${date}T${time}${DHAKA_OFFSET}`).toISOString();
