import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import AccountPage from "./pages/AccountPage";
import DeadlinePage from "./pages/DeadlinePage";
import HomePage from "./pages/HomePage";
import LoginPage from "./pages/LoginPage";
import NotFoundPage from "./pages/NotFoundPage";
import ProposalPage from "./pages/ProposalPage";
import { DeletionRequestsPage, RegistrationRequestsPage } from "./pages/RequestsPage";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      {/* Pages that need a logged-in user go inside Layout. */}
      <Route element={<Layout />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/proposal" element={<ProposalPage />} />
        <Route path="/deadlines" element={<DeadlinePage />} />
        <Route path="/registration-requests" element={<RegistrationRequestsPage />} />
        <Route path="/deletion-requests" element={<DeletionRequestsPage />} />
        <Route path="/account" element={<AccountPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
