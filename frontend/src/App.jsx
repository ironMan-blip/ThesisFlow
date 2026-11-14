import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import AccountPage from "./pages/AccountPage";
import AccountsPage from "./pages/AccountsPage";
import DeadlinePage from "./pages/DeadlinePage";
import HomePage from "./pages/HomePage";
import LoginPage from "./pages/LoginPage";
import NotFoundPage from "./pages/NotFoundPage";
import ProposalPage from "./pages/ProposalPage";
import { DeletionRequestsPage, RegistrationRequestsPage, RestartRequestsPage } from "./pages/RequestsPage";
import ThesesPage from "./pages/ThesesPage";
import ThesisPage from "./pages/ThesisPage";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      {/* Pages that need a logged-in user go inside Layout. */}
      <Route element={<Layout />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/thesis" element={<ThesisPage />} />
        <Route path="/theses" element={<ThesesPage />} />
        <Route path="/proposal" element={<ProposalPage />} />
        <Route path="/deadlines" element={<DeadlinePage />} />
        <Route path="/accounts" element={<AccountsPage />} />
        <Route path="/registration-requests" element={<RegistrationRequestsPage />} />
        <Route path="/deletion-requests" element={<DeletionRequestsPage />} />
        <Route path="/restart-requests" element={<RestartRequestsPage />} />
        <Route path="/account" element={<AccountPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
