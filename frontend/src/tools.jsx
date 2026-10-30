// Display info for each tool; which tools a user gets comes from the API (user.tools).
// Nav and dashboard both read this, so a new tool is added here only.
export const TOOLS = {
  proposal: {
    to: "/proposal", title: "Proposal", text: "Upload a new version and see your past submissions.",
    icon: <><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5M12 18v-6M9 15l3-3 3 3" /></>,
  },
  deadlines: {
    to: "/deadlines", title: "Deadlines", text: "P1, P2 and P3 due dates, grace time and countdowns.",
    icon: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  },
  accounts: {
    to: "/accounts", title: "Accounts", text: "View every account and delete one if needed.",
    icon: <><circle cx="9" cy="8" r="4" /><path d="M2 21a7 7 0 0 1 14 0M17 4a4 4 0 0 1 0 8M22 21a7 7 0 0 0-4-6.3" /></>,
  },
  registration_requests: {
    to: "/registration-requests", title: "Registration requests", text: "Approve or reject students and faculty who registered.",
    icon: <><circle cx="9" cy="8" r="4" /><path d="M2 21a7 7 0 0 1 14 0M16 11l2 2 4-4" /></>,
  },
  deletion_requests: {
    to: "/deletion-requests", title: "Deletion requests", text: "Approve or reject users who asked to delete their account.",
    icon: <><circle cx="9" cy="8" r="4" /><path d="M2 21a7 7 0 0 1 14 0M16 10l5 5M21 10l-5 5" /></>,
  },
  account: {
    to: "/account", title: "Account", text: "Your account details, and asking to delete your account.",
    icon: <><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></>,
  },
};
